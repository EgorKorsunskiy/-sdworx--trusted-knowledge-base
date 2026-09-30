from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.similarity import find_similar

router = APIRouter(prefix="/entries/similar", tags=["similarity"])


@router.get("")
def similar_entries(
    title: str = Query(...),
    body: str = Query(...),
    threshold: float | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict]:
    return find_similar(db, title, body, threshold)
