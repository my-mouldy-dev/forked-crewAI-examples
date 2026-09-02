"""The panel that writes the questions.

Four specialists propose, a chair picks one. The point of the panel is spread:
a philosopher and a skeptic ask about different things, and left to itself a
single agent will ask twenty polite variations of "what gives your life
meaning". The chair exists because panels produce paragraphs, and a question
you cannot say out loud in one breath is not a question.
"""

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from twenty_questions_of_life.models import NextQuestion


@CrewBase
class PanelCrew:
    """Writes the next question, given everything said so far."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def existential_philosopher(self) -> Agent:
        return Agent(config=self.agents_config["existential_philosopher"])

    @agent
    def developmental_psychologist(self) -> Agent:
        return Agent(config=self.agents_config["developmental_psychologist"])

    @agent
    def contemplative_practitioner(self) -> Agent:
        return Agent(config=self.agents_config["contemplative_practitioner"])

    @agent
    def hard_skeptic(self) -> Agent:
        return Agent(config=self.agents_config["hard_skeptic"])

    @agent
    def question_master(self) -> Agent:
        return Agent(config=self.agents_config["question_master"])

    @task
    def philosophical_angle(self) -> Task:
        return Task(config=self.tasks_config["philosophical_angle"])

    @task
    def psychological_angle(self) -> Task:
        return Task(config=self.tasks_config["psychological_angle"])

    @task
    def practice_angle(self) -> Task:
        return Task(config=self.tasks_config["practice_angle"])

    @task
    def skeptical_angle(self) -> Task:
        return Task(config=self.tasks_config["skeptical_angle"])

    @task
    def choose_question(self) -> Task:
        return Task(
            config=self.tasks_config["choose_question"],
            output_pydantic=NextQuestion,
        )

    @crew
    def crew(self) -> Crew:
        """Full panel: four proposals, then the chair chooses. Five LLM calls."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def lean_crew(self) -> Crew:
        """Chair only, one LLM call. Cheaper, noticeably blunter questions."""
        return Crew(
            agents=[self.question_master()],
            tasks=[self.choose_question()],
            process=Process.sequential,
            verbose=False,
        )
