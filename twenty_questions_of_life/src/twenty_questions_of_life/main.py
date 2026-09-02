"""Twenty Questions of Life.

A crewAI Flow that interviews you. Nothing is scripted: after every answer, a
panel of four agents looks at everything you have said so far, decides which
part of life you have not been tested on - or have been tested on and dodged -
and writes the next question for it. After twenty, the arithmetic decides the
result and a second crew has to explain it without softening it.

Run it with:  crewai flow kickoff
"""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from twenty_questions_of_life import scoring, session
from twenty_questions_of_life.crews.assessor_crew.assessor_crew import AssessorCrew
from twenty_questions_of_life.crews.panel_crew.panel_crew import PanelCrew
from twenty_questions_of_life.crews.verdict_crew.verdict_crew import VerdictCrew
from twenty_questions_of_life.dimensions import DIMENSION_KEYS, DIMENSIONS_BY_KEY, describe
from twenty_questions_of_life.models import AnswerAssessment, Exchange, NextQuestion, Verdict


@dataclass
class InterviewConfig:
    name: str = "Friend"
    total_questions: int = 20
    panel: str = "full"  # "full" = four proposers and a chair, "lean" = chair only
    sessions_dir: str = "sessions"


class InterviewState(BaseModel):
    subject_name: str = "Friend"
    total_questions: int = 20
    exchanges: List[Exchange] = []
    pending: Optional[NextQuestion] = None
    pending_reason: str = ""
    probe_next: str = "Nothing yet. Open where you like."
    score: float = 0.0
    band: str = ""
    band_blurb: str = ""
    verdict: Optional[Verdict] = None


class TwentyQuestionsFlow(Flow[InterviewState]):
    """One question at a time, each one chosen after the last answer."""

    def __init__(
        self,
        config: Optional[InterviewConfig] = None,
        answers: Optional[session.AnswerSource] = None,
    ):
        super().__init__()
        self.config = config or InterviewConfig()
        self.answers = answers or session.AnswerSource()
        self.state.subject_name = self.config.name
        self.state.total_questions = self.config.total_questions
        self._opened = False

    # ------------------------------------------------------------------ ask

    @start("ask_next")
    def compose_question(self):
        if not self._opened:
            session.opening(self.config.total_questions, self.config.name)
            self._opened = True

        asked = len(self.state.exchanges)
        remaining = self.config.total_questions - asked
        dimension, reason = scoring.choose_next_dimension(self.state.exchanges, remaining)
        self.state.pending_reason = reason

        inputs = {
            "subject_name": self.state.subject_name,
            "question_number": asked + 1,
            "total_questions": self.config.total_questions,
            "target_area": describe(dimension),
            "targeting_reason": reason,
            "probe_next": self.state.probe_next,
            "transcript": session.transcript_text(self.state.exchanges),
            "coverage": session.coverage_text(self.state.exchanges),
        }

        print(f"  ...panel is writing question {asked + 1}\n")
        try:
            panel = PanelCrew()
            crew = panel.crew() if self.config.panel == "full" else panel.lean_crew()
            question = crew.kickoff(inputs=inputs).pydantic
        except Exception as error:  # noqa: BLE001 - never lose an interview to a bad call
            print(f"  (panel unavailable: {error}. Using the standing question.)\n")
            question = None

        if question is None:
            question = NextQuestion(
                dimension=dimension,
                question=DIMENSIONS_BY_KEY[dimension].fallback_question,
                why_this_question=reason,
                what_a_bluff_looks_like=DIMENSIONS_BY_KEY[dimension].borrowed_answer_sounds_like,
            )

        # The panel is asked to echo the area key back. If it invents one, keep
        # the area we actually chose, so the coverage map stays honest.
        if question.dimension not in DIMENSION_KEYS:
            question.dimension = dimension
        self.state.pending = question

    # --------------------------------------------------------------- answer

    @listen(compose_question)
    def take_answer(self):
        pending = self.state.pending
        number = len(self.state.exchanges) + 1
        session.put_question(
            number,
            self.config.total_questions,
            pending.dimension,
            pending.question,
            pending.why_this_question,
        )
        answer = self.answers.get(number)
        if answer.strip().lower() in {"pass", "skip", "no comment"}:
            answer = ""
        self.state.exchanges.append(
            Exchange(
                number=number,
                dimension=pending.dimension,
                question=pending.question,
                answer=answer,
            )
        )

    # --------------------------------------------------------------- assess

    @listen(take_answer)
    def assess_answer(self):
        current = self.state.exchanges[-1]
        pending = self.state.pending

        if not current.answer.strip():
            # A pass is a real answer to a question about your life, and it is
            # scored as one. No LLM call needed.
            current.assessment = AnswerAssessment(
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
            current.score = 0.0
        else:
            inputs = {
                "subject_name": self.state.subject_name,
                "question": current.question,
                "answer": current.answer,
                "target_area": describe(current.dimension),
                "what_a_bluff_looks_like": pending.what_a_bluff_looks_like,
                "transcript": session.transcript_text(self.state.exchanges[:-1]),
            }
            try:
                assessor = AssessorCrew()
                crew = assessor.crew() if self.config.panel == "full" else assessor.lean_crew()
                current.assessment = crew.kickoff(inputs=inputs).pydantic
            except Exception as error:  # noqa: BLE001
                print(f"  (assessor unavailable: {error}. This answer is not scored.)\n")
                current.assessment = None

            if current.assessment is not None:
                current.score = scoring.score_answer(current.assessment)

        if current.assessment is not None:
            self.state.probe_next = current.assessment.probe_next
            session.show_read(current.score, current.assessment.read)

    @router(assess_answer)
    def more_or_done(self):
        if len(self.state.exchanges) >= self.config.total_questions:
            return "wrap_up"
        return "ask_next"

    # -------------------------------------------------------------- verdict

    @listen("wrap_up")
    def deliver_verdict(self):
        exchanges = self.state.exchanges
        scored = [ex for ex in exchanges if ex.assessment is not None]
        self.state.score = scoring.overall_score(exchanges)
        if scored:
            self.state.band, self.state.band_blurb = scoring.band(self.state.score)
        else:
            # The assessor never ran. That is a broken interview, not a bad one,
            # and it would be dishonest to print a failing band for it.
            self.state.band = "No result"
            self.state.band_blurb = (
                "Nothing was scored, so there is no verdict. The transcript is still here."
            )

        weakest = scoring.weakest_moment(exchanges)
        weakest_text = (
            f"Q{weakest.number}: {weakest.question}\nTheir answer: {weakest.answer or '(passed)'}"
            if weakest
            else "No answer was scored."
        )
        found = scoring.contradictions(exchanges)

        print(session.RULE)
        if not scored:
            print("  Nothing was scored, so there is nothing to write up.\n")
        else:
            print("  ...the panel is writing up\n")
            try:
                self.state.verdict = (
                    VerdictCrew()
                    .crew()
                    .kickoff(
                        inputs={
                            "subject_name": self.state.subject_name,
                            "transcript": session.transcript_text(exchanges),
                            "coverage": session.coverage_text(exchanges),
                            "contradiction_list": "\n".join(found) or "None recorded.",
                            "weakest_moment": weakest_text,
                            "score": self.state.score,
                            "band": self.state.band,
                            "band_blurb": self.state.band_blurb,
                        }
                    )
                    .pydantic
                )
            except Exception as error:  # noqa: BLE001
                print(f"  (write-up unavailable: {error}. The score and transcript still stand.)\n")

        report = session.render_report(
            self.state.subject_name,
            exchanges,
            self.state.score,
            self.state.band,
            self.state.band_blurb,
            self.state.verdict,
        )
        path = session.save_session(report, exchanges, self.config.sessions_dir)

        print(session.RULE)
        print(f"  Score: {self.state.score} / 5   -   {self.state.band}")
        print(session.RULE)
        if self.state.verdict:
            print(session.wrap(self.state.verdict.headline))
            print()
            print(session.wrap(f"The question you dodged: {self.state.verdict.the_question_you_dodged}"))
            print()
            print(session.wrap(f"What would change this: {self.state.verdict.what_would_change_this}"))
            print()
        print(f"  Full write-up and transcript: {path}")
        print(session.RULE)
        return report


def _parse_args(argv: Optional[List[str]] = None) -> tuple:
    parser = argparse.ArgumentParser(description="Twenty questions about whether you understand life.")
    parser.add_argument("--name", default="Friend", help="What the panel should call you")
    parser.add_argument("--questions", type=int, default=20, help="How many questions (default 20)")
    parser.add_argument(
        "--panel",
        choices=["full", "lean"],
        default="full",
        help="full: four proposers and a chair per question. lean: chair only, about a fifth of the cost",
    )
    parser.add_argument(
        "--answers",
        help="File of prepared answers (one per line, or a JSON list) instead of typing them",
    )
    parser.add_argument("--sessions-dir", default="sessions", help="Where to write the report")
    # parse_known_args so the crewai CLI can pass its own flags through
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    config = InterviewConfig(
        name=args.name,
        total_questions=max(1, args.questions),
        panel=args.panel,
        sessions_dir=args.sessions_dir,
    )
    answers = session.AnswerSource.from_file(args.answers) if args.answers else session.AnswerSource()
    return config, answers


def kickoff():
    if os.environ.get("MODEL") and not os.environ.get("OPENAI_MODEL_NAME"):
        os.environ["OPENAI_MODEL_NAME"] = os.environ["MODEL"]
    config, answers = _parse_args()
    TwentyQuestionsFlow(config=config, answers=answers).kickoff()


def plot():
    TwentyQuestionsFlow().plot()


if __name__ == "__main__":
    kickoff()
