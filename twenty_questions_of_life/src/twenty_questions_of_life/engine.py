"""The interview itself, with no terminal in it.

main.py drives this from a crewAI Flow and a keyboard; web.py drives the same
object from HTTP requests. Everything that talks to a model lives here, so the
two front ends cannot drift apart in what they actually ask you or how they
mark you.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from twenty_questions_of_life import scoring, session
from twenty_questions_of_life.crews.assessor_crew.assessor_crew import AssessorCrew
from twenty_questions_of_life.crews.panel_crew.panel_crew import PanelCrew
from twenty_questions_of_life.crews.verdict_crew.verdict_crew import VerdictCrew
from twenty_questions_of_life.dimensions import DIMENSION_KEYS, DIMENSIONS_BY_KEY, describe
from twenty_questions_of_life.models import AnswerAssessment, Exchange, NextQuestion, Verdict

PASS_WORDS = {"pass", "skip", "no comment"}

OPENING_PROBE = "Nothing yet. Open where you like."

PASSED = AnswerAssessment(
    lived=0,
    coherent=0,
    honest=0,
    original=0,
    consequential=0,
    evaded=True,
    contradiction=None,
    read="Passed. Nothing to weigh.",
    probe_next="They passed on this. Come back to the same ground from a different side.",
)


@dataclass
class InterviewConfig:
    name: str = "Friend"
    total_questions: int = 20
    panel: str = "full"  # "full" = four proposers and a chair, "lean" = chair only
    sessions_dir: str = "sessions"


@dataclass
class Result:
    """Everything the write-up produced, including what failed."""

    score: float
    band: str
    band_blurb: str
    verdict: Optional[Verdict]
    report: str
    path: str
    error: Optional[str] = None


def is_pass(answer: str) -> bool:
    return answer.strip().lower() in PASS_WORDS or not answer.strip()


def compose_question(
    exchanges: List[Exchange], probe_next: str, config: InterviewConfig
) -> Tuple[NextQuestion, str, Optional[str]]:
    """Ask the panel for the next question. Never raises.

    Returns the question, the reason that area was chosen, and the error text
    if the panel could not be reached - in which case the standing question for
    that area is used instead, because a fallback question beats a dead
    interview.
    """
    asked = len(exchanges)
    remaining = config.total_questions - asked
    dimension, reason = scoring.choose_next_dimension(exchanges, remaining)

    inputs = {
        "subject_name": config.name,
        "question_number": asked + 1,
        "total_questions": config.total_questions,
        "target_area": describe(dimension),
        "targeting_reason": reason,
        "probe_next": probe_next,
        "transcript": session.transcript_text(exchanges),
        "coverage": session.coverage_text(exchanges),
    }

    error: Optional[str] = None
    question: Optional[NextQuestion] = None
    try:
        panel = PanelCrew()
        crew = panel.crew() if config.panel == "full" else panel.lean_crew()
        question = crew.kickoff(inputs=inputs).pydantic
    except Exception as failure:  # noqa: BLE001 - never lose an interview to a bad call
        error = str(failure)

    if question is None:
        question = NextQuestion(
            dimension=dimension,
            question=DIMENSIONS_BY_KEY[dimension].fallback_question,
            why_this_question=reason,
            what_a_bluff_looks_like=DIMENSIONS_BY_KEY[dimension].borrowed_answer_sounds_like,
        )

    # The panel is asked to echo the area key back. If it invents one, keep the
    # area we actually chose, so the coverage map stays honest.
    if question.dimension not in DIMENSION_KEYS:
        question.dimension = dimension
    return question, reason, error


def assess(
    exchanges: List[Exchange], pending: NextQuestion, config: InterviewConfig
) -> Tuple[Optional[AnswerAssessment], float, Optional[str]]:
    """Mark the last answer in the list. Never raises.

    An answer that could not be marked comes back as None and is left out of
    the average later, rather than counted as a zero the person did not earn.
    """
    current = exchanges[-1]
    if not current.answer.strip():
        # A pass is a real answer to a question about your life, and is scored
        # as one. No model call needed.
        return PASSED.model_copy(), 0.0, None

    inputs = {
        "subject_name": config.name,
        "question": current.question,
        "answer": current.answer,
        "target_area": describe(current.dimension),
        "what_a_bluff_looks_like": pending.what_a_bluff_looks_like,
        "transcript": session.transcript_text(exchanges[:-1]),
    }
    try:
        assessor = AssessorCrew()
        crew = assessor.crew() if config.panel == "full" else assessor.lean_crew()
        assessment = crew.kickoff(inputs=inputs).pydantic
    except Exception as failure:  # noqa: BLE001
        return None, 0.0, str(failure)

    if assessment is None:
        return None, 0.0, "The assessor returned nothing usable."
    return assessment, scoring.score_answer(assessment), None


def finalise(exchanges: List[Exchange], config: InterviewConfig) -> Result:
    """Fix the score, get it explained, write the files. Never raises."""
    scored = [ex for ex in exchanges if ex.assessment is not None]
    score = scoring.overall_score(exchanges)
    if scored:
        band, blurb = scoring.band(score)
    else:
        # The assessor never ran. That is a broken interview, not a bad one, and
        # it would be dishonest to print a failing band for it.
        band = "No result"
        blurb = "Nothing was scored, so there is no verdict. The transcript is still here."

    weakest = scoring.weakest_moment(exchanges)
    weakest_text = (
        f"Q{weakest.number}: {weakest.question}\nTheir answer: {weakest.answer or '(passed)'}"
        if weakest
        else "No answer was scored."
    )
    found = scoring.contradictions(exchanges)

    verdict: Optional[Verdict] = None
    error: Optional[str] = None
    if scored:
        try:
            verdict = (
                VerdictCrew()
                .crew()
                .kickoff(
                    inputs={
                        "subject_name": config.name,
                        "transcript": session.transcript_text(exchanges),
                        "coverage": session.coverage_text(exchanges),
                        "contradiction_list": "\n".join(found) or "None recorded.",
                        "weakest_moment": weakest_text,
                        "score": score,
                        "band": band,
                        "band_blurb": blurb,
                    }
                )
                .pydantic
            )
        except Exception as failure:  # noqa: BLE001
            error = str(failure)

    report = session.render_report(config.name, exchanges, score, band, blurb, verdict)
    path = session.save_session(report, exchanges, config.sessions_dir)
    return Result(score, band, blurb, verdict, report, path, error)


@dataclass
class Interview:
    """One interview, held open between requests.

    The web front end needs to hand out a question, go away for an hour while
    somebody thinks about it on a train, and come back. So the state lives in
    an object rather than in the call stack of a loop.
    """

    config: InterviewConfig = field(default_factory=InterviewConfig)
    exchanges: List[Exchange] = field(default_factory=list)
    pending: Optional[NextQuestion] = None
    pending_reason: str = ""
    probe_next: str = OPENING_PROBE
    result: Optional[Result] = None
    last_error: Optional[str] = None

    @property
    def finished(self) -> bool:
        return len(self.exchanges) >= self.config.total_questions

    @property
    def answered(self) -> int:
        return len(self.exchanges)

    def ask(self) -> NextQuestion:
        """Get the next question ready. Safe to call twice - it will not
        replace a question that is already waiting to be answered."""
        if self.pending is None:
            self.pending, self.pending_reason, self.last_error = compose_question(
                self.exchanges, self.probe_next, self.config
            )
        return self.pending

    def answer(self, text: str) -> Exchange:
        """Record an answer to the waiting question and mark it."""
        if self.pending is None:
            raise RuntimeError("There is no question waiting to be answered.")
        pending = self.pending
        current = Exchange(
            number=len(self.exchanges) + 1,
            dimension=pending.dimension,
            question=pending.question,
            answer="" if is_pass(text) else text.strip(),
        )
        self.exchanges.append(current)
        current.assessment, current.score, self.last_error = assess(
            self.exchanges, pending, self.config
        )
        if current.assessment is not None:
            self.probe_next = current.assessment.probe_next
        self.pending = None
        return current

    def finish(self) -> Result:
        if self.result is None:
            self.result = finalise(self.exchanges, self.config)
        return self.result

    # ------------------------------------------------------------ storage

    def to_dict(self) -> dict:
        """A snapshot that can be written to disk and picked up later.

        The web front end saves this after every step, so an interview
        survives a server restart, a closed browser tab, or a phone that went
        to sleep on question eleven.
        """
        result = None
        if self.result is not None:
            result = {
                "score": self.result.score,
                "band": self.result.band,
                "band_blurb": self.result.band_blurb,
                "verdict": self.result.verdict.model_dump() if self.result.verdict else None,
                "report": self.result.report,
                "path": self.result.path,
                "error": self.result.error,
            }
        return {
            "config": {
                "name": self.config.name,
                "total_questions": self.config.total_questions,
                "panel": self.config.panel,
                "sessions_dir": self.config.sessions_dir,
            },
            "exchanges": [ex.model_dump() for ex in self.exchanges],
            "pending": self.pending.model_dump() if self.pending else None,
            "pending_reason": self.pending_reason,
            "probe_next": self.probe_next,
            "result": result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Interview":
        result = None
        if data.get("result"):
            saved = data["result"]
            result = Result(
                score=saved["score"],
                band=saved["band"],
                band_blurb=saved["band_blurb"],
                verdict=Verdict(**saved["verdict"]) if saved.get("verdict") else None,
                report=saved["report"],
                path=saved["path"],
                error=saved.get("error"),
            )
        return cls(
            config=InterviewConfig(**data["config"]),
            exchanges=[Exchange(**ex) for ex in data["exchanges"]],
            pending=NextQuestion(**data["pending"]) if data.get("pending") else None,
            pending_reason=data.get("pending_reason", ""),
            probe_next=data.get("probe_next", OPENING_PROBE),
            result=result,
        )
