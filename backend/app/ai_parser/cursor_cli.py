"""Run the Cursor CLI (`agent`) headless in a workspace and return its JSON answer.

`--mode ask` keeps the agent read-only: it reads the workspace files and answers, but never
edits files or runs commands. The backend writes the output itself.
"""
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import settings


class CursorCliError(RuntimeError):
    pass


@dataclass
class AgentReply:
    data: object  # the JSON object the agent answered with
    session_id: str | None  # lets a follow-up call continue the same chat (--resume)


Runner = Callable[[Path, str, str | None], AgentReply]


def build_command(workspace: Path, prompt: str, resume: str | None = None) -> list[str]:
    cmd = [
        settings.cursor_cli_path, "-p", "--output-format", "json",
        "--mode", "ask", "--trust", "--workspace", str(workspace),
    ]
    if settings.cursor_model:
        cmd += ["--model", settings.cursor_model]
    if resume:
        cmd += ["--resume", resume]
    return cmd + [prompt]


def parse_answer(text: str) -> object:
    """The JSON object in the agent's answer; tolerates code fences or words around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise CursorCliError("the agent's answer contains no JSON object")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise CursorCliError(f"the agent's answer is not valid JSON: {exc}") from exc


def run_agent(workspace: Path, prompt: str, resume: str | None = None) -> AgentReply:
    try:
        proc = subprocess.run(
            build_command(workspace, prompt, resume),
            capture_output=True, text=True, timeout=settings.cursor_timeout_s, cwd=workspace,
        )
    except FileNotFoundError as exc:
        raise CursorCliError(
            f"Cursor CLI {settings.cursor_cli_path!r} not found; install it with "
            "`curl https://cursor.com/install -fsS | bash` and sign in with `agent login`"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CursorCliError(f"Cursor CLI timed out after {settings.cursor_timeout_s} s") from exc
    if proc.returncode != 0:
        # On failure the CLI prints no JSON, only a message on stderr
        raise CursorCliError(f"Cursor CLI exited with {proc.returncode}: {(proc.stderr or proc.stdout).strip()}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CursorCliError(f"unexpected Cursor CLI output: {proc.stdout[:200]!r}") from exc
    if envelope.get("is_error"):
        raise CursorCliError(f"Cursor agent error: {envelope.get('result')}")
    return AgentReply(data=parse_answer(envelope.get("result") or ""), session_id=envelope.get("session_id"))
