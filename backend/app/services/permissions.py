from sqlalchemy.orm import Session, joinedload

from app.models import (
    Entry,
    EntryVersion,
    RoleType,
    TeamMembership,
    User,
    UserRole,
    VerifierDepartmentMap,
    VersionStatus,
)


def user_has_role(user: User, role: str) -> bool:
    return any(r.role == role for r in user.roles)


def get_user_primary_team(user: User) -> int | None:
    for m in user.memberships:
        if m.is_primary and m.team_id:
            return m.team_id
    if user.memberships:
        return user.memberships[0].team_id
    return None


def _in_verifier_scope(db: Session, user: User, entry: Entry, include_admin: bool) -> bool:
    roles = {r.role for r in user.roles}

    if include_admin and RoleType.ADMIN.value in roles:
        return True

    if RoleType.EXPERT.value in roles:
        mapped = (
            db.query(VerifierDepartmentMap)
            .filter_by(user_id=user.id, department=entry.department)
            .first()
        )
        if mapped:
            return True

    if RoleType.TEAM_LEAD.value in roles or RoleType.MANAGER.value in roles:
        user_team = get_user_primary_team(user)
        if user_team and entry.team_id == user_team:
            return True

    return False


def _fallback_applies(db: Session, user: User, entry: Entry, exclude_ids: set[int]) -> bool:
    """Fallback verification: if nobody else is in scope for an entry (no senior expert mapped to its
    department, no team lead / manager of its author's team), any Manager or Admin may verify it.
    Otherwise the usual scope rules decide and this never applies."""
    roles = {r.role for r in user.roles}
    if not user.is_active or user.id in exclude_ids:
        return False
    if RoleType.MANAGER.value not in roles and RoleType.ADMIN.value not in roles:
        return False
    for other in _scoped_verifiers(db, entry):
        if other.id in exclude_ids or not other.is_active:
            continue
        if _in_verifier_scope(db, other, entry, include_admin=False):
            return False
    return True


def can_verify_version(db: Session, user: User, version: EntryVersion) -> bool:
    entry = version.entry
    exclude = {entry.author_id, version.edited_by_id}
    if user.id in exclude:
        return False
    if _in_verifier_scope(db, user, entry, include_admin=False):
        return True
    return _fallback_applies(db, user, entry, exclude)


def can_verify_pr(db: Session, user: User, pr) -> bool:
    """Step-2 verifier of a pull request: in scope, not the PR author nor the entry author, no admin shortcut."""
    if not user.is_active or user.id in (pr.author_id, pr.entry.author_id):
        return False
    return _in_verifier_scope(db, user, pr.entry, include_admin=False)


def can_edit_own_unverified(user: User, entry: Entry, version: EntryVersion) -> bool:
    if version.status != VersionStatus.UNVERIFIED.value:
        return False
    return entry.author_id == user.id


def get_verifiers_for_entry(db: Session, entry: Entry) -> list[User]:
    """Who can verify this entry: the scoped verifiers, or, if there are none, the fallback Managers/Admins."""
    users = {u.id: u for u in _scoped_verifiers(db, entry)}
    scoped = [
        u for u in users.values()
        if u.id != entry.author_id and u.is_active and _in_verifier_scope(db, u, entry, include_admin=False)
    ]
    if not scoped:
        fallback = (
            db.query(User)
            .options(joinedload(User.roles))
            .join(User.roles)
            .filter(User.is_active.is_(True), UserRole.role.in_([RoleType.MANAGER.value, RoleType.ADMIN.value]))
            .all()
        )
        for u in fallback:
            if u.id != entry.author_id:
                users.setdefault(u.id, u)
    return list(users.values())


def _scoped_verifiers(db: Session, entry: Entry) -> list[User]:
    result: set[int] = set()
    mapped = db.query(VerifierDepartmentMap).filter_by(department=entry.department).all()
    for m in mapped:
        result.add(m.user_id)
    if entry.team_id:
        memberships = (
            db.query(TeamMembership)
            .options(joinedload(TeamMembership.user).joinedload(User.roles))
            .filter_by(team_id=entry.team_id)
            .all()
        )
        for m in memberships:
            if any(
                r.role in {RoleType.TEAM_LEAD.value, RoleType.MANAGER.value}
                for r in m.user.roles
            ):
                result.add(m.user_id)
    if not result:
        return []
    return db.query(User).options(joinedload(User.roles)).filter(User.id.in_(list(result))).all()


def verifier_role_badge(user: User) -> str:
    roles = {r.role for r in user.roles}
    if RoleType.MANAGER.value in roles:
        return "Manager"
    if RoleType.TEAM_LEAD.value in roles:
        return "Team Lead"
    if RoleType.EXPERT.value in roles:
        return "Senior Expert"
    return "Verifier"


def contributor_role_badge(user: User) -> str:
    roles = {r.role for r in user.roles}
    if RoleType.MANAGER.value in roles:
        return "Manager"
    if RoleType.TEAM_LEAD.value in roles:
        return "Team Lead"
    if RoleType.EXPERT.value in roles:
        return "Senior Expert"
    if RoleType.ADMIN.value in roles:
        return "Admin"
    return "Employee"


def entry_contributor_ids(db: Session, entry: Entry) -> set[int]:
    """Author plus everyone who ever edited a version (they may not vote on the entry)."""
    ids = {entry.author_id}
    rows = db.query(EntryVersion.edited_by_id).filter(EntryVersion.entry_id == entry.id).all()
    ids.update(r[0] for r in rows if r[0] is not None)
    return ids
