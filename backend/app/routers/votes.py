from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, user_to_out
from app.models import EntryVersion, Notification, SystemSetting, UsageVote, User
from app.schemas import UsageVoteCreate, UsageVoteOut

router = APIRouter(prefix="/entries/{public_id}/votes", tags=["votes"])


def _to_out(vote: UsageVote) -> UsageVoteOut:
    return UsageVoteOut(
        id=vote.id,
        user=user_to_out(vote.user),
        used_at=vote.used_at,
        where_ref=vote.where_ref,
        is_correct=vote.is_correct,
        created_at=vote.created_at,
    )


def _reputation_value(db: Session, key: str) -> int:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return int(setting.value) if setting else 0


@router.get("", response_model=list[UsageVoteOut])
def list_votes(
    public_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[UsageVoteOut]:
    version = (
        db.query(EntryVersion)
        .join(EntryVersion.entry)
        .filter(EntryVersion.entry.has(public_id=public_id))
        .order_by(EntryVersion.version_number.desc())
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    votes = (
        db.query(UsageVote)
        .filter(UsageVote.version_id == version.id, UsageVote.withdrawn_at.is_(None))
        .all()
    )
    return [_to_out(v) for v in votes]


@router.post("", response_model=UsageVoteOut)
def create_vote(
    public_id: str,
    body: UsageVoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UsageVoteOut:
    version = (
        db.query(EntryVersion)
        .join(EntryVersion.entry)
        .filter(EntryVersion.entry.has(public_id=public_id))
        .order_by(EntryVersion.version_number.desc())
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    if version.entry.author_id == user.id or version.edited_by_id == user.id:
        raise HTTPException(status_code=403, detail="Cannot vote on own entry")

    existing = (
        db.query(UsageVote)
        .filter(UsageVote.version_id == version.id, UsageVote.user_id == user.id, UsageVote.withdrawn_at.is_(None))
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already reported usage for this version")

    vote = UsageVote(
        version_id=version.id,
        user_id=user.id,
        used_at=body.used_at,
        where_ref=body.where_ref.strip(),
        is_correct=body.is_correct,
    )
    db.add(vote)

    if vote.is_correct:
        points = _reputation_value(db, "reputation_vote")
        version.edited_by.reputation += points
    else:
        # Notify author and last verifier
        last_verifier_id = None
        for ver in reversed(version.verifications):
            if ver.action == "verify":
                last_verifier_id = ver.verifier_id
                break
        db.add(Notification(
            user_id=version.entry.author_id,
            event_type="incorrect_vote",
            title="Incorrect usage reported",
            body=f"Someone reported {public_id} was incorrect when used.",
        ))
        if last_verifier_id:
            db.add(Notification(
                user_id=last_verifier_id,
                event_type="incorrect_vote",
                title="Incorrect usage reported",
                body=f"{public_id} was marked incorrect by a user.",
            ))

    db.commit()
    db.refresh(vote)
    return _to_out(vote)


@router.delete("/{vote_id}")
def withdraw_vote(
    public_id: str,
    vote_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    vote = (
        db.query(UsageVote)
        .join(UsageVote.version)
        .join(EntryVersion.entry)
        .filter(EntryVersion.entry.has(public_id=public_id))
        .filter(UsageVote.id == vote_id)
        .first()
    )
    if vote is None:
        raise HTTPException(status_code=404, detail="Vote not found")
    if vote.user_id != user.id:
        raise HTTPException(status_code=403, detail="Can only withdraw your own vote")
    vote.withdrawn_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"status": "withdrawn"}
