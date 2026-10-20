from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user, load_user, user_to_out
from app.models import Category, ClientProject, Entry, EntryContact, Meme, EntryVersion, Notification, RoleType, User, VersionStatus
from app.schemas import (
    BasisIn,
    ContactOut,
    EntryCreate,
    EntryDetailOut,
    EntryOut,
    EntryUpdate,
    EntryVersionBriefOut,
    EntryVersionOut,
    PersonBrief,
)
from app.services.permissions import (
    can_edit_own_unverified,
    get_verifiers_for_entry,
    user_has_role,
)
from app.services import tags as tag_service
from app.services import scopes as scope_service
from app.services import contacts as contact_service
from app.services import information as info_service
from app.services import parser_publish
from app.services.public_id import make_public_id

router = APIRouter(prefix="/entries", tags=["entries"])


def _entry_options():
    return [
        joinedload(Entry.author).joinedload(User.roles),
        joinedload(Entry.category),
        joinedload(Entry.team),
        joinedload(Entry.company),
        joinedload(Entry.client_project).joinedload(ClientProject.company),
        joinedload(Entry.tags),
        joinedload(Entry.contacts).joinedload(EntryContact.user),
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
    who_to_ask = _who_to_ask(db, entry)

    # The note is only for the author, admins and verifiers of this entry.
    note = None
    if entry.difference_note and current_user:
        if (
            entry.author_id == current_user.id
            or user_has_role(current_user, RoleType.ADMIN.value)
            or any(v.id == current_user.id for v in get_verifiers_for_entry(db, entry))
        ):
            note = entry.difference_note
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
        company=entry.company,
        client_project=entry.client_project,
        tags=entry.tags,
        current_version=_version_to_out(current) if current else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        can_edit=can_edit,
        who_to_ask=who_to_ask,
        difference_note=note,
        has_responsible_contact=contact_service.has_responsible_contact(entry),
    )


def _origin(db: Session, entry: Entry, viewer: User | None) -> dict | None:
    """Where an entry from an AI-parser meme came from: "From a meeting / group chat, date" (FR-MP8, FR-MS21).

    Everyone sees the origin line. The meme itself, the co-author request action and the notice for authors are only
    given to participants of the source, so the conversation stays private (BR-M1)."""
    meme = db.query(Meme).filter(Meme.entry_id == entry.id).first()
    if meme is None:
        return None
    src = meme.source
    out = {
        "kind": src.kind,
        "date_from": src.date_from,
        "date_to": src.date_to,
        "is_participant": False,
        "meme_id": None,
    }
    if viewer is None or not info_service.is_participant(db, viewer, src.id):
        return out
    authors = info_service.meme_authors(db, meme)
    viewer_is_author = any(p["user"].id == viewer.id for p in authors)
    my_request = next((r for r in meme.coauthor_requests if r.requester_id == viewer.id), None)
    pending = [r for r in meme.coauthor_requests if r.status == "pending"] if viewer_is_author else []
    out.update(
        is_participant=True,
        meme_id=meme.id,
        is_author=viewer_is_author,
        can_request_coauthorship=not viewer_is_author,
        request_blocked_reason=None if viewer_is_author else info_service.request_blocker(db, meme, viewer),
        my_request_status=my_request.status if my_request else None,
        pending_requests=len(pending),
    )
    return out


def _contact_out(c: EntryContact) -> ContactOut:
    u = c.user
    return ContactOut(
        user={"id": u.id, "display_name": u.display_name, "title": u.title,
              "department": u.department, "is_active": u.is_active},
        role=c.role,
        basis=c.basis,
        source=c.source,
        reputation=u.reputation or 0,
        email=u.email,
    )


def _entry_detail_out(
    db: Session,
    entry: Entry,
    current_user: User | None = None,
) -> EntryDetailOut:
    base = _entry_to_out(db, entry, current_user).model_dump()
    mine = next((c for c in entry.contacts if current_user and c.user_id == current_user.id), None)
    base.update(
        contacts=[_contact_out(c) for c in contact_service.active_contacts(entry)],
        no_responsible_contact=not contact_service.has_responsible_contact(entry),
        my_contact=_contact_out(mine) if mine else None,
        origin=_origin(db, entry, current_user),
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
    return EntryDetailOut(**base)


def _reload(db: Session, entry_id: int) -> Entry:
    entry = db.query(Entry).filter(Entry.id == entry_id).options(*_entry_options()).first()
    assert entry is not None
    return entry


def _set_keywords(db: Session, entry: Entry, keywords: list[str]) -> None:
    """Link people-set keyword tags (shared, normalized entities); a bad name is a 422."""
    try:
        tag_service.add_keywords(db, entry, keywords)
    except tag_service.TagError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


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

    try:
        company_id, client_project_id, _ = scope_service.resolve_scope(
            db, body.scope, body.company_id, body.client_project_id
        )
    except scope_service.ScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    client = scope_service.named_client(db, title, content, body.justification)
    if client:
        # BR-11: content refers to the client project; the client is named only in the scope badge
        raise HTTPException(
            status_code=422,
            detail=f"The text names the client '{client}'. Refer to the client project instead; the scope shows the client.",
        )

    try:
        basis, basis_source = contact_service.clean_basis(body.basis, body.basis_source)
    except contact_service.BasisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    suggestion = None
    if body.suggestion_id is not None:
        # Adding an AI-parser meme: only an author who approved it may, once, and sensitive text must be confirmed clean
        try:
            suggestion = parser_publish.check_can_publish(db, author, body.suggestion_id, body.sensitive_confirmed)
        except info_service.ParserError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc))

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
        company_id=company_id,
        client_project_id=client_project_id,
        department=author.department or "General",
        country=country,
        category_id=category.id,
        author_id=author.id,
        team_id=team_id,
        is_published=True,
        difference_note=(body.difference_note or "").strip() or None,
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
    contact_service.add_contact(db, entry, author.id, basis, basis_source, role="author")

    _set_keywords(db, entry, body.keywords)
    tag_service.add_auto_tags(db, entry, author)
    db.flush()
    if suggestion is not None:
        # Links the meme, records the approved co-authors (so they are not asked to verify) and closes the others
        parser_publish.publish(db, suggestion, entry, author, basis, basis_source)

    db.flush()
    # UC-1 step 4: verifiers in scope hear about the new entry (see get_verifiers_for_entry for the fallback).
    for verifier in get_verifiers_for_entry(db, entry):
        if verifier.id != author.id:
            db.add(Notification(
                user_id=verifier.id,
                event_type="new_entry",
                title="New entry waiting for verification",
                body=f"{author.display_name} added {entry.public_id}: {title}",
                link=f"/entries/{entry.public_id}",
            ))

    db.commit()
    entry = _reload(db, entry.id)
    return _entry_to_out(db, entry, current_user=author)


@router.get("/{public_id}", response_model=EntryDetailOut)
def get_entry(
    public_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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


@router.put("/{public_id}/my-basis", response_model=ContactOut)
def set_my_basis(
    public_id: str,
    body: BasisIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContactOut:
    """The signed-in author or contributor changes their own basis and source (FR-K2, BR-10).

    It is recorded in the change log; it creates no new version and does not reset verification."""
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    try:
        contact = contact_service.change_basis(db, entry, user, body.basis, body.source)
    except LookupError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except contact_service.BasisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    db.refresh(contact)
    return _contact_out(contact)


@router.get("/{public_id}/versions/{version_number}", response_model=EntryVersionOut)
def get_version(
    public_id: str,
    version_number: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
        # Keep the system's automatic tags; replace the keywords
        entry.tags = [t for t in entry.tags if t.tag_type == tag_service.AUTOMATIC]
        _set_keywords(db, entry, body.keywords)
        tag_service.add_auto_tags(db, entry, user)

    entry.updated_at = datetime.utcnow()
    db.commit()
    entry = _reload(db, entry.id)
    return _entry_to_out(db, entry, current_user=user)
