from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, EntryVersion, User, Verification
from app.schemas import EntryDiffOut, HistoryItemOut
from app.services.diff import attribute_range, build_diff, get_approvers, snapshot, user_ref

router = APIRouter(prefix="/entries", tags=["history"])


def _get_entry(db: Session, public_id: str) -> Entry:
    entry = (
        db.query(Entry)
        .options(
            joinedload(Entry.versions).joinedload(EntryVersion.edited_by),
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
