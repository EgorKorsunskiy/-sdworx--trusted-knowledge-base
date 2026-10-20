from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, user_to_out
from app.models import Entry, EntryContact, PullRequest, User

router = APIRouter(prefix="/me", tags=["contributions"])


@router.get("/contributions")
def my_contributions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entries = db.query(Entry).filter(Entry.author_id == user.id).order_by(Entry.updated_at.desc()).all()
    # Entries the user co-authored (through the AI parser) are listed too, marked as co-author
    co_authored = (
        db.query(Entry)
        .join(EntryContact, EntryContact.entry_id == Entry.id)
        .filter(EntryContact.user_id == user.id, EntryContact.role == "co_author")
        .order_by(Entry.updated_at.desc())
        .all()
    )
    prs = db.query(PullRequest).filter(PullRequest.author_id == user.id).order_by(PullRequest.created_at.desc()).all()
    return {
        "entries": [
            {
                "public_id": e.public_id,
                "title": e.versions[-1].title,
                "status": e.versions[-1].status,
                "updated_at": e.updated_at,
            }
            for e in entries
        ],
        "co_authored": [
            {
                "public_id": e.public_id,
                "title": e.versions[-1].title,
                "status": e.versions[-1].status,
                "updated_at": e.updated_at,
                "author": {"id": e.author.id, "display_name": e.author.display_name},
            }
            for e in co_authored
        ],
        "pull_requests": [
            {
                "id": p.id,
                "entry_public_id": p.entry.public_id,
                "title": p.title,
                "entry_title": p.entry.versions[-1].title,
                "change_note": p.change_note,
                "status": p.status,
                "created_at": p.created_at,
                "resolved_at": p.resolved_at,
            }
            for p in prs
        ],
        "reputation": user.reputation,
        "user": user_to_out(user),
    }
