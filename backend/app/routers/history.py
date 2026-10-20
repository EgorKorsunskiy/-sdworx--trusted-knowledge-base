from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, EntryContactChange, EntryVersion, User, Verification
from app.schemas import ContributorsOut, EntryDiffOut, HistoryItemOut
from app.services.blame import VersionSnap, compute_blame, contributor_stats
from app.services.permissions import contributor_role_badge, entry_contributor_ids
from app.services.diff import attribute_range, build_diff, get_approvers, snapshot, user_ref

router = APIRouter(prefix="/entries", tags=["history"])


def _get_entry(db: Session, public_id: str) -> Entry:
    entry = (
        db.query(Entry)
        .options(
            joinedload(Entry.versions).joinedload(EntryVersion.edited_by),
            joinedload(Entry.contacts),
            joinedload(Entry.versions)
            .joinedload(EntryVersion.verifications)
            .joinedload(Verification.verifier),
        )
        .filter(Entry.public_id == public_id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


def _diff_for(db: Session, entry: Entry, to_v: EntryVersion, base_v: EntryVersion | None) -> dict:
    """Diff of to_v against base_v (None = empty snapshot, i.e. creation). Reusable by pull requests."""
    author = user_ref(to_v.edited_by)
    meta = {
        "public_id": entry.public_id,
        "kind": "created" if base_v is None else "change",
        "from_version": base_v.version_number if base_v else None,
        "to_version": to_v.version_number,
        "version_id": to_v.id,
        "created_at": to_v.created_at,
        "change_note": to_v.change_note,
        "status": to_v.status,
        "approvers": get_approvers(db, to_v),
        "pull_request_id": to_v.source_pr_id,
    }
    diff = build_diff(snapshot(base_v), snapshot(to_v), author, meta)
    if base_v is not None and base_v.version_number != to_v.version_number - 1:
        in_range = [
            {"author": user_ref(v.edited_by), "body": v.body or ""}
            for v in entry.versions
            if base_v.version_number < v.version_number <= to_v.version_number
        ]
        attribute_range(diff, in_range)
    return diff


@router.get("/{public_id}/history", response_model=list[HistoryItemOut])
def entry_history(
    public_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entry = _get_entry(db, public_id)
    versions = entry.versions
    items = []
    prev = None
    for v in versions:
        author = user_ref(v.edited_by)
        summary = build_diff(snapshot(prev), snapshot(v), author)["summary"]
        verifies = [x for x in v.verifications if x.action == "verify"]
        items.append(
            {
                "version_id": v.id,
                "version_number": v.version_number,
                "title": v.title,
                "status": v.status,
                "change_note": v.change_note,
                "created_at": v.created_at,
                "author": author,
                "is_current": v is versions[-1],
                "verifier_role": verifies[-1].role if verifies else None,
                "approvers": get_approvers(db, v),
                "summary": summary,
            }
        )
        prev = v
    return list(reversed(items))


@router.get("/{public_id}/basis-log")
def entry_basis_log(
    public_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict]:
    """Changes of authorship basis, newest first. They are part of the change log but make no new version (FR-K2)."""
    entry = _get_entry(db, public_id)
    rows = (
        db.query(EntryContactChange)
        .options(joinedload(EntryContactChange.user))
        .filter(EntryContactChange.entry_id == entry.id)
        .order_by(EntryContactChange.created_at.desc(), EntryContactChange.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "user": {"id": r.user.id, "display_name": r.user.display_name},
            "old_basis": r.old_basis,
            "old_source": r.old_source,
            "new_basis": r.new_basis,
            "new_source": r.new_source,
        }
        for r in rows
    ]


@router.get("/{public_id}/versions/{version_number}/diff", response_model=EntryDiffOut)
def entry_version_diff(
    public_id: str,
    version_number: int,
    against: int | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entry = _get_entry(db, public_id)
    by_number = {v.version_number: v for v in entry.versions}
    to_v = by_number.get(version_number)
    if to_v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    base_v = None
    if against is not None:
        if against >= version_number:
            raise HTTPException(status_code=400, detail="against must be an older version")
        base_v = by_number.get(against)
        if base_v is None:
            raise HTTPException(status_code=404, detail="Base version not found")
    elif version_number > 1:
        base_v = by_number.get(version_number - 1)
        if base_v is None:
            raise HTTPException(status_code=404, detail="Base version not found")
    return _diff_for(db, entry, to_v, base_v)


@router.get("/{public_id}/contributors", response_model=ContributorsOut)
def entry_contributors(
    public_id: str,
    version: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = _get_entry(db, public_id)
    versions = sorted(entry.versions, key=lambda v: v.version_number)
    current_number = versions[-1].version_number
    target = current_number if version is None else version
    if target not in {v.version_number for v in versions}:
        raise HTTPException(status_code=404, detail="Version not found")
    snaps = [
        VersionSnap(v.version_number, v.body or "", v.edited_by_id)
        for v in versions
        if v.version_number <= target
    ]
    lines = compute_blame(snaps)
    stats = contributor_stats(lines)
    # Co-authors added through the AI parser are contributors without a line until they edit one (BR-7, BR-M3)
    with_lines = {s["user_id"] for s in stats}
    co_authors = [c.user_id for c in entry.contacts if c.role == "co_author" and c.user_id not in with_lines]
    ids = [s["user_id"] for s in stats] + co_authors
    users = {}
    if ids:
        rows = db.query(User).options(joinedload(User.roles)).filter(User.id.in_(ids)).all()
        users = {u.id: u for u in rows}
    return {
        "version_number": target,
        "current_version_number": current_number,
        "viewer_is_contributor": user.id in entry_contributor_ids(db, entry),
        "fragments": [
            {
                "index": l.index,
                "text": l.text,
                "separator_before": l.sep,
                "contributor_ids": list(l.contributor_ids),
                "introduced_in_version": l.introduced_in,
                "last_edited_in_version": l.last_edited_in,
            }
            for l in lines
        ],
        "contributors": [
            {
                "user": {
                    "id": u.id,
                    "display_name": u.display_name,
                    "title": u.title,
                    "department": u.department,
                    "email": u.email,
                    "reputation": u.reputation or 0,
                    "role_badge": contributor_role_badge(u),
                },
                "fragment_indexes": s["fragment_indexes"],
                "fragment_count": s["fragment_count"],
                "first_version": s["first_version"],
                "last_version": s["last_version"],
            }
            for s in stats
            if (u := users.get(s["user_id"])) is not None
        ] + [
            {
                "user": {
                    "id": u.id,
                    "display_name": u.display_name,
                    "title": u.title,
                    "department": u.department,
                    "email": u.email,
                    "reputation": u.reputation or 0,
                    "role_badge": contributor_role_badge(u),
                },
                "fragment_indexes": [],
                "fragment_count": 0,
                "first_version": 1,
                "last_version": target,
            }
            for uid in co_authors
            if (u := users.get(uid)) is not None
        ],
    }
