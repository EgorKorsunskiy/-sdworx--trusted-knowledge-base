from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Basis, ClientProject, Entry, EntryContact, User
from app.schemas import BasisBulkIn
from app.services import contacts as contact_service
from app.services.scopes import scope_label

router = APIRouter(tags=["responsibilities"])


def _item(c: EntryContact) -> dict:
    e = c.entry
    current = e.versions[-1]
    return {
        "public_id": e.public_id,
        "title": current.title,
        "status": current.status,
        "role": c.role,  # author | co_author | contributor
        "basis": c.basis,
        "source": c.source,
        "scope": scope_label(e.scope, e.company, e.client_project),
        "category": e.category.name if e.category else None,
        "updated_at": e.updated_at,
    }


@router.get("/people/{user_id}/responsibilities")
def get_responsibilities(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """The Responsibilities tab of a profile (FR-K8, FR-K9): areas of responsibility, then the entries the person
    authored or co-authored, grouped into Responsible and Relayed. Only entries a viewer can find in search."""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")
    rows = (
        db.query(EntryContact)
        .join(Entry, Entry.id == EntryContact.entry_id)
        .options(
            joinedload(EntryContact.entry).joinedload(Entry.versions),
            joinedload(EntryContact.entry).joinedload(Entry.category),
            joinedload(EntryContact.entry).joinedload(Entry.company),
            joinedload(EntryContact.entry).joinedload(Entry.client_project).joinedload(ClientProject.company),
            joinedload(EntryContact.entry).joinedload(Entry.tags),
        )
        .filter(EntryContact.user_id == user_id, Entry.is_published.is_(True))
        .order_by(Entry.updated_at.desc())
        .all()
    )
    responsible = [c for c in rows if c.basis == Basis.RESPONSIBLE.value]
    relayed = [c for c in rows if c.basis == Basis.RELAYED.value]

    # Areas of responsibility come from the entries where the person is Responsible
    def uniq(values):
        return sorted({v for v in values if v}, key=str.lower)

    tags: dict[int, str] = {}
    for c in responsible:
        for t in c.entry.tags:
            if t.tag_type == "keyword":
                tags[t.id] = t.name
    areas = {
        "categories": uniq(c.entry.category.name for c in responsible if c.entry.category),
        "countries": uniq(c.entry.country for c in responsible),
        "scopes": uniq(
            scope_label(c.entry.scope, None, None) for c in responsible if not c.entry.company and not c.entry.client_project
        ),
        "companies": uniq(c.entry.company.name for c in responsible if c.entry.company),
        "client_projects": uniq(c.entry.client_project.name for c in responsible if c.entry.client_project),
        "tags": [{"id": i, "name": n} for i, n in sorted(tags.items(), key=lambda kv: kv[1])],
    }
    return {
        "areas": areas,
        "responsible": [_item(c) for c in responsible],
        "relayed": [_item(c) for c in relayed],
    }


@router.patch("/me/responsibilities")
def change_my_basis(
    body: BasisBulkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Change one's own basis for several entries at once (FR-K10), e.g. to hand over responsibility.
    All or nothing; each change is logged and creates no new version."""
    entries = db.query(Entry).filter(Entry.public_id.in_(body.public_ids)).all()
    found = {e.public_id: e for e in entries}
    missing = [p for p in body.public_ids if p not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Entry not found: {', '.join(missing)}")
    try:
        for entry in entries:
            contact_service.change_basis(db, entry, user, body.basis, body.source)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except contact_service.BasisError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return {"changed": len(entries)}
