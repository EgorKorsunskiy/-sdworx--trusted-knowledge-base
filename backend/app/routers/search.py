from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user_optional
from app.models import Entry, User
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
    from app.routers.entries import _entry_options, _entry_to_out

    entries = search_entries(
        db,
        query=q,
        user_country="BE" if user else None,
        country=country,
        department=department,
        category=category,
        status=status,
    )
    if not entries:
        return []
    loaded = (
        db.query(Entry)
        .options(*_entry_options())
        .filter(Entry.id.in_([e.id for e in entries]))
        .all()
    )
    by_id = {e.id: e for e in loaded}
    return [_entry_to_out(db, by_id[e.id], current_user=user) for e in entries if e.id in by_id]
