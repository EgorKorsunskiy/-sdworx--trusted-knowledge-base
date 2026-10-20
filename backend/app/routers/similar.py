from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import User
from app.services.similarity import find_similar

# Must be registered BEFORE the entries router, otherwise /entries/similar is captured by /entries/{public_id}.
router = APIRouter(prefix="/entries/similar", tags=["similarity"])


@router.get("")
def similar_entries(
    title: str = Query(...),
    body: str = Query(...),
    threshold: float | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    return find_similar(db, title, body, threshold)
