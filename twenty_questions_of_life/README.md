# Twenty Questions of Life

An interview, not a quiz. A panel of agents asks you twenty questions - none of them
written in advance - and then tells you, in plain English, whether you actually understand
life or just know what a good answer sounds like.

Every question is chosen after your last answer. If you dodge one, the next one comes back
at the same ground from a different side. If you have never been asked about death, or about
what you owe other people, the panel will notice the gap and close it. At the end you get a
score, a band, and a write-up that quotes you back to yourself.

## Why it is built this way

Two problems have to be solved for this to be worth anything.

**A single agent asks the same question twenty times.** Left alone, one model will produce
twenty polite variations of "what gives your life meaning". So the questions come from a
panel of four - an existential philosopher, a developmental psychologist, a contemplative
practitioner, and a skeptic whose only job is to find the seam you are protecting. A chair
reads all their candidates and keeps the one you cannot answer well without telling the
truth.

**A model that grades you will tell you that you passed.** So the model never decides the
result. Each answer is scored by an assessor on five named criteria, a second marker
re-checks that scoring and pulls it back down, and then plain arithmetic in `scoring.py`
combines the numbers, applies the penalties, and picks the band. The write-up crew is handed
a result it cannot change and is told to explain it without softening it.

## The five criteria

Each answer is scored 0-5 on each of these, then weighted:

| Criterion | What it asks | Weight |
| --- | --- | --- |
| lived | Is this rooted in something that happened to you, with detail? | 1.2 |
| coherent | Does it hold together, and hold with your earlier answers? | 1.0 |
| honest | Do you admit cost, doubt, and the parts that do not flatter you? | 1.3 |
| original | Is this your own thinking, or a well known line repeated? | 0.9 |
| consequential | Does this belief visibly change what you do? | 1.1 |

Honesty is weighted highest because it is the one you cannot fake upward by being well read.
Originality is weighted lowest because plenty of true things about life were first said by
somebody else. Answering an easier question than the one asked costs 0.75. Contradicting
yourself costs 0.5. A pass scores zero and is recorded as a pass.

## The twelve areas

Twenty questions is not many, so the interview walks a map: death and running out of time,
where meaning comes from, pain that does not resolve, what is yours to control, other people,
being a different person over time, the story you tell about yourself, what you owe others,
work, ordinary days, not knowing, and whether your calendar agrees with your philosophy.

Breadth comes first - the panel will not spend six questions on meaning while never asking
about death. Once every area has been touched, the remaining questions go to your weakest
answers. No area gets asked about more than three times, and no area gets pressed more than
twice in a row.

Each area is defined in `dimensions.py`, including what a borrowed answer to it sounds like
and what a lived one sounds like. That text goes to the panel verbatim, so editing that one
file changes the whole interview.

## Installation

Python >=3.10 <=3.13.

```bash
pip install crewai
```

Copy `.env_example` to `.env` and put your `OPENAI_API_KEY` in it. Set `MODEL` in the same
file if you want something other than the default, for example `gpt-4o-mini` to keep the cost
down.

If you hit `ModuleNotFoundError: No module named 'pkg_resources'` on a fresh environment,
install `setuptools<81` - crewai 0.85 still imports `pkg_resources`, which newer setuptools
dropped.

## Running it

```bash
crewai flow kickoff
```

Answer each question in the terminal and finish with an empty line. Type `pass` to skip one;
it is recorded as a pass and scored as one.

Options are on the module itself. Run it from this folder, either through the installed
package (`crewai install`, then `uv run python -m ...`) or straight from the source tree:

```bash
PYTHONPATH=src python -m twenty_questions_of_life.main --name "Sam" --questions 20 --panel full
```

| Flag | What it does |
| --- | --- |
| `--name` | What the panel calls you |
| `--questions` | How many questions (default 20) |
| `--panel lean` | Chair only instead of the full panel, single marker instead of two. About a fifth of the cost, noticeably blunter questions |
| `--answers FILE` | Read answers from a file instead of typing them - one per line, or a JSON list |
| `--sessions-dir` | Where the report is written (default `sessions/`) |

To see it catch a bluff without typing anything, run it against the twenty platitudes in
`example_answers.txt`:

```bash
PYTHONPATH=src python -m twenty_questions_of_life.main --name "Demo" --answers example_answers.txt
```

## On your phone

The terminal version needs a keyboard. This one does not: the same panel, the same scoring,
one question per screen.

```bash
pip install -e ".[web]"
python -m twenty_questions_of_life.web --host 0.0.0.0
```

It prints a link with a token in it, and a QR code you can point your phone at. Answers are
saved after every question, so you can close the tab on question eleven, and open the same
link that evening to carry on - the start screen offers any interview you have left open.

A model call takes half a minute, which is longer than a phone will hold an HTTP request
open, so the work runs on a background thread and the page polls for it. That is also why
closing the tab costs you nothing.

### Reaching it from outside your house

`--host 0.0.0.0` is enough if the phone is on the same wifi as the machine running it. From
anywhere else, pick one:

| How | What to do | Worth knowing |
| --- | --- | --- |
| Tailscale | Install it on both devices, then use the machine's tailnet address | Nothing is exposed to the internet. This is the one to pick |
| Cloudflare tunnel | `cloudflared tunnel --url http://localhost:8020` | A public URL anyone with the link can hit, so keep the token |
| A small VPS | Run it there behind nginx and TLS | You are now hosting a service; treat it like one |

### The token

Bind to anything other than localhost and the app requires a token on every API call. If you
did not set one it generates one for the run and prints it in the link. Set your own with
`--token`, or the `INTERVIEW_TOKEN` environment variable, if you want the link to keep
working across restarts.

The token is the only thing between the open port and your model spend. Do not put this on a
public URL without one, and do not paste the link into anything you would not paste an API
key into.

### What it costs

A full run is about 20 x 5 calls for the questions, 20 x 2 for the scoring, and 2 for the
write-up: roughly 140 model calls. `--panel lean` cuts that to about 40. Neither is expensive
on a small model, but do not point this at your most expensive one and walk away.

## What you get back

Every run writes two files into `sessions/`:

- `<timestamp>-report.md` - the score, the band, what you have got hold of, where you were
  repeating things, the contradictions the panel logged, the question you dodged, an area by
  area table, and the full transcript with the panel's note on every answer.
- `<timestamp>-transcript.json` - the same thing as data, for re-running or comparing.

The bands, in order: *Lived it, and knows it* / *Real understanding, unevenly held* / *You have
thought about it. It is still mostly theory* / *Borrowed answers* / *Not yet - this was a
performance*.

## How the flow is wired

```
compose_question  ->  take_answer  ->  assess_answer  ->  router
      ^                                                     |
      |______________________ "ask_next" ___________________|
                                                            |
                                                      "wrap_up"
                                                            |
                                                    deliver_verdict
```

`compose_question` is a `@start("ask_next")` method, so the router can send the flow back to
it twenty times. Draw it with `crewai flow plot`.

## Layout

```
src/twenty_questions_of_life/
  engine.py        the interview itself, with no front end in it - both UIs drive this
  main.py          the crewAI Flow, the terminal loop, and the CLI
  web.py           the web front end: background workers, saved sessions, token check
  static/          the one page the phone loads
  dimensions.py    the twelve areas of life, and what a fake answer to each sounds like
  scoring.py       all the arithmetic: weights, penalties, coverage, bands, what to ask next
  session.py       the terminal, the transcript, and the report
  models.py        the shapes the crews return
  crews/
    panel_crew/     four proposers and a chair - writes the next question
    assessor_crew/  assessor and second marker - scores one answer
    verdict_crew/   chair and plain speaker - explains a result they cannot change
```

`scoring.py`, `session.py`, `dimensions.py` and `models.py` do not import crewAI, so the
judgement can be tested without an LLM anywhere near it. The web tests stub the three crews
out, so they need no key either:

```bash
python -m unittest discover tests
```

That is 31 tests: the weighting and the penalties, the rules for what gets asked next, the
bands, the report, and the web state machine - starting, answering, double taps, resuming an
interview the server has forgotten, and the token check.

## Windows

Everything above works the same in PowerShell, with two differences - the virtual environment
path, and how you set an environment variable:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[web]"
$env:OPENAI_API_KEY = "sk-..."
python -m twenty_questions_of_life.web --host 0.0.0.0
```

If Windows Firewall prompts when the server starts, allow it on private networks only - that
is what lets your phone reach it over your own wifi.

## Things worth knowing

- If a model call fails, the interview does not die. The panel falls back to a standing
  question for that area, and an answer that could not be scored is left out of the average
  rather than counted as a zero.
- The panel is asked to echo back the area key it was given. If it invents one, the code
  keeps the area that was actually chosen, so the coverage map stays honest.
- The web front end tags each answer with the question number it was written for, so a
  double tap on a slow connection cannot land your answer on the next question.
- Every agent is told, in its backstory, to write in plain English - no jargon, no therapy
  language, no mystical language. That is a real constraint on the output, not decoration.

## Support

- [Documentation](https://docs.crewai.com)
- [GitHub](https://github.com/joaomdmoura/crewai)
- [Discord](https://discord.com/invite/X4JWnZnxPb)
