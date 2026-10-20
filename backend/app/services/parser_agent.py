"""Stub parser agent: stores the memes of an agent's output as New memes with one suggestion per candidate.

For the demo the "agent" is the reference output in ``mock_data/sources/expected`` (the agent contract of
specs/ai-parser/FUNCTIONAL_SPEC.md section 6). ``import_agent_output`` validates it the way the backend must for a real
agent: one speaker who is a participant, confirmers who are other participants, at least one quote, a confidence above
the admin threshold. No quote, no meme (BR-M6).
"""

import json
import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import MOCK_DATA_DIR
from app.models import (
    ClientProject,
    Company,
    Meme,
    Notification,
    Quote,
    Source,
    SourceParticipant,
    Suggestion,
    SuggestionEvent,
    SystemSetting,
    User,
)
from app.services import tags as tag_service
from app.services.similarity import find_similar

SOURCES_DIR = MOCK_DATA_DIR / "sources"
CONTEXT_LINES = 2  # lines of the conversation kept before and after a quote
SCOPES = {"universal", "eu", "country", "company", "client_project"}

DEFAULTS = {
    "parser_confidence_threshold": 0.6,
    "parser_raw_retention_days": 30,
}


def setting(db: Session, key: str):
    """An agent setting an Admin can change; falls back to the PoC default."""
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    default = DEFAULTS[key]
    if row is None:
        return default
    try:
        return type(default)(row.value)
    except ValueError:
        return default


# --- reading the mock sources (context around quotes) ---------------------------------------------------------------

_CUE = re.compile(r"(\d\d:\d\d:\d\d)\.\d+\s+-->\s+\S+\s*\n<v ([^>]+)>(.*?)(?:</v>)?\s*(?:\n\n|\Z)", re.S)


def _meeting_lines(path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [
        {"at": m.group(1), "speaker": m.group(2).strip(), "text": " ".join(m.group(3).split())}
        for m in _CUE.finditer(text + "\n\n")
    ]


def _chat_lines(path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    names = {m["email"]: m["display_name"] for m in data.get("members", [])}
    return [
        {"at": m["id"], "speaker": names.get(m["from"], m["from"]), "text": m.get("text", "")}
        for m in data.get("messages", [])
        if not m.get("deleted_at")
    ]


def _context(lines: list[dict], at: str) -> list[dict]:
    """A few lines around the quoted one, cut from the stored source now so the raw file can be purged later."""
    for i, line in enumerate(lines):
        if line["at"] == at:
            lo, hi = max(0, i - CONTEXT_LINES), min(len(lines), i + CONTEXT_LINES + 1)
            return [{**l, "quote": j == i} for j, l in enumerate(lines[lo:hi], start=lo)]
    return []


# --- importing agent output ---------------------------------------------------------------------------------------------


def _scope_pointers(db: Session, suggested: dict) -> tuple[str, int | None, int | None]:
    scope = suggested.get("scope", "country")
    if scope not in SCOPES:
        scope = "country"
    company_id = client_project_id = None
    if scope == "company" and suggested.get("company"):
        company = db.query(Company).filter(Company.name.ilike(suggested["company"])).first()
        company_id = company.id if company else None
    elif scope == "client_project" and suggested.get("client_project"):
        project = db.query(ClientProject).filter(ClientProject.name.ilike(suggested["client_project"])).first()
        if project:
            client_project_id, company_id = project.id, project.company_id
    if scope == "company" and company_id is None or scope == "client_project" and client_project_id is None:
        scope = "country"  # the agent named a record that does not exist
    return scope, company_id, client_project_id


def import_agent_output(
    db: Session,
    *,
    kind: str,
    title: str,
    date_from: date,
    date_to: date | None,
    participant_emails: list[str],
    memes: list[dict],
    lines: list[dict] | None = None,
    mock_id: str | None = None,
    uploader: User | None = None,
) -> Source:
    """Store one source with its participants and the valid memes; send the notifications. The caller commits."""
    users = {u.email: u for u in db.query(User).filter(User.email.in_(participant_emails))}
    source = Source(
        kind=kind,
        title=title,
        date_from=date_from,
        date_to=date_to,
        mock_id=mock_id,
        uploader_id=uploader.id if uploader else None,
        raw_ref=mock_id,
        raw_expires_at=datetime.utcnow() + timedelta(days=setting(db, "parser_raw_retention_days")),
    )
    db.add(source)
    db.flush()
    for u in users.values():
        db.add(SourceParticipant(source_id=source.id, user_id=u.id))
    db.flush()

    threshold = setting(db, "parser_confidence_threshold")
    candidates: set[int] = set()
    created: list[Meme] = []
    for data in memes:
        speaker = users.get(data.get("speaker", ""))
        quotes = data.get("quotes") or []
        if speaker is None or not quotes or float(data.get("confidence", 0)) < threshold:
            continue  # FR-MA3, FR-MA4, FR-MA7: no quote, no known speaker or low confidence: not a meme
        suggested = data.get("suggested", {})
        scope, company_id, client_project_id = _scope_pointers(db, suggested)
        statement = data["statement"].strip()
        meme_title = (suggested.get("title") or statement[:80]).strip()
        meme = Meme(
            source_id=source.id,
            speaker_id=speaker.id,
            kind=data.get("kind", "fact"),
            statement=statement,
            title=meme_title,
            category_name=suggested.get("category"),
            country=suggested.get("country"),
            scope=scope,
            company_id=company_id,
            client_project_id=client_project_id,
            confidence=float(data.get("confidence", 1.0)),
            sensitive=bool(data.get("sensitive", False)),
            similar_json=json.dumps(find_similar(db, meme_title, statement)),
        )
        db.add(meme)
        db.flush()
        for name in data.get("tags", []):
            try:
                tag = tag_service.get_or_create_tag(db, tag_service.validate_keyword(name), tag_service.KEYWORD)
            except tag_service.TagError:
                continue
            if tag not in meme.tags:
                meme.tags.append(tag)
        for q in quotes:
            who = users.get(q.get("speaker", ""), speaker)
            db.add(Quote(
                meme_id=meme.id, user_id=who.id, text=q["text"], at=q["at"],
                context_json=json.dumps(_context(lines or [], q["at"])),
            ))

        hints = {speaker.id: data.get("speaker_basis_hint")}
        for c in data.get("confirmed_by", []):
            u = users.get(c.get("user", ""))
            q = c.get("quote") or {}
            if u is None or u.id == speaker.id or u.id in hints or not q.get("text"):
                continue  # a confirmer is another participant with a confirmation quote (BR-M2, BR-M6)
            hints[u.id] = c.get("basis_hint")
            db.add(Quote(
                meme_id=meme.id, user_id=u.id, text=q["text"], at=q.get("at", ""), is_confirmation=True,
                context_json=json.dumps(_context(lines or [], q.get("at", ""))),
            ))
        db.flush()
        for uid, hint in hints.items():
            sug = Suggestion(
                meme_id=meme.id,
                user_id=uid,
                role="speaker" if uid == speaker.id else "confirmer",
                basis_hint_json=json.dumps(hint) if hint else None,
            )
            db.add(sug)
            db.flush()
            db.add(SuggestionEvent(suggestion_id=sug.id, action="created"))
            candidates.add(uid)
            db.add(Notification(
                user_id=uid,
                event_type="suggestion_received",
                title="You have a new suggestion",
                body=f"From {source.title}: {meme_title}",
                link=f"/information?tab=yours&section=to_decide&suggestion={sug.id}",
            ))
        created.append(meme)

    if created:
        for uid in {p.user_id for p in source.participants}:
            db.add(Notification(
                user_id=uid,
                event_type="memes_ready",
                title="Memes ready",
                body=f"{len(created)} memes were extracted from {source.title}.",
                link="/information?tab=" + ("yours" if uid in candidates else "others"),
            ))
    db.flush()
    return source


def load_mock_sources(db: Session) -> int:
    """Run the stub agent over every source in mock_data/sources that has not been imported yet."""
    index_path = SOURCES_DIR / "index.json"
    if not index_path.exists():
        return 0
    imported = 0
    have = {m for (m,) in db.query(Source.mock_id).filter(Source.mock_id.isnot(None))}
    for meta in json.loads(index_path.read_text(encoding="utf-8")):
        if meta["id"] in have:
            continue
        expected = json.loads((SOURCES_DIR / meta["expected"]).read_text(encoding="utf-8"))
        path = SOURCES_DIR / meta["file"]
        if meta["type"] == "meeting":
            emails = meta.get("participants", [])
            lines = _meeting_lines(path)
            start, end = meta["date"], None
        else:
            chat = json.loads(path.read_text(encoding="utf-8"))
            emails = [m["email"] for m in chat.get("members", [])]
            lines = _chat_lines(path)
            start, end = meta["date_from"], meta.get("date_to")
        import_agent_output(
            db,
            kind=meta["type"],
            title=meta["title"],
            date_from=date.fromisoformat(start),
            date_to=date.fromisoformat(end) if end else None,
            participant_emails=emails,
            memes=expected["memes"],
            lines=lines,
            mock_id=meta["id"],
        )
        imported += 1
    db.commit()
    return imported


def purge_expired_sources(db: Session, now: datetime | None = None) -> int:
    """BR-M7: the raw transcript or chat export is dropped once its retention has passed. Memes and their stored quotes
    (with the context cut from them at import) stay. Idempotent; returns the number purged."""
    now = now or datetime.utcnow()
    rows = (
        db.query(Source)
        .filter(Source.raw_purged_at.is_(None), Source.raw_expires_at.isnot(None), Source.raw_expires_at <= now)
        .all()
    )
    for s in rows:
        s.raw_ref = None
        s.raw_purged_at = now
    db.commit()
    return len(rows)
