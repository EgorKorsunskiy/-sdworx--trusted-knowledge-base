from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.deps.auth import (
    create_session,
    destroy_session,
    get_current_user_optional,
    get_session_token,
    load_user,
    user_to_out,
)
from app.models import TeamMembership, User
from app.schemas import DevLoginRequest, SessionOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/users", response_model=list[UserOut])
def list_dev_users(db: Session = Depends(get_db)) -> list[UserOut]:
    users = (
        db.query(User)
        .options(
            joinedload(User.roles),
            joinedload(User.memberships).joinedload(TeamMembership.team),
        )
        .filter(User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )
    return [user_to_out(u) for u in users]


@router.post("/dev-login", response_model=SessionOut)
def dev_login(
    body: DevLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionOut:
    user = load_user(db, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token = create_session(user.id)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    response.headers["X-Session-Token"] = token
    return SessionOut(authenticated=True, user=user_to_out(user), token=token)


@router.post("/logout", response_model=SessionOut)
def logout(response: Response, request: Request) -> SessionOut:
    token = get_session_token(request)
    destroy_session(token)
    response.delete_cookie(key=settings.session_cookie_name)
    return SessionOut(authenticated=False, user=None)


@router.get("/me", response_model=SessionOut)
def me(user: User | None = Depends(get_current_user_optional)) -> SessionOut:
    if user is None:
        return SessionOut(authenticated=False, user=None)
    return SessionOut(authenticated=True, user=user_to_out(user))
