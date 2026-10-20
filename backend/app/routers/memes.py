"""Memes of the meetings and chats a user took part in, and their authorship requests.

Only participants of a source see its memes (BR-M1); everyone else gets 404.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import (
    AuthorshipRequest,
    AuthorshipStatus,
    Meme,
    MemeSource,
    MemeSourceParticipant,
    MemeStatus,
    Notification,
    User,
)
from app.schemas import AcceptAuthorship, DeclineAuthorship

router = APIRouter(prefix="/memes", tags=["memes"])

CONTRACT_FIELDS = ("kind", "statement", "suggested", "tags", "quotes", "confirmed_by", "confidence", "sensitive", "similar_entries")


def _visible(db: Session, user: User):
    """Memes of the sources the user participated in."""
    sources = db.query(MemeSourceParticipant.source_id).filter(MemeSourceParticipant.user_id == user.id)
    return (
        db.query(Meme)
        .options(
            joinedload(Meme.source),
            joinedload(Meme.speaker),
            joinedload(Meme.requests).joinedload(AuthorshipRequest.user),
        )
        .filter(Meme.source_id.in_(sources))
    )


def _person(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name}


def _meme_out(meme: Meme, user: User) -> dict:
    source: MemeSource = meme.source
    mine = next((r for r in meme.requests if r.user_id == user.id), None)
    hint = None
    if mine:
        # The agent's suggestion prefills the basis the author chooses (FR-MO16)
        if mine.role == "speaker":
            hint = meme.data.get("speaker_basis_hint")
        else:
            email = mine.user.email
            hint = next((c.get("basis_hint") for c in meme.data.get("confirmed_by", []) if c["user"] == email), None)
    return {
        "id": meme.id,
        "key": meme.key,
        "status": meme.status,
        "day": meme.day.isoformat() if meme.day else None,
        "source": {
            "key": source.key,
            "type": source.type,
            "title": source.title,
            "date": source.meeting_date.isoformat() if source.meeting_date else None,
            "date_from": source.date_from.isoformat() if source.date_from else None,
            "date_to": source.date_to.isoformat() if source.date_to else None,
        },
        "speaker": _person(meme.speaker),
        **{k: meme.data.get(k) for k in CONTRACT_FIELDS},
        "candidates": [
            {
                "user": _person(r.user),
                "role": r.role,
                "status": r.status,
                "basis": r.basis,
                "basis_source": r.basis_source,
                "decline_reason": r.decline_reason,
            }
            for r in meme.requests
        ],
        "my_request": {"role": mine.role, "status": mine.status, "basis_hint": hint} if mine else None,
    }


def _pending_first(meme: Meme, user: User) -> tuple:
    mine = next((r for r in meme.requests if r.user_id == user.id), None)
    return (not (mine and mine.status == AuthorshipStatus.PENDING.value), -meme.id)


@router.get("")
def list_memes(
    tab: Literal["mine", "colleagues"] = Query("mine"),
    source_type: list[Literal["meeting", "chat"]] | None = Query(None, alias="type"),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """My memes: where I am the speaker or a confirmer. Colleagues' memes: all others of my sources (FR-MS3)."""
    q = _visible(db, user)
    if source_type:
        q = q.filter(Meme.source.has(MemeSource.type.in_(source_type)))
    if source:
        q = q.filter(Meme.source.has(MemeSource.key == source))
    mine = Meme.requests.any(AuthorshipRequest.user_id == user.id)
    q = q.filter(mine if tab == "mine" else ~mine)
    memes = q.all()
    memes.sort(key=lambda m: _pending_first(m, user))
    return [_meme_out(m, user) for m in memes]


@router.get("/requests/pending")
def pending_requests(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """Memes waiting for my answer as speaker or confirmer."""
    memes = (
        _visible(db, user)
        .filter(Meme.requests.any((AuthorshipRequest.user_id == user.id) & (AuthorshipRequest.status == AuthorshipStatus.PENDING.value)))
        .order_by(Meme.id.desc())
        .all()
    )
    return [_meme_out(m, user) for m in memes]


def _get(db: Session, user: User, meme_id: int) -> Meme:
    meme = _visible(db, user).filter(Meme.id == meme_id).first()
    if meme is None:
        raise HTTPException(status_code=404, detail="Meme not found")
    return meme


def _my_pending_request(meme: Meme, user: User) -> AuthorshipRequest:
    mine = next((r for r in meme.requests if r.user_id == user.id), None)
    if mine is None:
        raise HTTPException(status_code=403, detail="Only the speaker and the confirmers of a meme are asked")
    if mine.status != AuthorshipStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"You already answered ({mine.status})")
    if meme.status not in (MemeStatus.NEW.value, MemeStatus.PREPARING.value):
        raise HTTPException(status_code=409, detail=f"The meme is {meme.status}")
    return mine


@router.get("/{meme_id}")
def get_meme(meme_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _meme_out(_get(db, user, meme_id), user)


@router.post("/{meme_id}/accept")
def accept_authorship(
    meme_id: int,
    body: AcceptAuthorship,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    meme = _get(db, user, meme_id)
    request = _my_pending_request(meme, user)
    source = (body.source or "").strip()
    if body.basis == "relayed" and not source:
        raise HTTPException(status_code=422, detail="A relayed basis needs a source")
    request.status = AuthorshipStatus.ACCEPTED.value
    request.basis, request.basis_source = body.basis, source or None
    request.responded_at = datetime.utcnow()
    if meme.status == MemeStatus.NEW.value:
        meme.status = MemeStatus.PREPARING.value  # one acceptance is enough (FR-MO3)
    title = meme.data.get("suggested", {}).get("title") or meme.key
    for other in meme.requests:
        if other.user_id != user.id and other.status in (AuthorshipStatus.PENDING.value, AuthorshipStatus.ACCEPTED.value):
            db.add(Notification(
                user_id=other.user_id, event_type="authorship_accepted",
                title=f"{user.display_name} accepted authorship of “{title}”",
                body="The meme is being prepared for publication." if other.status == AuthorshipStatus.ACCEPTED.value
                else "You can still accept and become an author too.",
                link=f"/memes/{meme.id}",
            ))
    db.commit()
    return _meme_out(_get(db, user, meme_id), user)


@router.post("/{meme_id}/decline")
def decline_authorship(
    meme_id: int,
    body: DeclineAuthorship,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    meme = _get(db, user, meme_id)
    request = _my_pending_request(meme, user)
    request.status = AuthorshipStatus.DECLINED.value
    request.decline_reason = body.reason
    request.responded_at = datetime.utcnow()
    if all(r.status == AuthorshipStatus.DECLINED.value for r in meme.requests):
        meme.status = MemeStatus.DECLINED.value  # every candidate declined (FR-MO5)
    db.commit()
    return _meme_out(_get(db, user, meme_id), user)
