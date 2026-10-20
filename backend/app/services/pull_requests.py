"""Pull request lifecycle helpers (DB only, no HTTP). Callers commit."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    EntryVersion,
    Notification,
    OutdatedResolution,
    PullRequest,
    PullRequestStatus,
    User,
    VersionStatus,
)
from app.services.diff import user_ref
from app.services.permissions import can_verify_pr, can_verify_version, get_verifiers_for_entry
from app.services.reputation import award

OPEN_STATUSES = (PullRequestStatus.OPEN.value, PullRequestStatus.AUTHOR_APPROVED.value)


def is_resolved(pr: PullRequest) -> bool:
    return pr.status in (PullRequestStatus.MERGED.value, PullRequestStatus.REJECTED.value)


def current_step(pr: PullRequest) -> str | None:
    """Who decides next. Only the entry author approves a PR; if the author is no longer active a
    verifier in scope stands in ('verifier'). AUTHOR_APPROVED is a legacy status that is no longer set."""
    if pr.status in OPEN_STATUSES:
        return "author" if pr.entry.author.is_active else "verifier"
    return None


def role_of(db: Session, user: User, pr: PullRequest) -> str | None:
    if user.id == pr.entry.author_id:
        return "author"
    if can_verify_pr(db, user, pr):
        return "verifier"
    return None


def current_number(pr: PullRequest) -> int:
    return pr.entry.versions[-1].version_number


def is_stale(pr: PullRequest) -> bool:
    return pr.base_version_number is not None and current_number(pr) != pr.base_version_number


def base_version(pr: PullRequest) -> EntryVersion:
    for v in pr.entry.versions:
        if v.version_number == pr.base_version_number:
            return v
    return pr.entry.versions[-1]


def proposed_snapshot(pr: PullRequest, base: EntryVersion) -> dict:
    return {
        "title": pr.proposed_title or base.title,
        "body": pr.proposed_body or base.body or "",
        "justification": pr.proposed_justification if pr.proposed_justification is not None else base.justification,
    }


def pr_approvers(pr: PullRequest) -> list[dict]:
    rows = sorted((a for a in pr.approvals if a.action == "approve"), key=lambda a: (a.created_at, a.id))
    return [
        {
            "user": user_ref(a.approver),
            "role": a.step,
            "action": a.action,
            "created_at": a.created_at,
            "source": "pull_request",
        }
        for a in rows
    ]


def scope_verifiers(db: Session, pr: PullRequest) -> list[User]:
    return [u for u in get_verifiers_for_entry(db, pr.entry) if can_verify_pr(db, u, pr)]


def notify(db: Session, user_id: int, event: str, title: str, body: str | None, link: str | None) -> None:
    db.add(Notification(user_id=user_id, event_type=event, title=title, body=body, link=link))


def notify_merged(db: Session, pr: PullRequest, version: EntryVersion, actor: User) -> None:
    """After a merge: tell the PR author, the entry author, and the verifiers who must now verify the
    new (Unverified) version. Adds notifications only; the caller commits."""
    entry = pr.entry
    link = f"/entries/{entry.public_id}"
    told = {actor.id}
    if pr.author_id not in told:
        notify(db, pr.author_id, "pr_merged", "Your pull request was merged",
               f"{pr.title} was merged into {entry.public_id} by {actor.display_name}.", link)
        told.add(pr.author_id)
    if entry.author_id not in told:
        notify(db, entry.author_id, "pr_merged", "A pull request was merged into your entry",
               f"{pr.title} by {pr.author.display_name} was merged into {entry.public_id}.", link)
        told.add(entry.author_id)
    for v in get_verifiers_for_entry(db, entry):
        if v.id not in told and can_verify_version(db, v, version):
            notify(db, v.id, "new_version_in_scope", "New version waiting for verification",
                   f"{entry.public_id} v{version.version_number} (from a merged pull request) needs verification.", link)


def finish_legacy_author_approved(db: Session) -> int:
    """PRs approved by their author under the old two-step rule: the author's approval is now enough.
    Merge them (or reopen them if the entry moved on meanwhile). Idempotent; returns the number merged."""
    merged = 0
    for pr in db.query(PullRequest).filter(PullRequest.status == PullRequestStatus.AUTHOR_APPROVED.value).all():
        if is_stale(pr):
            pr.status = PullRequestStatus.OPEN.value  # shows as stale: it can only be rejected now
            continue
        actor = pr.entry.author
        version = merge(db, pr, actor)
        notify_merged(db, pr, version, actor)
        merged += 1
    db.commit()
    return merged


def merge(db: Session, pr: PullRequest, verifier: User) -> EntryVersion:
    """Create the new Unverified version from the PR and mark it merged (no commit)."""
    entry = pr.entry
    base = entry.versions[-1]
    snap = proposed_snapshot(pr, base)
    now = datetime.utcnow()
    version = EntryVersion(
        entry_id=entry.id,
        version_number=base.version_number + 1,
        title=snap["title"],
        body=snap["body"],
        justification=snap["justification"],
        status=VersionStatus.UNVERIFIED.value,
        change_note=pr.change_note or pr.title,
        edited_by_id=pr.author_id,
        source_pr_id=pr.id,
    )
    db.add(version)
    if base.status == VersionStatus.OUTDATED.value:
        db.add(OutdatedResolution(version_id=base.id, verifier_id=verifier.id, action="merged_pr"))
        for flag in base.outdated_flags:
            if flag.resolved_at is None:
                flag.resolved_at = now
    pr.status = PullRequestStatus.MERGED.value
    pr.resolved_at = now
    entry.updated_at = now
    if pr.author_id != entry.author_id:
        award(db, pr.author, "reputation_pr_merged")
    db.flush()
    db.expire(entry, ["versions"])  # so entry.versions[-1] is the merged version for later checks
    return version
