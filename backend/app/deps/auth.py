import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import TeamMembership, User
from app.schemas import RoleOut, TeamBrief, UserOut
from app.services.tokens import audit, decode_access_token


def get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


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
        country=user.country,
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
    """The signed-in employee from a valid access token, or None. Only used where a missing token is fine."""
    token = get_bearer_token(request)
    if not token:
        return None
    try:
        claims = decode_access_token(token)
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
    user = load_user(db, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: str):
    """Coarse role check. Roles come from the employee record, so changes apply immediately."""

    def checker(user: User = Depends(get_current_user)) -> User:
        user_roles = {r.role for r in user.roles}
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def record_denied(request: Request, exc: HTTPException) -> None:
    """Audit-log a 401 (with a bad/expired token presented) or any 403. Never raises."""
    try:
        token = get_bearer_token(request)
        if exc.status_code == 401 and token is None:
            return  # plain "not signed in": not worth logging
        user_id = None
        if token:
            try:
                user_id = int(decode_access_token(token)["sub"])  # only trust verified tokens
            except Exception:
                user_id = None
        get_db_dep = request.app.dependency_overrides.get(get_db, get_db)
        gen = get_db_dep()
        db = next(gen)
        try:
            audit(
                db,
                "access_denied",
                user_id,
                f"{exc.status_code} {request.method} {request.url.path}: {exc.detail}",
            )
        finally:
            gen.close()
    except Exception:
        pass
