from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Category, User
from app.schemas import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CategoryOut]:
    cats = db.query(Category).order_by(Category.name).all()
    return [CategoryOut.model_validate(c) for c in cats]
