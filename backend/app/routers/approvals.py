from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user, user_to_out
from app.models import (
    Entry,
    EntryVersion,
    Notification,
    RoleType,
    TeamMembership,
    User,
    Verification,
    VersionStatus,
)
from app.schemas import EntryVersionOut, UserOut
from app.services.permissions import can_verify_version, get_verifiers_for_entry, verifier_role_badge

router = APIRouter(prefix="/approvals", tags=["approvals"])


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


def _notify_author(db: Session, author_id: int, event_type: str, title: str, body: str, link: str | None = None) -> None:
    db.add(Notification(user_id=author_id, event_type=event_type, title=title, body=body, link=link))
    db.commit()


@router.get("/pending")
def pending_approvals(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List unverified versions the current user can verify under dual-scope rules."""
    versions = (
        db.query(EntryVersion)
        .filter(EntryVersion.status == VersionStatus.UNVERIFIED.value)
        .options(
            joinedload(EntryVersion.entry),
            joinedload(EntryVersion.edited_by),
        )
        .all()
    )
    result = []
    for v in versions:
        if can_verify_version(db, user, v):
            result.append({
                "version": _version_to_out(v),
                "entry": {
                    "public_id": v.entry.public_id,
                    "department": v.entry.department,
                    "country": v.entry.country,
                    "author": user_to_out(v.entry.author),
                },
            })
    return result


class VerifyBody:
    pass


@router.post("/{version_id}/verify")
def verify_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    version = db.query(EntryVersion).filter(EntryVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    if not can_verify_version(db, user, version):
        raise HTTPException(status_code=403, detail="Not authorized to verify this version")

    version.status = VersionStatus.VERIFIED.value
    badge = verifier_role_badge(user)
    db.add(Verification(
        version_id=version.id,
        verifier_id=user.id,
        role=badge,
        action="verify",
    ))
    db.commit()

    _notify_author(
        db, version.entry.author_id, "verified",
        "Your entry was verified",
        f"{version.entry.public_id} was verified by {user.display_name} ({badge}).",
        f"/entries/{version.entry.public_id}",
    )

    return {"status": "verified", "role": badge}


@router.post("/{version_id}/send-back")
def send_back_version(
    version_id: int,
    comment: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    version = db.query(EntryVersion).filter(EntryVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    if not can_verify_version(db, user, version):
        raise HTTPException(status_code=403, detail="Not authorized to send back this version")

    # status stays unverified
    badge = verifier_role_badge(user)
    db.add(Verification(
        version_id=version.id,
        verifier_id=user.id,
        role=badge,
        action="send_back",
        comment=comment,
    ))
    db.commit()

    _notify_author(
        db, version.entry.author_id, "sent_back",
        "Your entry was sent back",
        f"{version.entry.public_id} needs changes. Comment: {comment or 'None'}",
        f"/entries/{version.entry.public_id}",
    )

    return {"status": "sent_back"}


@router.get("/who-to-ask/{public_id}", response_model=list[UserOut])
def who_to_ask(
    public_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[UserOut]:
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    verifiers = get_verifiers_for_entry(db, entry)
    return [user_to_out(u) for u in verifiers]
