"""Shared data shapes.

These are plain pydantic models with no crewAI import, so the scoring and
reporting code can be used (and tested) without an LLM anywhere near it.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class NextQuestion(BaseModel):
    """What the panel hands back when asked for the next question."""

    dimension: str = Field(description="Key of the area this question probes")
    question: str = Field(description="The question, as it will be read out")
    why_this_question: str = Field(description="Why this question, now, for this person")
    what_a_bluff_looks_like: str = Field(
        description="The shape of the answer that would sound good and mean nothing"
    )


class AnswerAssessment(BaseModel):
    """What the assessor returns after each answer. All scores are 0-5."""

    lived: int = Field(description="Grounded in their own experience, not in the abstract")
    coherent: int = Field(description="Holds together, and holds with their earlier answers")
    honest: int = Field(description="Admits cost, doubt and the unflattering parts")
    original: int = Field(description="Their own thinking rather than a quoted platitude")
    consequential: int = Field(description="Changes what they actually do")
    evaded: bool = Field(description="True if they answered a different, easier question")
    contradiction: Optional[str] = Field(
        default=None, description="Conflict with an earlier answer, or null"
    )
    read: str = Field(description="One plain sentence on what this answer shows")
    probe_next: str = Field(description="The follow-up pressure the panel should apply next")


class Exchange(BaseModel):
    """One question, one answer, one assessment."""

    number: int
    dimension: str
    question: str
    answer: str
    assessment: Optional[AnswerAssessment] = None
    score: float = 0.0


class Verdict(BaseModel):
    """The closing judgement, written after the numbers are already fixed."""

    headline: str = Field(description="One sentence, plain English, no hedging")
    what_you_understand: List[str] = Field(description="Things they have genuinely got hold of")
    where_you_are_bluffing: List[str] = Field(
        description="Where the answer was borrowed or performed"
    )
    contradictions: List[str] = Field(
        description="Places their answers do not agree with each other"
    )
    the_question_you_dodged: str = Field(description="The one they most avoided, and how")
    what_would_change_this: str = Field(
        description="What they would have to live, not read, to score higher"
    )
