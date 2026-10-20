"""Publishing an AI-parser meme through the Add entry form (FR-MP1 to FR-MP10, BR-M3, BR-M5)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Category,
    Entry,
    Meme,
    MemeStatus,
    Suggestion,
    SuggestionState,
    User,
)
from app.services import contacts as contact_service
from app.services import information as info


def source_reference(meme: Meme, basis: str | None = None, basis_source: str | None = None) -> str:
    """The justification prefill: a reference to the source (type, title, date), never quotes or transcript text.
    A relayed author's own source is added (FR-MP4)."""
    src = meme.source
    kind = "meeting" if src.kind == "meeting" else "group chat"
    when = src.date_from.isoformat() if not src.date_to else f"{src.date_from.isoformat()} to {src.date_to.isoformat()}"
    text = f"From a {kind}: {src.title}, {when}."
    if basis == "relayed" and basis_source:
        text += f" Source: {basis_source}"
    return text


def prefill(db: Session, sug: Suggestion) -> dict:
    """What the Add entry form is prefilled with for an approved suggestion (FR-MP2, FR-MP3, FR-MS22)."""
    meme = sug.meme
    category = (
        db.query(Category).filter(Category.name == meme.category_name).first() if meme.category_name else None
    )
    published = meme.status == MemeStatus.PUBLISHED.value
    out = {
        "suggestion_id": sug.id,
        "meme_id": meme.id,
        "already_published": published,
        "entry_public_id": meme.entry.public_id if published and meme.entry else None,
        "title": meme.title,
        "body": meme.statement,
        "justification": source_reference(meme, sug.basis, sug.basis_source),
        "category_id": category.id if category else None,
        "country": meme.country,
        "scope": meme.scope,
        "company_id": meme.company_id,
        "client_project_id": meme.client_project_id,
        "keywords": [t.name for t in meme.tags if t.tag_type == "keyword"],
        "basis": sug.basis,
        "basis_source": sug.basis_source,
        "sensitive": meme.sensitive,
        "source": {
            "kind": meme.source.kind,
            "title": meme.source.title,
            "date_from": meme.source.date_from,
            "date_to": meme.source.date_to,
        },
        # Everyone's answer, so the author knows who is pending and who objected (FR-MP3)
        "candidates": [
            {
                "owner": {"id": s.user.id, "display_name": s.user.display_name},
                "role": s.role,
                "state": s.state,
                "label": info.suggestion_out(s, sug.user)["label"],
                "reason": s.decline_reason,
                "is_me": s.id == sug.id,
            }
            for s in meme.suggestions
        ],
        # The approved authors who will be recorded as co-authors of the entry (FR-MP6)
        "co_authors": [
            {"id": s.user.id, "display_name": s.user.display_name, "basis": s.basis, "source": s.basis_source}
            for s in meme.suggestions
            if s.state == SuggestionState.ACCEPTED.value and s.id != sug.id
        ],
    }
    return out


def check_can_publish(db: Session, user: User, suggestion_id: int, sensitive_confirmed: bool) -> Suggestion:
    """Only a candidate who approved can add the meme, and only once (first save wins); sensitive text must be
    confirmed clean (BR-M5). Raises ParserError."""
    sug = info.get_own_suggestion(db, user, suggestion_id)
    meme = sug.meme
    if meme.status == MemeStatus.PUBLISHED.value:
        public_id = meme.entry.public_id if meme.entry else "an entry"
        raise info.ParserError(f"This meme was already published as {public_id}", 409)
    if sug.state != SuggestionState.ACCEPTED.value:
        raise info.ParserError("Approve your suggestion first; only an approved author can add it to the repository", 403)
    if meme.sensitive and not sensitive_confirmed:
        raise info.ParserError(
            "This meme was flagged as containing personal or confidential customer data. Edit the text and confirm "
            "that it no longer contains any.", 422,
        )
    return sug


def publish(db: Session, sug: Suggestion, entry: Entry, saver: User, basis: str, basis_source: str | None) -> None:
    """After the entry was created: link it to the meme, record every approved author, close the other suggestions."""
    meme = sug.meme
    sug.basis, sug.basis_source = basis, basis_source  # what the saving author finally stated on the form
    meme.entry_id = entry.id
    meme.status = MemeStatus.PUBLISHED.value
    meme.published_at = datetime.utcnow()
    for s in meme.suggestions:
        if s.state == SuggestionState.ACCEPTED.value and s.user_id != saver.id:
            contact_service.add_contact(db, entry, s.user_id, s.basis, s.basis_source, role="co_author")
    db.flush()
    db.refresh(meme)
    info.close_open_suggestions(db, meme)
    link = f"/entries/{entry.public_id}"
    told = {saver.id}
    for s in meme.suggestions:
        if s.state == SuggestionState.ACCEPTED.value and s.user_id not in told:
            info.notify(db, s.user_id, "meme_published", "Your meme was published",
                        f"{saver.display_name} added “{meme.title}” as {entry.public_id}. You are a co-author.", link)
            told.add(s.user_id)
