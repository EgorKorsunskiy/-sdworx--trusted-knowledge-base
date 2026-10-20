"""Read Teams transcripts (.vtt) and group chat exports (.json) into units the agent can quote."""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

_TIMING = re.compile(r"^(\d{2}:\d{2}:\d{2})\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}")
_VOICE = re.compile(r"^<v ([^>]+)>(.*?)(?:</v>)?$", re.S)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "source"


def normalize(text: str) -> str:
    """Whitespace-insensitive form used to compare quotes with the source."""
    return " ".join(text.split())


@dataclass
class Unit:
    """One transcript cue or chat message; quotes point to it by `at`."""

    at: str  # cue start "HH:MM:SS" or message id
    speaker: str  # display name, or the guest's label
    text: str
    order: int
    line: str  # how the unit is shown to the agent in source.md
    day: date | None = None  # chats only
    deleted: bool = False


@dataclass
class Source:
    id: str
    type: Literal["meeting", "chat"]
    title: str
    participants: dict[str, str]  # email -> display name
    units: list[Unit]
    meeting_date: date | None = None  # meetings
    date_from: date | None = None  # chats
    date_to: date | None = None
    guests: list[str] = field(default_factory=list)

    def units_at(self, at: str) -> list[Unit]:
        return [u for u in self.units if u.at == at]

    def ref(self) -> dict:
        """The `source` object of every meme, as in the agent contract."""
        if self.type == "meeting":
            return {"type": "meeting", "title": self.title, "date": self.meeting_date.isoformat()}
        return {
            "type": "chat",
            "title": self.title,
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }

    def render(self) -> str:
        return "\n".join(u.line for u in self.units) + "\n"


def parse_vtt(path: Path) -> list[tuple[str, str, str]]:
    """Cues of a Teams WebVTT transcript as (start "HH:MM:SS", speaker label, text)."""
    cues = []
    for block in path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n\n"):
        lines = [line for line in block.strip().split("\n") if line]
        timing = next((i for i, line in enumerate(lines) if _TIMING.match(line)), None)
        if timing is None:
            continue  # header, NOTE or STYLE block
        text = " ".join(lines[timing + 1:])
        voice = _VOICE.match(text)
        speaker, text = (voice.group(1), voice.group(2)) if voice else ("Unknown", text)
        cues.append((_TIMING.match(lines[timing]).group(1), speaker.strip(), text.strip()))
    return cues


def load_meeting(path: Path, title: str, meeting_date: date, participants: dict[str, str], source_id: str | None = None) -> Source:
    units = [
        Unit(at=at, speaker=speaker, text=text, order=i, line=f"[{at}] {speaker}: {text}")
        for i, (at, speaker, text) in enumerate(parse_vtt(path))
    ]
    names = set(participants.values())
    guests = sorted({u.speaker for u in units if u.speaker not in names})
    return Source(
        id=source_id or path.stem,
        type="meeting",
        title=title,
        participants=participants,
        units=units,
        meeting_date=meeting_date,
        guests=guests,
    )


def load_chat(path: Path, source_id: str | None = None) -> Source:
    data = json.loads(path.read_text(encoding="utf-8"))
    participants = {m["email"]: m["display_name"] for m in data["members"]}
    units = []
    for i, msg in enumerate(data["messages"]):
        name = participants.get(msg["from"], msg["from"])
        sent = datetime.fromisoformat(msg["created_at"])
        deleted = bool(msg.get("deleted_at"))
        # Only the final text of an edited message counts; deleted messages are never shown, so never quoted
        text = "[deleted]" if deleted else msg["text"]
        header = f"{msg['id']} · {sent:%Y-%m-%d %H:%M} · {name}"
        if msg.get("reply_to_id"):
            header += f" · reply to {msg['reply_to_id']}"
        extras = [f"attachment: {a['type']} {a.get('name', '')}".strip() for a in msg.get("attachments", [])]
        if msg.get("reactions"):
            extras.append("reactions: " + ", ".join(f"{r['emoji']} {participants.get(r['by'], r['by'])}" for r in msg["reactions"]))
        body = text.replace("\n", "\n    ")  # continuation lines of a multi-line message are indented
        line = f"[{header}] {body}" + "".join(f"  ({e})" for e in extras)
        units.append(Unit(at=msg["id"], speaker=name, text=text, order=i, line=line, day=sent.date(), deleted=deleted))
    return Source(
        id=source_id or path.stem,
        type="chat",
        title=data["chat"]["title"],
        participants=participants,
        units=units,
        date_from=date.fromisoformat(data["range"]["from"]),
        date_to=date.fromisoformat(data["range"]["to"]),
    )


def meme_day(meme: dict, source: Source) -> date:
    """A chat meme belongs to the day of its latest quote (statement or confirmation)."""
    ats = [q.get("at") for q in meme.get("quotes", [])] + [
        (c.get("quote") or {}).get("at") for c in meme.get("confirmed_by", [])
    ]
    days = [u.day for at in ats for u in source.units_at(at) if u.day]
    return max(days) if days else source.date_to
