"""The same interview, over a web page, so you can do it on a phone.

The panel takes half a minute to write a question and the same again to mark
an answer, which is far too long to hold an HTTP request open on a phone that
is about to lock its screen. So every model call runs on a background thread,
the page polls for the state, and the whole interview is written to disk after
each step. Close the tab on question eleven, come back in the evening, open
the same link and carry on.

    python -m twenty_questions_of_life.web --host 0.0.0.0

Bind to anything other than localhost and it demands a token, generates one if
you did not set it, and prints the link with the token in it.
"""

import argparse
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from twenty_questions_of_life.dimensions import DIMENSIONS_BY_KEY
from twenty_questions_of_life.engine import Interview, InterviewConfig
from twenty_questions_of_life.main import apply_model_env

STATIC = Path(__file__).parent / "static"

# What the page is waiting for. "question" is the only state where it is your
# turn; everything else means a model call is in flight.
THINKING = "thinking"
QUESTION = "question"
MARKING = "marking"
WRITING = "writing"
DONE = "done"


class Settings:
    """Set once at startup by main(), read by the request handlers."""

    token: Optional[str] = None
    sessions_dir: str = "sessions"

    @classmethod
    def store(cls) -> Path:
        path = Path(cls.sessions_dir) / "web"
        path.mkdir(parents=True, exist_ok=True)
        return path


class WebSession:
    """One interview, plus the thread currently working on it."""

    def __init__(self, sid: str, interview: Interview, status: str = THINKING):
        self.sid = sid
        self.interview = interview
        self.status = status
        self.note: Optional[str] = None  # the panel's read on the last answer
        self.error: Optional[str] = None
        self.lock = threading.Lock()
        self.worker: Optional[threading.Thread] = None

    # -- persistence ------------------------------------------------------

    @property
    def path(self) -> Path:
        return Settings.store() / f"{self.sid}.json"

    def save(self) -> None:
        payload = {"sid": self.sid, "status": self.status, "note": self.note,
                   "interview": self.interview.to_dict()}
        # Write through a temporary file: a phone refreshing mid-write should
        # never be able to read half a session.
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @classmethod
    def load(cls, sid: str) -> Optional["WebSession"]:
        path = Settings.store() / f"{sid}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded = cls(sid, Interview.from_dict(payload["interview"]), payload.get("status", THINKING))
        loaded.note = payload.get("note")
        return loaded

    # -- running the model calls off the request thread -------------------

    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(self, target) -> None:
        if self.busy():
            return
        self.worker = threading.Thread(target=self._guard(target), daemon=True)
        self.worker.start()

    def _guard(self, target):
        def run():
            try:
                target()
            except Exception as failure:  # noqa: BLE001 - a dead thread must not hang the page
                self.error = str(failure)
                self.status = QUESTION if self.interview.pending else THINKING
            finally:
                self.save()

        return run

    def ask_next(self) -> None:
        self.status = THINKING
        self.save()
        self.interview.ask()
        self.status = QUESTION
        self.error = self.interview.last_error

    def take_answer(self, text: str) -> None:
        self.status = MARKING
        self.save()
        current = self.interview.answer(text)
        self.note = current.assessment.read if current.assessment else None
        self.error = self.interview.last_error
        if self.interview.finished:
            self.status = WRITING
            self.save()
            self.interview.finish()
            self.status = DONE
        else:
            self.ask_next()


SESSIONS: Dict[str, WebSession] = {}
SESSIONS_LOCK = threading.Lock()


def get_session(sid: str) -> WebSession:
    with SESSIONS_LOCK:
        if sid in SESSIONS:
            return SESSIONS[sid]
        restored = WebSession.load(sid)
        if restored is None:
            raise HTTPException(status_code=404, detail="No such interview.")
        SESSIONS[sid] = restored
    # A server that died mid-question left a session with nothing waiting.
    # Pick it back up rather than showing a page that never moves.
    if restored.status in {THINKING, MARKING} and not restored.busy():
        if restored.interview.finished:
            restored.start(lambda: (restored.interview.finish(), setattr(restored, "status", DONE)))
        else:
            restored.start(restored.ask_next)
    return restored


def check_token(
    x_interview_token: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
) -> None:
    """No token configured means loopback only, which is its own protection."""
    if Settings.token is None:
        return
    if secrets.compare_digest(x_interview_token or t or "", Settings.token):
        return
    raise HTTPException(status_code=401, detail="Bad or missing token.")


app = FastAPI(title="Twenty Questions of Life", docs_url=None, redoc_url=None)


class StartRequest(BaseModel):
    name: str = Field(default="Friend", max_length=60)
    questions: int = Field(default=20, ge=1, le=40)
    panel: str = Field(default="full", pattern="^(full|lean)$")


class AnswerRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    # Which question this is an answer to. The page always sends it, and it is
    # what makes a double tap on a slow connection harmless: the second one
    # names a question that has already been answered, so it is refused rather
    # than being applied to whatever came next.
    number: Optional[int] = Field(default=None, ge=1)


@app.get("/")
def page() -> FileResponse:
    # The page itself is public; every call it makes needs the token.
    return FileResponse(STATIC / "index.html")


@app.post("/api/start", dependencies=[Depends(check_token)])
def start(request: StartRequest) -> dict:
    sid = secrets.token_urlsafe(9)
    interview = Interview(
        config=InterviewConfig(
            name=request.name.strip() or "Friend",
            total_questions=request.questions,
            panel=request.panel,
            sessions_dir=Settings.sessions_dir,
        )
    )
    web_session = WebSession(sid, interview)
    with SESSIONS_LOCK:
        SESSIONS[sid] = web_session
    web_session.start(web_session.ask_next)
    return {"sid": sid}


@app.get("/api/state/{sid}", dependencies=[Depends(check_token)])
def state(sid: str) -> dict:
    web_session = get_session(sid)
    interview = web_session.interview
    payload = {
        "sid": sid,
        "status": web_session.status,
        "name": interview.config.name,
        "answered": interview.answered,
        "total": interview.config.total_questions,
        "note": web_session.note,
        "error": web_session.error,
        "question": None,
        "result": None,
    }
    if web_session.status == QUESTION and interview.pending:
        pending = interview.pending
        area = DIMENSIONS_BY_KEY.get(pending.dimension)
        payload["question"] = {
            "number": interview.answered + 1,
            "text": pending.question,
            "why": pending.why_this_question,
            "area": area.title if area else pending.dimension,
        }
    if web_session.status == DONE and interview.result:
        result = interview.result
        payload["result"] = {
            "score": result.score,
            "band": result.band,
            "band_blurb": result.band_blurb,
            "verdict": result.verdict.model_dump() if result.verdict else None,
            "path": result.path,
        }
    return payload


@app.post("/api/answer/{sid}", dependencies=[Depends(check_token)])
def answer(sid: str, request: AnswerRequest) -> dict:
    web_session = get_session(sid)
    with web_session.lock:
        if web_session.status != QUESTION or web_session.busy():
            raise HTTPException(status_code=409, detail="No question is waiting.")
        expected = web_session.interview.answered + 1
        if request.number is not None and request.number != expected:
            raise HTTPException(
                status_code=409,
                detail=f"That was an answer to question {request.number}; we are on {expected}.",
            )
        web_session.status = MARKING
        text = request.text
        web_session.start(lambda: web_session.take_answer(text))
    return {"status": web_session.status}


@app.get("/api/report/{sid}", dependencies=[Depends(check_token)])
def report(sid: str) -> PlainTextResponse:
    web_session = get_session(sid)
    if not web_session.interview.result:
        raise HTTPException(status_code=409, detail="The interview is not finished.")
    return PlainTextResponse(
        web_session.interview.result.report,
        headers={"Content-Disposition": f'attachment; filename="{sid}-report.md"'},
    )


@app.get("/api/sessions", dependencies=[Depends(check_token)])
def list_sessions() -> List[dict]:
    """Interviews you can pick back up, newest first."""
    out = []
    for path in sorted(Settings.store().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        interview = payload.get("interview", {})
        out.append({
            "sid": payload.get("sid", path.stem),
            "name": interview.get("config", {}).get("name", "Friend"),
            "answered": len(interview.get("exchanges", [])),
            "total": interview.get("config", {}).get("total_questions", 20),
            "status": payload.get("status", THINKING),
        })
    return out[:20]


def _print_launch_details(host: str, port: int, token: Optional[str]) -> None:
    shown = "localhost" if host in {"127.0.0.1", "localhost"} else host
    url = f"http://{shown}:{port}/" + (f"?t={token}" if token else "")
    print("\n  Twenty Questions of Life is up.")
    print(f"  Open this on your phone: {url}\n")
    if host == "0.0.0.0":
        print("  That address only works on your own network. To reach it from")
        print("  anywhere, put it behind Tailscale or a Cloudflare tunnel - see the README.\n")
    try:  # a QR code is much easier than typing a token on a phone
        import qrcode  # type: ignore

        code = qrcode.QRCode(border=1)
        code.add_data(url)
        code.print_ascii(invert=True)
    except ImportError:
        print("  (pip install qrcode for a scannable QR code of that link)\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the interview as a web page.")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from your phone")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--sessions-dir", default="sessions", help="Where interviews are stored")
    parser.add_argument("--token", help="Shared secret. Generated automatically if you expose the port")
    args = parser.parse_args()

    apply_model_env()
    Settings.sessions_dir = args.sessions_dir

    token = args.token or os.environ.get("INTERVIEW_TOKEN")
    if not token and args.host not in {"127.0.0.1", "localhost", "::1"}:
        # Anything reachable from another device is reachable by anything else
        # on that network, and this endpoint spends money on model calls.
        token = secrets.token_urlsafe(12)
        print("\n  No token set, so one has been generated for this run.")
    Settings.token = token

    _print_launch_details(args.host, args.port, token)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
