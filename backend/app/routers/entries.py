from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user, get_current_user_optional, load_user, user_to_out
from app.models import Category, Entry, EntryVersion, Tag, User, VersionStatus
from app.schemas import (
    EntryCreate,
    EntryDetailOut,
    EntryOut,
    EntryUpdate,
    EntryVersionBriefOut,
    EntryVersionOut,
    PersonBrief,
)
from app.services.permissions import can_edit_own_unverified, get_verifiers_for_entry
from app.services.public_id import make_public_id

router = APIRouter(prefix="/entries", tags=["entries"])


def _entry_options():
    return [
        joinedload(Entry.author).joinedload(User.roles),
        joinedload(Entry.category),
        joinedload(Entry.team),
        joinedload(Entry.tags),
        joinedload(Entry.versions).joinedload(EntryVersion.edited_by).joinedload(User.roles),
    ]


def _person(user: User) -> PersonBrief:
    role = user.roles[0].role if user.roles else None
    return PersonBrief(
        id=user.id,
        display_name=user.display_name,
        title=user.title,
        department=user.department,
        role=role,
    )


def _version_to_out(version: EntryVersion) -> EntryVersionOut:
    return EntryVersionOut(
        id=version.id,
        version_number=version.version_number,
        title=version.title,
        body=version.body,
        justification=version.justification,
        status=version.status,
        change_note=version.change_note,
        edited_by=user_to_out(version.edited_by),
        created_at=version.created_at,
    )


def _who_to_ask(db: Session, entry: Entry) -> list[PersonBrief]:
    people: list[PersonBrief] = []
    if entry.author:
        people.append(_person(entry.author))
    for v in get_verifiers_for_entry(db, entry):
        if entry.author and v.id == entry.author.id:
            continue
        people.append(_person(v))
    return people


def _entry_to_out(
    db: Session,
    entry: Entry,
    current_user: User | None = None,
) -> EntryOut:
    current = entry.versions[-1] if entry.versions else None
    can_edit = False
    if current_user and current:
        can_edit = can_edit_own_unverified(current_user, entry, current)
    return EntryOut(
        id=entry.id,
        public_id=entry.public_id,
        scope=entry.scope,
        department=entry.department,
        country=entry.country,
        category=entry.category,
        author=user_to_out(entry.author),
        team=(
            {"id": entry.team.id, "name": entry.team.name, "department": entry.team.department}
            if entry.team
            else None
        ),
        tags=entry.tags,
        current_version=_version_to_out(current) if current else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        can_edit=can_edit,
        who_to_ask=_who_to_ask(db, entry),
    )


def _entry_detail_out(
    db: Session,
    entry: Entry,
    current_user: User | None = None,
) -> EntryDetailOut:
    base = _entry_to_out(db, entry, current_user)
    return EntryDetailOut(
        **base.model_dump(),
        versions=[
            EntryVersionBriefOut(
                id=v.id,
                version_number=v.version_number,
                title=v.title,
                status=v.status,
                created_at=v.created_at,
            )
            for v in entry.versions
        ],
    )


def _reload(db: Session, entry_id: int) -> Entry:
    entry = db.query(Entry).filter(Entry.id == entry_id).options(*_entry_options()).first()
    assert entry is not None
    return entry


def _ensure_tag(db: Session, name: str) -> Tag:
    tag = db.query(Tag).filter(Tag.name == name).first()
    if tag is None:
        tag = Tag(name=name)
        db.add(tag)
        db.flush()
    return tag


def _apply_auto_tags(db: Session, entry: Entry, user: User) -> None:
    role = user.roles[0].role if user.roles else "employee"
    auto = [
        f"author:{user.display_name}",
        f"department:{user.department or 'unknown'}",
        f"role:{role}",
        f"date:{datetime.utcnow().date().isoformat()}",
    ]
    existing = {t.name for t in entry.tags}
    for name in auto:
        if name not in existing:
            entry.tags.append(_ensure_tag(db, name))
            existing.add(name)


@router.post("", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntryOut:
    author = load_user(db, user.id)
    assert author is not None

    title = body.title.strip()
    content = body.body.strip()
    country = body.country.strip()
    if not title or not content or not country:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title, content and country are required",
        )

    category = db.query(Category).filter(Category.id == body.category_id).first()
    if category is None:
        raise HTTPException(status_code=422, detail="Category not found")

    public_id = make_public_id(db, country, category.name)

    team_id = None
    for m in author.memberships:
        if m.is_primary and m.team_id:
            team_id = m.team_id
            break
    if team_id is None and author.memberships:
        team_id = author.memberships[0].team_id

    entry = Entry(
        public_id=public_id,
        scope=body.scope,
        department=author.department or "General",
        country=country,
        category_id=category.id,
        author_id=author.id,
        team_id=team_id,
        is_published=True,
    )
    db.add(entry)
    db.flush()

    version = EntryVersion(
        entry_id=entry.id,
        version_number=1,
        title=title,
        body=content,
        justification=body.justification.strip() if body.justification else None,
        status=VersionStatus.UNVERIFIED.value,
        change_note="Created",
        edited_by_id=author.id,
    )
    db.add(version)

    for kw in body.keywords:
        name = kw.strip()
        if not name:
            continue
        entry.tags.append(_ensure_tag(db, name))

    _apply_auto_tags(db, entry, author)

    db.commit()
    entry = _reload(db, entry.id)
    return _entry_to_out(db, entry, current_user=author)


@router.get("/{public_id}", response_model=EntryDetailOut)
def get_entry(
    public_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> EntryDetailOut:
    entry = (
        db.query(Entry)
        .filter(Entry.public_id == public_id)
        .options(*_entry_options())
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return _entry_detail_out(db, entry, current_user=user)


@router.get("/{public_id}/versions/{version_number}", response_model=EntryVersionOut)
def get_version(
    public_id: str,
    version_number: int,
    db: Session = Depends(get_db),
) -> EntryVersionOut:
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    version = (
        db.query(EntryVersion)
        .filter(EntryVersion.entry_id == entry.id, EntryVersion.version_number == version_number)
        .options(joinedload(EntryVersion.edited_by).joinedload(User.roles))
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return _version_to_out(version)


@router.patch("/{public_id}", response_model=EntryOut)
def update_entry(
    public_id: str,
    body: EntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntryOut:
    entry = (
        db.query(Entry)
        .filter(Entry.public_id == public_id)
        .options(*_entry_options())
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    current = entry.versions[-1]
    if not can_edit_own_unverified(user, entry, current):
        raise HTTPException(status_code=403, detail="Cannot edit this version")

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Title is required")
        current.title = title
    if body.body is not None:
        content = body.body.strip()
        if not content:
            raise HTTPException(status_code=422, detail="Content is required")
        current.body = content
    if body.justification is not None:
        current.justification = body.justification.strip() or None
    current.change_note = "Updated draft"

    if body.keywords is not None:
        # Keep auto-tags; replace keywords
        auto_prefix = ("author:", "department:", "role:", "date:")
        entry.tags = [t for t in entry.tags if t.name.startswith(auto_prefix)]
        for kw in body.keywords:
            name = kw.strip()
            if not name:
                continue
            entry.tags.append(_ensure_tag(db, name))
        _apply_auto_tags(db, entry, user)

    entry.updated_at = datetime.utcnow()
    db.commit()
    entry = _reload(db, entry.id)
    return _entry_to_out(db, entry, current_user=user)
