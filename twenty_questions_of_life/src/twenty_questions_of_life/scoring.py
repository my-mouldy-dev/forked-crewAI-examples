"""The parts of the judgement that must not be up to the model.

Language models are agreeable. If you let one both interview you and grade
you, it will tell you that you understand life. So the model only ever does
two narrow jobs: score a single answer on five named criteria, and later
explain a result it did not choose. Everything below - how those criteria
combine, what counts as coverage, which area gets probed next, and the final
band - is fixed arithmetic that runs the same way every time.
"""

from typing import Dict, List, Optional, Tuple

from .dimensions import DIMENSION_KEYS, DIMENSIONS_BY_KEY
from .models import AnswerAssessment, Exchange

# What each criterion is worth. Honesty counts most: it is the one you cannot
# fake upward by being well read. Originality counts least: plenty of true
# things about life were first said by somebody else.
WEIGHTS: Dict[str, float] = {
    "lived": 1.2,
    "coherent": 1.0,
    "honest": 1.3,
    "original": 0.9,
    "consequential": 1.1,
}

EVASION_PENALTY = 0.75
CONTRADICTION_PENALTY = 0.5

# Missing a whole area of life is a real gap, but a small one next to answering
# badly. Capped so that a short interview cannot be dragged to zero by breadth.
UNCOVERED_DIMENSION_PENALTY = 0.15
MAX_COVERAGE_PENALTY = 1.0

MAX_VISITS_PER_DIMENSION = 3

BANDS: List[Tuple[float, str, str]] = [
    (4.2, "Lived it, and knows it",
     "You are not reciting. The answers cost you something and they agree with each other."),
    (3.4, "Real understanding, unevenly held",
     "You have done the work in some areas and are still borrowing in others."),
    (2.6, "You have thought about it. It is still mostly theory",
     "The ideas are sound. Your own life is not yet evidence for them."),
    (1.6, "Borrowed answers",
     "You know what a good answer sounds like. That is a different skill."),
    (0.0, "Not yet - this was a performance",
     "You answered the questions you wished had been asked."),
]


def score_answer(assessment: AnswerAssessment) -> float:
    """Turn one assessment into a single 0-5 number."""
    raw = sum(WEIGHTS[k] * getattr(assessment, k) for k in WEIGHTS)
    score = raw / sum(WEIGHTS.values())
    if assessment.evaded:
        score -= EVASION_PENALTY
    if assessment.contradiction:
        score -= CONTRADICTION_PENALTY
    return round(max(0.0, min(5.0, score)), 2)


def coverage(exchanges: List[Exchange]) -> Dict[str, List[float]]:
    """Scores so far, grouped by area of life."""
    out: Dict[str, List[float]] = {key: [] for key in DIMENSION_KEYS}
    for ex in exchanges:
        if ex.dimension in out and ex.assessment is not None:
            out[ex.dimension].append(ex.score)
    return out


def dimension_averages(exchanges: List[Exchange]) -> Dict[str, float]:
    return {
        key: round(sum(scores) / len(scores), 2)
        for key, scores in coverage(exchanges).items()
        if scores
    }


def uncovered(exchanges: List[Exchange]) -> List[str]:
    covered = {ex.dimension for ex in exchanges}
    return [key for key in DIMENSION_KEYS if key not in covered]


def choose_next_dimension(
    exchanges: List[Exchange], questions_remaining: int
) -> Tuple[str, str]:
    """Pick the area for the next question, and say why in one line.

    Breadth first: an interview that never asks about death or about other
    people has not tested whether you understand life. Once every area has
    been touched, spend what is left on the weakest answers and on anything
    the person dodged, because that is where the borrowed material is.
    """
    gaps = uncovered(exchanges)
    if gaps:
        # Keep enough questions in hand to touch every remaining area, but if
        # the last answer was a dodge, chase it instead of moving on politely.
        last = exchanges[-1] if exchanges else None
        must_cover = len(gaps) >= questions_remaining
        # Two in a row on one area is pressure. Three is a grudge.
        already_pressed = (
            len(exchanges) >= 2 and exchanges[-2].dimension == exchanges[-1].dimension
        )
        if last is not None and last.assessment is not None and not must_cover and not already_pressed:
            if last.assessment.evaded or last.score < 2.0:
                return (
                    last.dimension,
                    "The last answer went soft. Ask again in the same area, harder.",
                )
        return gaps[0], f"No question has touched {DIMENSIONS_BY_KEY[gaps[0]].title.lower()} yet."

    averages = dimension_averages(exchanges)
    visits = {key: len(v) for key, v in coverage(exchanges).items()}
    eligible = {
        key: avg
        for key, avg in averages.items()
        if visits.get(key, 0) < MAX_VISITS_PER_DIMENSION
    }
    if not eligible:
        eligible = averages
    weakest = min(eligible, key=lambda k: (eligible[k], DIMENSION_KEYS.index(k)))
    return (
        weakest,
        f"Weakest area so far ({eligible[weakest]}/5). Go back and press on it.",
    )


def overall_score(exchanges: List[Exchange]) -> float:
    scored = [ex.score for ex in exchanges if ex.assessment is not None]
    if not scored:
        return 0.0
    base = sum(scored) / len(scored)
    penalty = min(len(uncovered(exchanges)) * UNCOVERED_DIMENSION_PENALTY, MAX_COVERAGE_PENALTY)
    return round(max(0.0, base - penalty), 2)


def band(score: float) -> Tuple[str, str]:
    for threshold, name, blurb in BANDS:
        if score >= threshold:
            return name, blurb
    return BANDS[-1][1], BANDS[-1][2]


def weakest_moment(exchanges: List[Exchange]) -> Optional[Exchange]:
    scored = [ex for ex in exchanges if ex.assessment is not None]
    if not scored:
        return None
    return min(scored, key=lambda ex: ex.score)


def contradictions(exchanges: List[Exchange]) -> List[str]:
    return [
        f"Q{ex.number} ({ex.dimension}): {ex.assessment.contradiction}"
        for ex in exchanges
        if ex.assessment is not None and ex.assessment.contradiction
    ]
