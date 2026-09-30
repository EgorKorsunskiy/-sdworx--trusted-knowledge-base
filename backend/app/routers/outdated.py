from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, EntryVersion, Notification, OutdatedFlag, OutdatedResolution, User, VersionStatus
from app.services.permissions import can_verify_version

router = APIRouter(prefix="/entries/{public_id}", tags=["outdated"])


def _last_verifier_id(version: EntryVersion) -> int | None:
    for ver in reversed(version.verifications):
        if ver.action == "verify":
            return ver.verifier_id
    return None


@router.post("/outdated")
def mark_outdated(
    public_id: str,
    reason: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    current = entry.versions[-1]

    db.add(OutdatedFlag(version_id=current.id, user_id=user.id, reason=reason.strip()))
    current.status = VersionStatus.OUTDATED.value

    # notify author
    db.add(Notification(
        user_id=entry.author_id,
        event_type="outdated",
        title="Entry marked outdated",
        body=f"{public_id} was flagged as outdated: {reason}",
        link=f"/entries/{public_id}",
    ))
    last = _last_verifier_id(current)
    if last:
        db.add(Notification(
            user_id=last,
            event_type="outdated",
            title="Entry marked outdated",
            body=f"{public_id} was flagged as outdated: {reason}",
            link=f"/entries/{public_id}",
        ))
    db.commit()
    return {"status": "outdated"}


@router.post("/confirm-still-valid")
def confirm_still_valid(
    public_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    current = entry.versions[-1]
    if current.status != VersionStatus.OUTDATED.value:
        raise HTTPException(status_code=400, detail="Entry is not outdated")
    if not can_verify_version(db, user, current):
        raise HTTPException(status_code=403, detail="Not authorized to confirm")

    current.status = VersionStatus.VERIFIED.value
    db.add(OutdatedResolution(version_id=current.id, verifier_id=user.id, action="confirm_valid"))

    # Resolve active flags
    for flag in current.outdated_flags:
        if flag.resolved_at is None:
            flag.resolved_at = __import__("datetime").datetime.utcnow()

    db.add(Notification(
        user_id=entry.author_id,
        event_type="confirmed_valid",
        title="Entry confirmed still valid",
        body=f"{public_id} is confirmed still valid by {user.display_name}.",
        link=f"/entries/{public_id}",
    ))
    db.commit()
    return {"status": "verified"}
