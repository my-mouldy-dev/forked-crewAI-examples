"""Tests for the parts of the judgement that do not involve a model.

Run from the project root:  python -m unittest discover tests
These need pydantic only - no crewAI, no API key, no network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from twenty_questions_of_life import scoring, session  # noqa: E402
from twenty_questions_of_life.dimensions import DIMENSION_KEYS  # noqa: E402
from twenty_questions_of_life.models import AnswerAssessment, Exchange  # noqa: E402


def assessment(value=4, **overrides):
    fields = dict(
        lived=value,
        coherent=value,
        honest=value,
        original=value,
        consequential=value,
        evaded=False,
        contradiction=None,
        read="a read",
        probe_next="press harder",
    )
    fields.update(overrides)
    return AnswerAssessment(**fields)


def exchange(number, dimension, value=4, **overrides):
    a = assessment(value, **overrides)
    return Exchange(
        number=number,
        dimension=dimension,
        question=f"question {number}",
        answer="an answer",
        assessment=a,
        score=scoring.score_answer(a),
    )


class ScoreAnAnswer(unittest.TestCase):
    def test_flat_scores_come_back_unchanged(self):
        self.assertEqual(scoring.score_answer(assessment(0)), 0.0)
        self.assertEqual(scoring.score_answer(assessment(5)), 5.0)
        self.assertEqual(scoring.score_answer(assessment(3)), 3.0)

    def test_honesty_outweighs_originality(self):
        honest = scoring.score_answer(assessment(3, honest=5, original=1))
        quotable = scoring.score_answer(assessment(3, honest=1, original=5))
        self.assertGreater(honest, quotable)

    def test_evasion_and_contradiction_both_cost(self):
        base = scoring.score_answer(assessment(4))
        evaded = scoring.score_answer(assessment(4, evaded=True))
        clashed = scoring.score_answer(assessment(4, contradiction="clashes with Q2"))
        self.assertAlmostEqual(base - evaded, scoring.EVASION_PENALTY, places=2)
        self.assertAlmostEqual(base - clashed, scoring.CONTRADICTION_PENALTY, places=2)

    def test_penalties_cannot_push_below_zero(self):
        self.assertEqual(
            scoring.score_answer(assessment(0, evaded=True, contradiction="x")), 0.0
        )


class ChooseTheNextArea(unittest.TestCase):
    def test_first_question_opens_on_the_first_area(self):
        area, why = scoring.choose_next_dimension([], questions_remaining=20)
        self.assertEqual(area, DIMENSION_KEYS[0])
        self.assertIn("No question has touched", why)

    def test_a_weak_answer_gets_pressed_again(self):
        history = [exchange(1, "mortality", value=1)]
        area, why = scoring.choose_next_dimension(history, questions_remaining=19)
        self.assertEqual(area, "mortality")
        self.assertIn("went soft", why)

    def test_pressing_stops_after_two_in_a_row(self):
        history = [exchange(1, "mortality", value=1), exchange(2, "mortality", value=1)]
        area, _ = scoring.choose_next_dimension(history, questions_remaining=18)
        self.assertNotEqual(area, "mortality")

    def test_breadth_wins_when_questions_are_running_out(self):
        # One question left, one area never asked about: cover it rather than
        # go back and press on a bad answer.
        history = [exchange(i + 1, key, value=1) for i, key in enumerate(DIMENSION_KEYS[:-1])]
        area, _ = scoring.choose_next_dimension(history, questions_remaining=1)
        self.assertEqual(area, DIMENSION_KEYS[-1])

    def test_once_everything_is_covered_the_weakest_area_is_revisited(self):
        history = [exchange(i + 1, key, value=4) for i, key in enumerate(DIMENSION_KEYS)]
        history[5] = exchange(6, DIMENSION_KEYS[5], value=1)
        history.append(exchange(13, DIMENSION_KEYS[0], value=4))  # break the press rule
        area, why = scoring.choose_next_dimension(history, questions_remaining=7)
        self.assertEqual(area, DIMENSION_KEYS[5])
        self.assertIn("Weakest area", why)

    def test_no_area_is_asked_more_than_three_times(self):
        history = [exchange(i + 1, key, value=4) for i, key in enumerate(DIMENSION_KEYS)]
        weak = DIMENSION_KEYS[3]
        for n in range(3):
            history.append(exchange(20 + n, weak, value=0))
            history.append(exchange(30 + n, DIMENSION_KEYS[0], value=5))
        area, _ = scoring.choose_next_dimension(history, questions_remaining=4)
        self.assertNotEqual(area, weak)


class TheFinalNumber(unittest.TestCase):
    def test_missing_areas_cost_something_but_not_everything(self):
        history = [exchange(1, "mortality", value=5)]
        # Eleven areas untouched, capped at the maximum coverage penalty.
        self.assertEqual(scoring.overall_score(history), 5.0 - scoring.MAX_COVERAGE_PENALTY)

    def test_full_coverage_carries_no_penalty(self):
        history = [exchange(i + 1, key, value=3) for i, key in enumerate(DIMENSION_KEYS)]
        self.assertEqual(scoring.overall_score(history), 3.0)

    def test_unscored_answers_are_left_out_rather_than_counted_as_zero(self):
        history = [exchange(i + 1, key, value=4) for i, key in enumerate(DIMENSION_KEYS)]
        history.append(
            Exchange(number=13, dimension="mortality", question="q", answer="a", assessment=None)
        )
        self.assertEqual(scoring.overall_score(history), 4.0)

    def test_bands_run_from_top_to_bottom(self):
        self.assertEqual(scoring.band(5.0)[0], scoring.BANDS[0][1])
        self.assertEqual(scoring.band(0.0)[0], scoring.BANDS[-1][1])
        self.assertEqual(scoring.band(4.2)[0], scoring.BANDS[0][1])
        self.assertEqual(scoring.band(4.19)[0], scoring.BANDS[1][1])

    def test_contradictions_are_collected_with_their_question_numbers(self):
        history = [
            exchange(1, "mortality"),
            exchange(2, "meaning", contradiction="clashes with Q1"),
        ]
        found = scoring.contradictions(history)
        self.assertEqual(len(found), 1)
        self.assertIn("Q2", found[0])

    def test_the_weakest_moment_is_the_lowest_scoring_answer(self):
        history = [exchange(1, "mortality", value=4), exchange(2, "meaning", value=1)]
        self.assertEqual(scoring.weakest_moment(history).number, 2)


class WritingItUp(unittest.TestCase):
    def test_the_report_holds_the_score_the_band_and_the_transcript(self):
        history = [exchange(i + 1, key, value=3) for i, key in enumerate(DIMENSION_KEYS)]
        score = scoring.overall_score(history)
        name, blurb = scoring.band(score)
        report = session.render_report("Tester", history, score, name, blurb, None)
        self.assertIn("**Score:** 3.0 / 5", report)
        self.assertIn(name, report)
        self.assertIn("question 12", report)
        self.assertIn("| Area | Times asked | Average |", report)

    def test_a_pass_shows_as_a_pass(self):
        skipped = Exchange(number=1, dimension="mortality", question="q", answer="")
        report = session.render_report("Tester", [skipped], 0.0, "band", "blurb", None)
        self.assertIn("(passed)", report)

    def test_prepared_answers_are_served_in_order_and_then_run_out(self):
        source = session.AnswerSource(prepared=["first", "second"])
        self.assertEqual(source.get(1), "first")
        self.assertEqual(source.get(2), "second")
        self.assertEqual(source.get(3), "")

    def test_the_transcript_for_prompts_carries_the_panel_notes(self):
        history = [exchange(1, "mortality", value=2, evaded=True)]
        text = session.transcript_text(history)
        self.assertIn("Q1 [mortality]", text)
        self.assertIn("evaded", text)


if __name__ == "__main__":
    unittest.main()
