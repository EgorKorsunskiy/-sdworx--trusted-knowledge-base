"""Save extracted memes to the database and ask their authors (FR-MO1, FR-MN1)."""
from collections import Counter
from datetime import date

from sqlalchemy.orm import Session

from app.ai_parser.pipeline import Extraction
from app.models import AuthorshipRequest, Meme, MemeSource, MemeSourceParticipant, Notification, User


def _count(n: int) -> str:
    return f"{n} meme{'s' if n > 1 else ''}"


def _short(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def save_memes(
    db: Session,
    *,
    key: str,
    type: str,
    title: str,
    participants: list[str],
    memes: list[dict],
    meeting_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    uploaded_by_id: int | None = None,
    generator: dict | None = None,
) -> MemeSource:
    """Store one source with its memes, send an authorship request to every speaker and
    confirmer, and tell all participants that the memes are ready."""
    users = {u.email: u for u in db.query(User).filter(User.email.in_(set(participants)))}
    source = MemeSource(
        key=key, type=type, title=title, meeting_date=meeting_date, date_from=date_from,
        date_to=date_to, uploaded_by_id=uploaded_by_id, generator=generator,
    )
    db.add(source)
    db.flush()
    for user in users.values():
        db.add(MemeSourceParticipant(source_id=source.id, user_id=user.id))

    stored, requests = 0, Counter()
    for data in memes:
        speaker = users.get(data["speaker"])
        if speaker is None:
            continue  # only a participant with an account can own a meme
        meme = Meme(
            key=data["id"], source_id=source.id, speaker_id=speaker.id, data=data,
            day=date.fromisoformat(data["day"]) if data.get("day") else None,
        )
        db.add(meme)
        db.flush()
        stored += 1
        candidates = [(speaker, "speaker")] + [
            (users[c["user"]], "confirmer") for c in data.get("confirmed_by", []) if c["user"] in users
        ]
        for user, role in candidates:
            db.add(AuthorshipRequest(meme_id=meme.id, user_id=user.id, role=role))
            requests[user.id] += 1

    if stored:
        for user in users.values():
            n = requests[user.id]
            if n:
                event, note = "authorship_request", f"{_count(n)} from “{_short(title)}” {'await' if n > 1 else 'awaits'} your answer"
            else:
                event, note = "memes_ready", f"{_count(stored)} from “{_short(title)}” {'are' if stored > 1 else 'is'} ready"
            db.add(Notification(
                user_id=user.id, event_type=event, title=note,
                body="Accept or decline your authorship requests." if n else "Vote on how useful your colleagues' memes are.",
                link=f"/memes?source={key}",
            ))
    db.commit()
    return source


def save_extraction(db: Session, extraction: Extraction, uploaded_by_id: int | None = None) -> MemeSource:
    source = extraction.source
    return save_memes(
        db,
        key=source.id, type=source.type, title=source.title,
        participants=list(source.participants), memes=extraction.memes,
        meeting_date=source.meeting_date, date_from=source.date_from, date_to=source.date_to,
        uploaded_by_id=uploaded_by_id, generator=extraction.generator,
    )
