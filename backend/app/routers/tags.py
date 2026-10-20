from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, require_roles
from app.models import Tag, User
from app.services import tags as tag_service

router = APIRouter(tags=["tags"])


class TagRename(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class TagMerge(BaseModel):
    into_id: int


def _get_tag(db: Session, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def _out(db: Session, tag: Tag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "tag_type": tag.tag_type,
        "entry_count": tag_service.usage_count(db, tag.id),
    }


@router.get("/tags")
def list_tags(
    q: str | None = Query(None, description="Suggest existing tags matching this text"),
    type: str | None = Query(None, pattern="^(keyword|automatic)$"),
    limit: int = Query(10, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Existing tags, matching ``q`` and most used first. Used for suggestions while typing a tag."""
    return tag_service.suggest_tags(db, q, type, limit)


@router.patch("/admin/tags/{tag_id}")
def rename_tag(
    tag_id: int,
    body: TagRename,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    tag = _get_tag(db, tag_id)
    try:
        tag_service.rename_tag(db, tag, body.name)
    except tag_service.TagError as exc:
        db.rollback()
        # A name clash is a conflict (merge instead); everything else is a bad request.
        code = 409 if "already exists" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc))
    db.commit()
    return _out(db, tag)


@router.post("/admin/tags/{tag_id}/merge")
def merge_tag(
    tag_id: int,
    body: TagMerge,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    """Merge this tag into another: all its entries end up linked to the target, the tag disappears."""
    source = _get_tag(db, tag_id)
    target = _get_tag(db, body.into_id)
    try:
        tag_service.merge_tags(db, source, target)
    except tag_service.TagError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _out(db, target)
