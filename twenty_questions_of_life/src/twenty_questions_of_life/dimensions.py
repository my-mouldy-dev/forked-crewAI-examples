"""The territory the interview has to cover.

Twenty questions is not many. To avoid twenty variations of the same question,
the interview walks a fixed map of the areas a person has to have some grip on
before "I understand life" means anything. Each entry says what the area is,
what a borrowed answer usually sounds like, and what a lived one usually
sounds like. The panel gets this text verbatim when it writes a question.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Dimension:
    key: str
    title: str
    probe: str
    borrowed_answer_sounds_like: str
    lived_answer_sounds_like: str
    # Used only if the panel cannot be reached. A plain question is better than
    # a crashed interview.
    fallback_question: str


DIMENSIONS: List[Dimension] = [
    Dimension(
        key="mortality",
        title="Death and running out of time",
        probe="Whether they have actually reckoned with their own ending, or only agreed that death exists.",
        borrowed_answer_sounds_like="'Death gives life meaning.' Said calmly, with no cost attached.",
        lived_answer_sounds_like="A specific moment when the clock became real, and what they changed the week after.",
        fallback_question="When did it last become real to you that you are going to die, and what did you do differently that week?",
    ),
    Dimension(
        key="meaning",
        title="Where meaning comes from",
        probe="Whether meaning is something they make and maintain, or a slogan they inherited.",
        borrowed_answer_sounds_like="'Meaning comes from within' or 'from helping others', with no example.",
        lived_answer_sounds_like="A description of what stopped feeling meaningful and what they did about it.",
        fallback_question="What used to feel meaningful to you and stopped, and what did you do about it?",
    ),
    Dimension(
        key="suffering",
        title="Pain, loss and things that do not resolve",
        probe="Whether they can hold a loss that had no lesson in it.",
        borrowed_answer_sounds_like="'Everything happens for a reason.' Suffering as a growth programme.",
        lived_answer_sounds_like="Naming a loss they never got anything useful out of, and how they carry it anyway.",
        fallback_question="Tell me about a loss you never got anything useful out of. How do you carry it?",
    ),
    Dimension(
        key="agency",
        title="What is theirs to control",
        probe="Whether they can draw the line between effort and outcome without hiding behind either.",
        borrowed_answer_sounds_like="'Control what you can control', recited, then a story where they controlled nothing.",
        lived_answer_sounds_like="A decision where they owned their part precisely, no more and no less.",
        fallback_question="Describe a bad outcome where you can say exactly which part was yours.",
    ),
    Dimension(
        key="relationships",
        title="Other people, love and obligation",
        probe="Whether they understand being known, and the cost of it.",
        borrowed_answer_sounds_like="'Relationships are everything', listed as a value, not a practice.",
        lived_answer_sounds_like="Something they gave up for a person, or a repair they made after doing damage.",
        fallback_question="What have you given up for one specific person, and would you do it again?",
    ),
    Dimension(
        key="identity",
        title="Being a different person over time",
        probe="Whether they can face that the person they were is partly gone.",
        borrowed_answer_sounds_like="'I have grown so much' with no account of what was lost in the change.",
        lived_answer_sounds_like="A belief they held hard, dropped, and can explain why they were wrong.",
        fallback_question="What did you believe strongly five years ago that you now think was wrong, and what convinced you?",
    ),
    Dimension(
        key="self_deception",
        title="The story they tell about themselves",
        probe="Whether they can catch themselves flattering themselves, live, in this interview.",
        borrowed_answer_sounds_like="'I am very self aware.' Insight described, never demonstrated.",
        lived_answer_sounds_like="Naming a comfortable belief they hold that is probably not true, and why they keep it.",
        fallback_question="Name a comfortable belief you hold about yourself that is probably not true. Why do you keep it?",
    ),
    Dimension(
        key="ethics",
        title="What they owe other people",
        probe="Whether their moral line survives contact with cost to themselves.",
        borrowed_answer_sounds_like="Universal principles stated in the abstract, with no case that cost them.",
        lived_answer_sounds_like="A time doing right was expensive, or a time they took the cheap option and know it.",
        fallback_question="When did doing the right thing cost you something real, or when did you take the cheap way out?",
    ),
    Dimension(
        key="work",
        title="Work and what they are building",
        probe="Whether their work is theirs or an inherited script about status.",
        borrowed_answer_sounds_like="'Do what you love.' Purpose as a job description.",
        lived_answer_sounds_like="What they would still do if nobody ever saw it, and what they do only for money, said plainly.",
        fallback_question="What part of your work would you keep doing if nobody ever knew you did it, and what part is only for money?",
    ),
    Dimension(
        key="ordinary_joy",
        title="Ordinary days and small pleasures",
        probe="Whether they can find life in an unremarkable Tuesday, without needing it to signify.",
        borrowed_answer_sounds_like="'Be present.' Gratitude as a technique.",
        lived_answer_sounds_like="A concrete, unglamorous thing that reliably makes their day better, described without justification.",
        fallback_question="What small, unimpressive thing reliably makes your day better? Do not justify it.",
    ),
    Dimension(
        key="uncertainty",
        title="Not knowing",
        probe="Whether they can sit in an open question without closing it prematurely.",
        borrowed_answer_sounds_like="'Nobody really knows anything', used to end the conversation rather than open it.",
        lived_answer_sounds_like="A question they genuinely have not settled, held with real discomfort.",
        fallback_question="What question about your own life have you genuinely not settled, and how long has it been open?",
    ),
    Dimension(
        key="consistency",
        title="Whether their life matches their answers",
        probe="Whether the calendar and the bank statement agree with the philosophy.",
        borrowed_answer_sounds_like="Stated values that nothing in their week reflects.",
        lived_answer_sounds_like="An honest gap between what they say matters and where their time actually goes.",
        fallback_question="Where does your time actually go, and which of your stated values does that not match?",
    ),
]

DIMENSIONS_BY_KEY: Dict[str, Dimension] = {d.key: d for d in DIMENSIONS}
DIMENSION_KEYS: List[str] = [d.key for d in DIMENSIONS]


def describe(key: str) -> str:
    """One block of plain text about a dimension, for a prompt."""
    d = DIMENSIONS_BY_KEY[key]
    return (
        f"Area: {d.title} (key: {d.key})\n"
        f"What we are testing: {d.probe}\n"
        f"A borrowed answer sounds like: {d.borrowed_answer_sounds_like}\n"
        f"A lived answer sounds like: {d.lived_answer_sounds_like}"
    )


def describe_all() -> str:
    return "\n\n".join(describe(k) for k in DIMENSION_KEYS)
