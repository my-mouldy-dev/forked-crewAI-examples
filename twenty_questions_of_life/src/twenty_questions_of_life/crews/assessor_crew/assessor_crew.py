"""Scoring one answer.

Two passes on purpose. A single model marking its own interview is a soft
marker; the second agent's only job is to take the score back down when the
first one was charmed. Neither of them decides the final verdict - they hand
back five numbers and two flags, and the arithmetic in scoring.py does the
rest.
"""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from twenty_questions_of_life.models import AnswerAssessment


@CrewBase
class AssessorCrew:
    """Scores a single answer on five criteria."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def answer_assessor(self) -> Agent:
        return Agent(config=self.agents_config["answer_assessor"])

    @agent
    def integrity_checker(self) -> Agent:
        return Agent(config=self.agents_config["integrity_checker"])

    @task
    def score_the_answer(self) -> Task:
        return Task(config=self.tasks_config["score_the_answer"])

    @task
    def cross_check(self) -> Task:
        return Task(
            config=self.tasks_config["cross_check"],
            output_pydantic=AnswerAssessment,
        )

    @crew
    def crew(self) -> Crew:
        """Score, then second-mark. Two LLM calls."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def lean_crew(self) -> Crew:
        """Single marker, one LLM call. Expect scores to drift upward."""
        return Crew(
            agents=[self.integrity_checker()],
            tasks=[self.cross_check()],
            process=Process.sequential,
            verbose=False,
        )
