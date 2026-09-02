"""Talking to the person, and writing down what happened.

Kept separate from the flow so the interview can be driven by a keyboard, by
a file of prepared answers (useful for demos and for re-running the same
subject against a changed prompt), or by anything else you bolt on later.
"""

import json
import os
import textwrap
from datetime import datetime
from typing import Dict, List, Optional

from .dimensions import DIMENSIONS_BY_KEY
from .models import Exchange, Verdict
from . import scoring

WIDTH = 88
RULE = "-" * WIDTH


def wrap(text: str, indent: str = "") -> str:
    return "\n".join(
        textwrap.fill(line, WIDTH, initial_indent=indent, subsequent_indent=indent) or indent
        for line in text.splitlines() or [""]
    )


class AnswerSource:
    """Where answers come from. Default is a human at a terminal."""

    def __init__(self, prepared: Optional[List[str]] = None):
        self.prepared = list(prepared) if prepared else None

    @classmethod
    def from_file(cls, path: str) -> "AnswerSource":
        """One answer per line, or a JSON list of strings. Blank lines are skipped."""
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
        try:
            loaded = json.loads(raw)
            answers = [str(item) for item in loaded]
        except json.JSONDecodeError:
            answers = [line.strip() for line in raw.splitlines() if line.strip()]
        return cls(prepared=answers)

    def get(self, number: int) -> str:
        if self.prepared is not None:
            answer = self.prepared[number - 1] if number <= len(self.prepared) else ""
            print(f"  (prepared answer) {answer}\n")
            return answer
        print("  Your answer (end with an empty line):")
        lines: List[str] = []
        while True:
            try:
                line = input("  > ")
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line)
        print()
        return "\n".join(lines).strip()


def opening(total: int, name: str) -> None:
    print(RULE)
    print("TWENTY QUESTIONS OF LIFE".center(WIDTH))
    print(RULE)
    print(
        wrap(
            f"{name}, a panel of four is going to ask you {total} questions. They are not "
            "picked in advance. Each one is chosen after your last answer, aimed at the "
            "part of life you have not covered or have covered badly."
        )
    )
    print()
    print(
        wrap(
            "Two things worth knowing. The panel is looking for answers that cost you "
            "something, not answers that sound wise. And the score is arithmetic, not "
            "opinion, so being agreeable with it will not help you."
        )
    )
    print()
    print(wrap("Say 'pass' if you want to skip one. It is recorded as a pass."))
    print(RULE)
    print()


def put_question(number: int, total: int, dimension: str, question: str, why: str) -> None:
    area = DIMENSIONS_BY_KEY[dimension].title if dimension in DIMENSIONS_BY_KEY else dimension
    print(RULE)
    print(f"Question {number} of {total}   [{area}]")
    print(RULE)
    print(wrap(question))
    print()
    print(wrap(f"Why this one: {why}", indent="  "))
    print()


def show_read(score: float, read: str) -> None:
    print(wrap(f"Panel note ({score}/5): {read}", indent="  "))
    print()


def transcript_text(exchanges: List[Exchange], limit: Optional[int] = None) -> str:
    """The interview so far, as plain text for a prompt."""
    if not exchanges:
        return "Nothing yet. This is the first question."
    chosen = exchanges[-limit:] if limit else exchanges
    blocks = []
    for ex in chosen:
        note = ""
        if ex.assessment is not None:
            flags = []
            if ex.assessment.evaded:
                flags.append("evaded")
            if ex.assessment.contradiction:
                flags.append(f"contradiction: {ex.assessment.contradiction}")
            flag_text = f" [{'; '.join(flags)}]" if flags else ""
            note = f"\nPanel read ({ex.score}/5){flag_text}: {ex.assessment.read}"
        blocks.append(
            f"Q{ex.number} [{ex.dimension}]: {ex.question}\n"
            f"Answer: {ex.answer or '(no answer given)'}{note}"
        )
    return "\n\n".join(blocks)


def coverage_text(exchanges: List[Exchange]) -> str:
    """Which areas have been asked about, and how they went."""
    averages = scoring.dimension_averages(exchanges)
    counts: Dict[str, int] = {}
    for ex in exchanges:
        counts[ex.dimension] = counts.get(ex.dimension, 0) + 1
    lines = []
    for key, dim in DIMENSIONS_BY_KEY.items():
        if key in averages:
            lines.append(f"- {dim.title}: asked {counts[key]}x, average {averages[key]}/5")
        else:
            lines.append(f"- {dim.title}: not asked yet")
    return "\n".join(lines)


def render_report(
    name: str,
    exchanges: List[Exchange],
    score: float,
    band_name: str,
    band_blurb: str,
    verdict: Optional[Verdict],
) -> str:
    averages = scoring.dimension_averages(exchanges)
    lines = [
        "# Twenty Questions of Life",
        "",
        f"**Subject:** {name}  ",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Questions answered:** {len([e for e in exchanges if e.answer])} of {len(exchanges)}  ",
        f"**Score:** {score} / 5  ",
        f"**Verdict:** {band_name}",
        "",
        band_blurb,
        "",
    ]

    if verdict:
        lines += ["## The short version", "", verdict.headline, ""]
        if verdict.what_you_understand:
            lines += ["### What you have actually got hold of", ""]
            lines += [f"- {item}" for item in verdict.what_you_understand] + [""]
        if verdict.where_you_are_bluffing:
            lines += ["### Where you were repeating things", ""]
            lines += [f"- {item}" for item in verdict.where_you_are_bluffing] + [""]
        if verdict.contradictions:
            lines += ["### Answers that do not agree with each other", ""]
            lines += [f"- {item}" for item in verdict.contradictions] + [""]
        lines += [
            "### The question you dodged",
            "",
            verdict.the_question_you_dodged,
            "",
            "### What would change this",
            "",
            verdict.what_would_change_this,
            "",
        ]

    lines += ["## Area by area", "", "| Area | Times asked | Average |", "| --- | --- | --- |"]
    counts: Dict[str, int] = {}
    for ex in exchanges:
        counts[ex.dimension] = counts.get(ex.dimension, 0) + 1
    for key, dim in DIMENSIONS_BY_KEY.items():
        asked = counts.get(key, 0)
        avg = f"{averages[key]}/5" if key in averages else "-"
        lines.append(f"| {dim.title} | {asked} | {avg} |")
    lines.append("")

    lines += ["## Full transcript", ""]
    for ex in exchanges:
        area = DIMENSIONS_BY_KEY[ex.dimension].title if ex.dimension in DIMENSIONS_BY_KEY else ex.dimension
        lines += [f"### Q{ex.number}. {ex.question}", "", f"*Area: {area}*", ""]
        lines += [f"**Answer:** {ex.answer or '(passed)'}", ""]
        if ex.assessment is not None:
            a = ex.assessment
            lines += [
                f"**Panel read ({ex.score}/5):** {a.read}",
                "",
                f"lived {a.lived} | coherent {a.coherent} | honest {a.honest} | "
                f"own thinking {a.original} | changes what you do {a.consequential}",
                "",
            ]
            if a.contradiction:
                lines += [f"**Contradiction:** {a.contradiction}", ""]
    return "\n".join(lines)


def save_session(report: str, exchanges: List[Exchange], directory: str = "sessions") -> str:
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(directory, f"{stamp}-report.md")
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    with open(os.path.join(directory, f"{stamp}-transcript.json"), "w", encoding="utf-8") as handle:
        json.dump([ex.model_dump() for ex in exchanges], handle, indent=2)
    return report_path
