from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, User
from app.schemas import EntryOut
from app.services.search import SearchFilters, search_entries, search_facets

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/facets")
def facets(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    """Options for the filter panel on the search page."""
    return search_facets(db)


@router.get("")
def search(
    q: str | None = Query(None),
    country: list[str] | None = Query(None),
    department: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    scope: list[str] | None = Query(None),
    verifier_role: list[str] | None = Query(None),
    author: list[int] | None = Query(None),
    team: list[int] | None = Query(None),
    project: list[int] | None = Query(None),
    updated_from: date | None = Query(None),
    updated_to: date | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EntryOut]:
    from app.routers.entries import _entry_options, _entry_to_out

    filters = SearchFilters(
        countries=country or [],
        departments=department or [],
        categories=category or [],
        statuses=status or [],
        scopes=scope or [],
        verifier_roles=verifier_role or [],
        author_ids=author or [],
        team_ids=team or [],
        project_ids=project or [],
        updated_from=updated_from,
        updated_to=updated_to,
    )
    entries = search_entries(
        db,
        query=q,
        user_country=user.country,
        filters=filters,
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
