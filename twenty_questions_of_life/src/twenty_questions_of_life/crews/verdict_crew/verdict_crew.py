"""The closing judgement.

By the time this crew runs, the score and the band are already decided by
arithmetic. These two agents only explain a result they cannot change, which
is the whole point: a model that can pick both the evidence and the grade
will always find a way to be encouraging.
"""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from twenty_questions_of_life.models import Verdict


@CrewBase
class VerdictCrew:
    """Writes up the interview once the numbers are locked."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def panel_chair(self) -> Agent:
        return Agent(config=self.agents_config["panel_chair"])

    @agent
    def plain_speaker(self) -> Agent:
        return Agent(config=self.agents_config["plain_speaker"])

    @task
    def find_the_pattern(self) -> Task:
        return Task(config=self.tasks_config["find_the_pattern"])

    @task
    def write_the_verdict(self) -> Task:
        return Task(
            config=self.tasks_config["write_the_verdict"],
            output_pydantic=Verdict,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )
