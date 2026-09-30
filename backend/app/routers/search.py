from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user_optional
from app.models import User
from app.schemas import EntryOut
from app.services.search import search_entries

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str | None = Query(None),
    country: str | None = Query(None),
    department: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> list[EntryOut]:
    from app.routers.entries import _entry_to_out
    entries = search_entries(
        db,
        query=q,
        user_country=user.country if user else None,
        country=country,
        department=department,
        category=category,
        status=status,
    )
    return [_entry_to_out(e) for e in entries]
