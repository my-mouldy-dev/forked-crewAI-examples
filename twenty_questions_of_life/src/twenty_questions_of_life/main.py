"""Twenty Questions of Life - the terminal front end.

A crewAI Flow that interviews you. Nothing is scripted: after every answer, a
panel of four agents looks at everything you have said so far, decides which
part of life you have not been tested on - or have been tested on and dodged -
and writes the next question for it. After twenty, the arithmetic decides the
result and a second crew has to explain it without softening it.

Run it with:  crewai flow kickoff
The same interview over a web page, for a phone:  python -m twenty_questions_of_life.web
"""

import argparse
import os
import sys
from typing import List, Optional

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from twenty_questions_of_life import session
from twenty_questions_of_life.engine import Interview, InterviewConfig
from twenty_questions_of_life.models import Exchange


class InterviewState(BaseModel):
    """Kept so `crewai flow plot` has something to draw. The interview itself
    lives in engine.Interview, which the web front end shares."""

    subject_name: str = "Friend"
    total_questions: int = 20
    asked: int = 0
    exchanges: List[Exchange] = []
    score: float = 0.0
    band: str = ""


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
        self.interview = Interview(config=self.config)
        self.state.subject_name = self.config.name
        self.state.total_questions = self.config.total_questions
        self._opened = False

    # ------------------------------------------------------------------ ask

    @start("ask_next")
    def compose_question(self):
        if not self._opened:
            session.opening(self.config.total_questions, self.config.name)
            self._opened = True

        print(f"  ...panel is writing question {self.interview.answered + 1}\n")
        self.interview.ask()
        if self.interview.last_error:
            print(
                f"  (panel unavailable: {self.interview.last_error}. "
                "Using the standing question.)\n"
            )

    # --------------------------------------------------------------- answer

    @listen(compose_question)
    def take_answer(self):
        pending = self.interview.pending
        number = self.interview.answered + 1
        session.put_question(
            number,
            self.config.total_questions,
            pending.dimension,
            pending.question,
            pending.why_this_question,
        )
        self._answer_text = self.answers.get(number)

    # --------------------------------------------------------------- assess

    @listen(take_answer)
    def assess_answer(self):
        current = self.interview.answer(self._answer_text)
        if current.assessment is None:
            print(
                f"  (assessor unavailable: {self.interview.last_error}. "
                "This answer is not scored.)\n"
            )
        else:
            session.show_read(current.score, current.assessment.read)
        self.state.asked = self.interview.answered
        self.state.exchanges = self.interview.exchanges

    @router(assess_answer)
    def more_or_done(self):
        return "wrap_up" if self.interview.finished else "ask_next"

    # -------------------------------------------------------------- verdict

    @listen("wrap_up")
    def deliver_verdict(self):
        print(session.RULE)
        if any(ex.assessment is not None for ex in self.interview.exchanges):
            print("  ...the panel is writing up\n")
        else:
            print("  Nothing was scored, so there is nothing to write up.\n")

        result = self.interview.finish()
        self.state.score, self.state.band = result.score, result.band
        if result.error:
            print(f"  (write-up unavailable: {result.error}. The score and transcript still stand.)\n")

        print(session.RULE)
        print(f"  Score: {result.score} / 5   -   {result.band}")
        print(session.RULE)
        if result.verdict:
            print(session.wrap(result.verdict.headline))
            print()
            print(session.wrap(f"The question you dodged: {result.verdict.the_question_you_dodged}"))
            print()
            print(session.wrap(f"What would change this: {result.verdict.what_would_change_this}"))
            print()
        print(f"  Full write-up and transcript: {result.path}")
        print(session.RULE)
        return result.report


def apply_model_env() -> None:
    """MODEL is the friendlier name; crewAI reads OPENAI_MODEL_NAME."""
    if os.environ.get("MODEL") and not os.environ.get("OPENAI_MODEL_NAME"):
        os.environ["OPENAI_MODEL_NAME"] = os.environ["MODEL"]


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
    apply_model_env()
    config, answers = _parse_args()
    TwentyQuestionsFlow(config=config, answers=answers).kickoff()


def plot():
    TwentyQuestionsFlow().plot()


if __name__ == "__main__":
    kickoff()
