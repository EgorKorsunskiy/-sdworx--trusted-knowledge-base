from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, EntryVersion, PRApproval, PullRequest, PullRequestStatus, User
from app.schemas import (
    EntryDiffOut,
    PendingPROut,
    PRApproveIn,
    PRRejectIn,
    PullRequestBrief,
    PullRequestCreate,
    PullRequestOut,
)
from app.services import contacts as contact_service
from app.services import pull_requests as svc
from app.services.diff import build_diff, snapshot, user_ref

router = APIRouter(tags=["pull-requests"])

AUTO_COMMENT = "Automatic: PR author is the entry author"
SKIP_COMMENT = "Skipped: author is no longer active"


def _get_entry(db: Session, public_id: str) -> Entry:
    entry = db.query(Entry).filter(Entry.public_id == public_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


def _get_pr(db: Session, pr_id: int) -> PullRequest:
    pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
    if pr is None:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return pr


def _brief(pr: PullRequest) -> dict:
    return {
        "id": pr.id,
        "title": pr.title,
        "status": pr.status,
        "author": user_ref(pr.author),
        "created_at": pr.created_at,
        "resolved_at": pr.resolved_at,
        "change_note": pr.change_note,
        "base_version_number": pr.base_version_number,
        "is_stale": not svc.is_resolved(pr) and svc.is_stale(pr),
        "basis": pr.basis,
        "basis_source": pr.basis_source,
    }


def _out(db: Session, pr: PullRequest, user: User) -> dict:
    entry = pr.entry
    role = svc.role_of(db, user, pr)
    step = svc.current_step(pr)
    active = not svc.is_resolved(pr) and user.id != pr.author_id
    stale = svc.is_stale(pr)
    approvals = sorted(pr.approvals, key=lambda a: (a.created_at, a.id))
    reject = next((a for a in reversed(approvals) if a.action == "reject"), None)
    merged = (
        db.query(EntryVersion.version_number).filter(EntryVersion.source_pr_id == pr.id).scalar()
        if pr.status == PullRequestStatus.MERGED.value
        else None
    )
    return {
        **_brief(pr),
        "entry": {
            "public_id": entry.public_id,
            "title": entry.versions[-1].title,
            "department": entry.department,
            "author": user_ref(entry.author),
            "current_version_number": entry.versions[-1].version_number,
        },
        "description": pr.description,
        "proposed_title": pr.proposed_title,
        "proposed_body": pr.proposed_body,
        "proposed_justification": pr.proposed_justification,
        "approvals": [
            {
                "id": a.id,
                "step": a.step,
                "action": a.action,
                "comment": a.comment,
                "created_at": a.created_at,
                "approver": user_ref(a.approver),
            }
            for a in approvals
        ],
        "rejection_reason": reject.comment if reject else None,
        "merged_version_number": merged,
        "next_step": step,
        # Who can approve it now: the entry author, or (author inactive) the verifiers in scope.
        "waiting_on": (
            [user_ref(entry.author)]
            if step == "author"
            else [user_ref(u) for u in svc.scope_verifiers(db, pr)]
            if step == "verifier"
            else []
        ),
        "can_approve_as_author": active and not stale and step == "author" and role == "author",
        "can_approve_as_verifier": active and not stale and step == "verifier" and role == "verifier",
        "can_reject": active and role is not None and role == step,
    }


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


@router.get("/pull-requests/pending", response_model=list[PendingPROut])
def pending_pull_requests(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prs = (
        db.query(PullRequest)
        .filter(PullRequest.status.in_(svc.OPEN_STATUSES), PullRequest.author_id != user.id)
        .order_by(PullRequest.created_at, PullRequest.id)
        .all()
    )
    out = []
    for pr in prs:
        step = svc.current_step(pr)
        if step is None or svc.role_of(db, user, pr) != step:
            continue
        out.append(
            {
                **_brief(pr),
                "step": step,
                "entry": {
                    "public_id": pr.entry.public_id,
                    "title": pr.entry.versions[-1].title,
                    "department": pr.entry.department,
                },
            }
        )
    return out


@router.post("/entries/{public_id}/pull-requests", response_model=PullRequestOut, status_code=201)
def open_pull_request(
    public_id: str,
    body: PullRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = _get_entry(db, public_id)
    base = entry.versions[-1]

    change_note = (body.change_note or "").strip()
    if not change_note:
        raise HTTPException(status_code=422, detail="A change note is required")
    p_title, p_body, p_just = _clean(body.proposed_title), _clean(body.proposed_body), _clean(body.proposed_justification)
    if p_title == (base.title or "").strip():
        p_title = None
    if p_body == (base.body or "").strip():
        p_body = None
    if p_just == (base.justification or "").strip():
        p_just = None
    if p_title is None and p_body is None and p_just is None:
        raise HTTPException(status_code=422, detail="The proposal does not change the entry")

    try:
        pr_basis, pr_source = contact_service.clean_basis(body.basis, body.basis_source)
    except contact_service.BasisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    pr = PullRequest(
        entry_id=entry.id,
        author_id=user.id,
        status=PullRequestStatus.OPEN.value,
        title=_clean(body.title) or p_title or f"Change to {entry.public_id}",
        description=_clean(body.description),
        proposed_title=p_title,
        proposed_body=p_body,
        proposed_justification=p_just,
        change_note=change_note,
        base_version_number=base.version_number,
        basis=pr_basis,
        basis_source=pr_source,
    )
    db.add(pr)
    db.flush()

    link = f"/pull-requests/{pr.id}"
    if entry.author_id == user.id:
        # The PR author is the entry author: their own approval is implicit, so it merges right away
        # (as a new Unverified version that still needs normal verification).
        db.add(PRApproval(pull_request_id=pr.id, approver_id=user.id, step="author", action="approve", comment=AUTO_COMMENT))
        db.flush()
        db.refresh(pr)
        _merge_and_notify(db, pr, user)
    elif not entry.author.is_active:
        # Nobody to approve it: a verifier in scope stands in for the departed author.
        db.flush()
        db.refresh(pr)
        for v in svc.scope_verifiers(db, pr):
            svc.notify(db, v.id, "pr_opened", "Pull request needs your approval",
                       f"The author of {entry.public_id} is no longer active. {user.display_name} proposed: {pr.title}", link)
        db.commit()
    else:
        svc.notify(db, entry.author_id, "pr_opened", "New pull request on your entry",
                   f"{user.display_name} proposed a change to {entry.public_id}: {pr.title}", link)
        db.commit()
    return _out(db, pr, user)


def _merge_and_notify(db: Session, pr: PullRequest, actor: User) -> None:
    """Merge the PR into a new Unverified version, notify, commit. 409 if the entry moved on."""
    try:
        version = svc.merge(db, pr, actor)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The entry changed while merging; open a new pull request.")
    svc.notify_merged(db, pr, version, actor)
    db.commit()


@router.get("/entries/{public_id}/pull-requests", response_model=list[PullRequestBrief])
def list_entry_pull_requests(
    public_id: str,
    open_only: bool = Query(False),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entry = _get_entry(db, public_id)
    q = db.query(PullRequest).filter(PullRequest.entry_id == entry.id)
    if open_only:
        q = q.filter(PullRequest.status.in_(svc.OPEN_STATUSES))
    return [_brief(p) for p in q.order_by(PullRequest.created_at.desc(), PullRequest.id.desc()).all()]


@router.get("/pull-requests/{pr_id}", response_model=PullRequestOut)
def get_pull_request(
    pr_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _out(db, _get_pr(db, pr_id), user)


@router.get("/pull-requests/{pr_id}/diff", response_model=EntryDiffOut)
def pull_request_diff(
    pr_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    pr = _get_pr(db, pr_id)
    base = svc.base_version(pr)
    meta = {
        "public_id": pr.entry.public_id,
        "kind": "proposal",
        "from_version": base.version_number,
        "to_version": None,
        "version_id": None,
        "created_at": pr.created_at,
        "change_note": pr.change_note,
        "status": pr.status,
        "approvers": svc.pr_approvers(pr),
        "pull_request_id": pr.id,
    }
    return build_diff(snapshot(base), svc.proposed_snapshot(pr, base), user_ref(pr.author), meta)


def _check_actor(db: Session, pr: PullRequest, user: User) -> str:
    """Shared approve/reject checks; returns the step being acted on."""
    if svc.is_resolved(pr):
        raise HTTPException(status_code=409, detail=f"This pull request is already {pr.status}")
    if user.id == pr.author_id:
        raise HTTPException(status_code=403, detail="You cannot approve or reject your own pull request")
    role = svc.role_of(db, user, pr)
    if role is None:
        raise HTTPException(status_code=403, detail="You have no role on this pull request")
    step = svc.current_step(pr)
    if role != step:
        if step == "author":
            raise HTTPException(status_code=409, detail="Waiting for the entry author's approval")
        raise HTTPException(status_code=409, detail="This step is already done")
    return step


@router.post("/pull-requests/{pr_id}/approve", response_model=PullRequestOut)
def approve_pull_request(
    pr_id: int,
    body: PRApproveIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pr = _get_pr(db, pr_id)
    step = _check_actor(db, pr, user)
    if svc.is_stale(pr):
        raise HTTPException(
            status_code=409,
            detail=(
                f"The entry changed since this pull request was opened (now v{svc.current_number(pr)}, "
                f"based on v{pr.base_version_number}); open a new pull request."
            ),
        )
    comment = _clean(body.comment) if body else None

    # The entry author's approval is the only one needed: approving merges the PR into a new
    # Unverified version, which then goes through normal verification like any other entry.
    # If the author is no longer active a verifier in scope approves in their place.
    if step == "verifier":
        db.add(PRApproval(pull_request_id=pr.id, approver_id=pr.entry.author_id, step="author", action="skip", comment=SKIP_COMMENT))
    db.add(PRApproval(pull_request_id=pr.id, approver_id=user.id, step=step, action="approve", comment=comment))
    db.flush()
    db.refresh(pr)
    _merge_and_notify(db, pr, user)
    return _out(db, pr, user)


@router.post("/pull-requests/{pr_id}/reject", response_model=PullRequestOut)
def reject_pull_request(
    pr_id: int,
    body: PRRejectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pr = _get_pr(db, pr_id)
    step = _check_actor(db, pr, user)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required")
    db.add(PRApproval(pull_request_id=pr.id, approver_id=user.id, step=step, action="reject", comment=reason))
    pr.status = PullRequestStatus.REJECTED.value
    pr.resolved_at = datetime.utcnow()
    svc.notify(db, pr.author_id, "pr_rejected", "Your pull request was rejected",
               f"{pr.title} on {pr.entry.public_id} was rejected: {reason}", f"/pull-requests/{pr.id}")
    db.commit()
    return _out(db, pr, user)
