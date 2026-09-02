"""Tests for the web front end, with the panel stubbed out.

No API key, no network, no model calls: the three crews are replaced with fakes
so what is being tested is the state machine, the locking, the persistence and
the token check - the parts that break on a phone.

Run from the project root:  python -m unittest discover tests
Skipped automatically if crewAI or FastAPI is not installed.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

HAVE_WEB = all(importlib.util.find_spec(name) for name in ("crewai", "fastapi", "httpx"))


def fake_crews(module):
    """Point the engine at crews that answer instantly and never touch a model."""
    from twenty_questions_of_life.models import AnswerAssessment, NextQuestion, Verdict

    class Output:
        def __init__(self, payload):
            self.pydantic = payload

    class Panel:
        def crew(self):
            return self

        def lean_crew(self):
            return self

        def kickoff(self, inputs):
            area = inputs["target_area"].split("key: ")[1].split(")")[0]
            return Output(
                NextQuestion(
                    dimension=area,
                    question=f"A question about {area}?",
                    why_this_question="Because it has not been asked.",
                    what_a_bluff_looks_like="A slogan.",
                )
            )

    class Assessor(Panel):
        def kickoff(self, inputs):
            return Output(
                AnswerAssessment(
                    lived=4, coherent=4, honest=4, original=3, consequential=3,
                    evaded=False, contradiction=None,
                    read="Specific, and it cost them something.",
                    probe_next="Press on the part they skipped over.",
                )
            )

    class VerdictMaker(Panel):
        def kickoff(self, inputs):
            return Output(
                Verdict(
                    headline="You have done some of the work.",
                    what_you_understand=["You know what you do not know."],
                    where_you_are_bluffing=["The bit about work."],
                    contradictions=[],
                    the_question_you_dodged="The one about money.",
                    what_would_change_this="Have the conversation you have been putting off.",
                )
            )

    module.PanelCrew, module.AssessorCrew, module.VerdictCrew = Panel, Assessor, VerdictMaker


@unittest.skipUnless(HAVE_WEB, "needs crewai, fastapi and httpx")
class TheWebInterview(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("OPENAI_API_KEY", "sk-not-used")
        from fastapi.testclient import TestClient

        from twenty_questions_of_life import engine, web

        self.engine, self.web = engine, web
        fake_crews(engine)
        self.directory = tempfile.mkdtemp()
        web.Settings.sessions_dir = self.directory
        web.Settings.token = None
        web.SESSIONS.clear()
        self.client = TestClient(web.app)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        self.web.SESSIONS.clear()

    def wait_for(self, sid, status, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.client.get(f"/api/state/{sid}").json()
            if state["status"] == status:
                return state
            time.sleep(0.02)
        self.fail(f"stuck in {state['status']}, wanted {status}")

    def start(self, questions=2):
        response = self.client.post(
            "/api/start", json={"name": "Tester", "questions": questions, "panel": "lean"}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["sid"]

    def test_a_question_is_waiting_shortly_after_starting(self):
        sid = self.start()
        state = self.wait_for(sid, "question")
        self.assertEqual(state["question"]["number"], 1)
        self.assertTrue(state["question"]["text"])
        self.assertTrue(state["question"]["area"])

    def test_answering_moves_to_the_next_question_and_shows_the_panel_note(self):
        sid = self.start()
        self.wait_for(sid, "question")
        self.client.post(f"/api/answer/{sid}", json={"text": "Something that actually happened."})
        state = self.wait_for(sid, "question")
        self.assertEqual(state["answered"], 1)
        self.assertEqual(state["question"]["number"], 2)
        self.assertIn("cost them", state["note"])

    def test_the_last_answer_produces_a_verdict_and_a_downloadable_report(self):
        sid = self.start(questions=2)
        for _ in range(2):
            self.wait_for(sid, "question")
            self.client.post(f"/api/answer/{sid}", json={"text": "A real answer."})
        state = self.wait_for(sid, "done")
        self.assertGreater(state["result"]["score"], 0)
        self.assertTrue(state["result"]["band"])
        self.assertEqual(state["result"]["verdict"]["headline"], "You have done some of the work.")

        report = self.client.get(f"/api/report/{sid}")
        self.assertEqual(report.status_code, 200)
        self.assertIn("# Twenty Questions of Life", report.text)
        self.assertIn("attachment", report.headers["content-disposition"])

    def test_a_double_tap_cannot_answer_the_same_question_twice(self):
        sid = self.start()
        self.wait_for(sid, "question")
        first = self.client.post(f"/api/answer/{sid}", json={"text": "One.", "number": 1})
        second = self.client.post(f"/api/answer/{sid}", json={"text": "One again.", "number": 1})
        self.assertEqual(first.status_code, 200)
        # Either the worker is still marking, or it has moved on to question 2
        # and the stale number is refused. Both are a 409, and neither answers
        # question 2 with the text meant for question 1.
        self.assertEqual(second.status_code, 409)
        self.wait_for(sid, "question")
        self.assertEqual(self.client.get(f"/api/state/{sid}").json()["answered"], 1)

    def test_an_interview_survives_the_server_forgetting_it(self):
        sid = self.start()
        self.wait_for(sid, "question")
        self.client.post(f"/api/answer/{sid}", json={"text": "An answer."})
        self.wait_for(sid, "question")

        self.web.SESSIONS.clear()  # as if the process had been restarted
        state = self.client.get(f"/api/state/{sid}").json()
        self.assertEqual(state["answered"], 1)
        self.assertEqual(state["status"], "question")

    def test_unknown_interviews_are_not_found(self):
        self.assertEqual(self.client.get("/api/state/nope").status_code, 404)

    def test_open_interviews_are_listed_so_you_can_pick_one_back_up(self):
        sid = self.start()
        self.wait_for(sid, "question")
        listed = self.client.get("/api/sessions").json()
        self.assertIn(sid, [row["sid"] for row in listed])

    def test_the_token_is_enforced_on_the_api_but_not_the_page(self):
        self.web.Settings.token = "shared-secret"
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.post("/api/start", json={}).status_code, 401)
        self.assertEqual(
            self.client.post("/api/start", json={}, headers={"X-Interview-Token": "wrong"}).status_code,
            401,
        )
        allowed = self.client.post(
            "/api/start", json={"questions": 1}, headers={"X-Interview-Token": "shared-secret"}
        )
        self.assertEqual(allowed.status_code, 200)

    def test_the_page_is_served_and_carries_the_viewport_a_phone_needs(self):
        page = self.client.get("/")
        self.assertIn("width=device-width", page.text)
        self.assertIn("Twenty Questions of Life", page.text)


@unittest.skipUnless(HAVE_WEB, "needs crewai")
class SavingAndReloading(unittest.TestCase):
    def test_an_interview_round_trips_through_a_dictionary(self):
        from twenty_questions_of_life import engine
        from twenty_questions_of_life.engine import Interview, InterviewConfig

        fake_crews(engine)
        interview = Interview(config=InterviewConfig(name="Tester", total_questions=2))
        interview.ask()
        interview.answer("Something true.")
        interview.ask()

        copy = Interview.from_dict(interview.to_dict())
        self.assertEqual(copy.config.name, "Tester")
        self.assertEqual(len(copy.exchanges), 1)
        self.assertEqual(copy.exchanges[0].answer, "Something true.")
        self.assertEqual(copy.exchanges[0].score, interview.exchanges[0].score)
        self.assertEqual(copy.pending.question, interview.pending.question)
        self.assertEqual(copy.probe_next, interview.probe_next)

    def test_pass_words_are_recorded_as_a_pass_and_scored_as_one(self):
        from twenty_questions_of_life import engine
        from twenty_questions_of_life.engine import Interview, InterviewConfig

        fake_crews(engine)
        interview = Interview(config=InterviewConfig(total_questions=2))
        interview.ask()
        exchange = interview.answer("  Pass  ")
        self.assertEqual(exchange.answer, "")
        self.assertEqual(exchange.score, 0.0)
        self.assertTrue(exchange.assessment.evaded)


if __name__ == "__main__":
    unittest.main()
