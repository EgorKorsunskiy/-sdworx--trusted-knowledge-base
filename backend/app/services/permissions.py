from sqlalchemy.orm import Session, joinedload

from app.models import (
    Entry,
    EntryVersion,
    RoleType,
    TeamMembership,
    User,
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


def can_verify_version(db: Session, user: User, version: EntryVersion) -> bool:
    entry = version.entry
    if entry.author_id == user.id or version.edited_by_id == user.id:
        return False

    roles = {r.role for r in user.roles}

    if RoleType.ADMIN.value in roles:
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


def can_edit_own_unverified(user: User, entry: Entry, version: EntryVersion) -> bool:
    if version.status != VersionStatus.UNVERIFIED.value:
        return False
    return entry.author_id == user.id


def get_verifiers_for_entry(db: Session, entry: Entry) -> list[User]:
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
