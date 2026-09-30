from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import TeamMembership, User, UserRole
from app.schemas import RoleOut, TeamBrief, UserOut

_sessions: dict[str, int] = {}


def create_session(user_id: int) -> str:
    import secrets

    token = secrets.token_urlsafe(32)
    _sessions[token] = user_id
    return token


def destroy_session(token: str | None) -> None:
    if token and token in _sessions:
        del _sessions[token]


def get_session_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(settings.session_cookie_name)


def user_to_out(user: User) -> UserOut:
    teams: list[TeamBrief] = []
    for m in user.memberships:
        if m.team:
            teams.append(TeamBrief(id=m.team.id, name=m.team.name, department=m.team.department))
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        department=user.department,
        title=user.title,
        reputation=user.reputation,
        is_active=user.is_active,
        roles=[RoleOut(role=r.role, scope=r.scope) for r in user.roles],
        teams=teams,
    )


def load_user(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .options(
            joinedload(User.roles),
            joinedload(User.memberships).joinedload(TeamMembership.team),
        )
        .filter(User.id == user_id)
        .first()
    )


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    token = get_session_token(request)
    if not token:
        return None
    user_id = _sessions.get(token)
    if not user_id:
        return None
    return load_user(db, user_id)


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        user_roles = {r.role for r in user.roles}
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker
