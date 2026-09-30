from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, user_to_out
from app.models import Entry, PullRequest, User

router = APIRouter(prefix="/me", tags=["contributions"])


@router.get("/contributions")
def my_contributions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entries = db.query(Entry).filter(Entry.author_id == user.id).order_by(Entry.updated_at.desc()).all()
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
        "pull_requests": [
            {
                "id": p.id,
                "entry_public_id": p.entry.public_id,
                "title": p.title,
                "status": p.status,
                "created_at": p.created_at,
            }
            for p in prs
        ],
        "reputation": user.reputation,
        "user": user_to_out(user),
    }
