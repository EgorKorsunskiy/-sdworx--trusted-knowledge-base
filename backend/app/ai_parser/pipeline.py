"""Source → Cursor agent → validated, enriched memes → JSON files under MEMES_DIR."""
import json
import tempfile
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import config
from app.ai_parser import cursor_cli
from app.ai_parser.cursor_cli import CursorCliError, Runner
from app.ai_parser.schema import AgentMeme
from app.ai_parser.sources import Source, load_chat, load_meeting, meme_day
from app.ai_parser.validate import validate_reply
from app.models import Category, Tag, User
from app.services.parser_agent import setting as agent_setting
from app.services.similarity import find_similar

PROMPT_VERSION = "2026-10-20.2"
PROMPT_FILE = Path(__file__).parent / "prompts" / "extract_memes.md"
PROMPT = (
    "Read instructions.md, source.md and context.json in this workspace "
    "and answer with only the JSON object described in instructions.md."
)
SOURCES_DIR = config.MOCK_DATA_DIR / "sources"

# One Cursor run at a time: runs are long and share the account's quota
_lock = threading.Lock()


def source_from_index(db: Session, row: dict) -> Source:
    """A mock source from mock_data/sources/index.json."""
    path = SOURCES_DIR / row["file"]
    if row["type"] == "chat":
        return only_known_participants(db, load_chat(path))
    users = db.query(User).filter(User.email.in_(row["participants"])).all()
    return load_meeting(path, row["title"], date.fromisoformat(row["date"]), {u.email: u.display_name for u in users})


def only_known_participants(db: Session, source: Source) -> Source:
    """Chat members without a Peerpoint account become guests: they can be neither speakers nor confirmers."""
    known = {email for (email,) in db.query(User.email).filter(User.email.in_(list(source.participants)))}
    source.guests = sorted(set(source.guests) | {n for e, n in source.participants.items() if e not in known})
    source.participants = {e: n for e, n in source.participants.items() if e in known}
    return source


def _repair_prompt(problems: list[dict]) -> str:
    lines = []
    for p in problems:
        where = f"meme {p['index']}" if p["index"] else "the answer"
        lines += [f"- {where}: {error}" for error in p["errors"]]
    return (
        "Your answer failed these checks:\n" + "\n".join(lines) + "\n"
        "Fix them and answer with the full corrected JSON object only, including the memes that were already correct."
    )


def _context(db: Session, source: Source) -> dict:
    tags = sorted(name for (name,) in db.query(Tag.name) if ":" not in name)  # skip automatic author:/date: tags
    return {
        "source": source.ref(),
        "participants": [{"email": e, "display_name": n} for e, n in source.participants.items()],
        "guests": source.guests,
        "existing_tags": tags,
        "categories": [name for (name,) in db.query(Category.name).order_by(Category.name)],
    }


def _ask_agent(db: Session, source: Source, runner: Runner) -> tuple[list[AgentMeme], list[dict], str | None]:
    """Run the agent, then one repair round if its answer fails validation."""
    with _lock, tempfile.TemporaryDirectory(prefix="peerpoint-memes-") as tmp:
        workspace = Path(tmp)  # only these three files: the agent never sees the repository
        (workspace / "instructions.md").write_text(PROMPT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        (workspace / "source.md").write_text(source.render(), encoding="utf-8")
        (workspace / "context.json").write_text(json.dumps(_context(db, source), indent=2, ensure_ascii=False), encoding="utf-8")

        reply = runner(workspace, PROMPT, None)
        memes, problems = validate_reply(reply.data, source)
        if problems:
            try:
                repaired = runner(workspace, _repair_prompt(problems), reply.session_id)
            except CursorCliError:
                pass  # keep the first answer; its invalid memes end up in "rejected"
            else:
                memes, problems = validate_reply(repaired.data, source)
                reply = repaired
    return memes, problems, reply.session_id


def _tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        name = " ".join(tag.lower().split())
        if name:
            seen.setdefault(name)
    return list(seen)


def _meme_out(db: Session, meme: AgentMeme, source: Source, meme_id: str, day: date | None) -> dict:
    similar = find_similar(db, meme.suggested.title, meme.statement)
    out = {"id": meme_id, "source": source.ref()}
    if day:
        out["day"] = day.isoformat()
    return {
        **out,
        **meme.model_dump(),
        "tags": _tags(meme.tags),
        "similar_entries": [{"public_id": m["public_id"], "score": m["score"]} for m in similar],
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@dataclass
class Extraction:
    source: Source
    memes: list[dict]  # enriched memes with id (and day for chats), in the agent contract format
    rejected: list[dict]  # {meme, errors} (and day for chats)
    generator: dict


def extract(db: Session, source: Source, runner: Runner | None = None) -> Extraction:
    """Run the agent on one source and return its validated, enriched memes."""
    threshold = agent_setting(db, "parser_confidence_threshold")  # the Admin setting the import uses too

    memes, problems, session_id = _ask_agent(db, source, runner or cursor_cli.run_agent)
    rejected = [{"meme": p["meme"], "errors": p["errors"]} for p in problems]
    kept = []
    for meme in memes:
        if meme.confidence < threshold:
            rejected.append({"meme": meme.model_dump(), "errors": [f"confidence {meme.confidence} is below {threshold}"]})
        else:
            kept.append(meme)

    if source.type == "meeting":
        out = [_meme_out(db, m, source, f"{source.id}#{n}", None) for n, m in enumerate(kept, 1)]
    else:
        # A chat meme belongs to the day of its latest quote; ids are numbered per day
        out, numbers = [], defaultdict(int)
        for meme in kept:
            day = meme_day(meme.model_dump(), source)
            numbers[day] += 1
            out.append(_meme_out(db, meme, source, f"{source.id}@{day.isoformat()}#{numbers[day]}", day))
        for item in rejected:
            item["day"] = meme_day(item["meme"] if isinstance(item["meme"], dict) else {}, source).isoformat()

    generator = {
        "tool": "cursor-agent",
        "model": config.settings.cursor_model,
        "session_id": session_id,
        "prompt_version": PROMPT_VERSION,
    }
    return Extraction(source=source, memes=out, rejected=rejected, generator=generator)


def write_files(extraction: Extraction, out_dir: Path | None = None) -> list[Path]:
    """Write the memes as JSON: one file per meeting, one file per chat day."""
    source, out_dir = extraction.source, out_dir or config.MEMES_DIR
    header = {
        "participants": [{"email": e, "display_name": n} for e, n in source.participants.items()],
        "guests": source.guests,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": extraction.generator,
    }
    if source.type == "meeting":
        payload = {"source": {"id": source.id, **source.ref()}, **header, "memes": extraction.memes, "rejected": extraction.rejected}
        return [_write(out_dir / "meetings" / f"{source.id}.json", payload)]

    by_day: dict[str, dict[str, list]] = defaultdict(lambda: {"memes": [], "rejected": []})
    for meme in extraction.memes:
        by_day[meme["day"]]["memes"].append(meme)
    for item in extraction.rejected:
        by_day[item["day"]]["rejected"].append({k: v for k, v in item.items() if k != "day"})

    chat_dir = out_dir / "chats" / source.id
    for old in chat_dir.glob("*.json"):
        old.unlink()  # a re-run replaces every day file of the chat
    return [
        _write(chat_dir / f"{day}.json", {"source": {"id": source.id, **source.ref(), "day": day}, **header, **by_day[day]})
        for day in sorted(by_day)
    ]


def run_source(db: Session, source: Source, out_dir: Path | None = None, runner: Runner | None = None) -> list[Path]:
    """Extract the memes of one source and write its demo file(s); returns the written paths."""
    return write_files(extract(db, source, runner), out_dir)
