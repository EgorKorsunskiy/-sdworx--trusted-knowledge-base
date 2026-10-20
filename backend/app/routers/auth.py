from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.deps.auth import get_current_user, load_user, user_to_out
from app.models import TeamMembership, User
from app.schemas import DevLoginRequest, SessionOut, UserOut
from app.services import idp
from app.services.tokens import (
    audit,
    create_access_token,
    issue_refresh_token,
    refresh_lifetime_hours,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


def _set_refresh_cookie(response: Response, raw: str, hours: int) -> None:
    # Path "/" so the cookie is also sent through a dev proxy that mounts the API under /api.
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=hours * 3600,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path="/")


def _start_session(db: Session, response: Response, user: User, event: str) -> SessionOut:
    full = load_user(db, user.id)
    access = create_access_token(db, full)
    raw, _ = issue_refresh_token(db, full)
    db.commit()
    _set_refresh_cookie(response, raw, refresh_lifetime_hours(db))
    audit(db, event, full.id, full.email)
    return SessionOut(authenticated=True, user=user_to_out(full), token=access)


@router.get("/config")
def auth_config() -> dict:
    """What the sign-in screen needs: where to send the browser and whether the demo picker is on."""
    return {
        "demo_mode": settings.demo_mode,
        "idp": {
            "client_id": settings.idp_client_id,
            # Relative path = served by this API (mock IdP); the frontend prefixes its API base.
            "authorize_url": "/idp/authorize",
            "scope": "openid email profile",
        },
    }


@router.post("/token", response_model=SessionOut)
def exchange_code(
    body: TokenExchangeRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionOut:
    """Final step of the authorization code flow: swap code + PKCE verifier for Peerpoint tokens."""
    try:
        claims = idp.exchange_code(body.code, body.code_verifier, body.redirect_uri)
    except idp.IdpError as exc:
        audit(db, "sign_in_failed", None, str(exc))
        raise HTTPException(status_code=400, detail="Sign-in failed. Please try again.")

    email = str(claims["email"]).lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None or not user.is_active:
        audit(db, "sign_in_denied", user.id if user else None, f"no active employee for {email}")
        raise HTTPException(status_code=403, detail="No active Peerpoint account for this identity")
    return _start_session(db, response, user, "sign_in")


@router.post("/refresh", response_model=SessionOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    """Trade the refresh cookie for a new access token. The refresh token is rotated."""
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(status_code=401, detail="No refresh token")
    user, new_raw, reason = rotate_refresh_token(db, raw)
    if user is None:
        audit(db, "refresh_failed", None, reason)
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    full = load_user(db, user.id)
    access = create_access_token(db, full)
    _set_refresh_cookie(response, new_raw, refresh_lifetime_hours(db))
    audit(db, "token_refresh", full.id, None)
    return SessionOut(authenticated=True, user=user_to_out(full), token=access)


@router.post("/logout", response_model=SessionOut)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    raw = request.cookies.get(settings.refresh_cookie_name)
    user_id = revoke_refresh_token(db, raw) if raw else None
    _clear_refresh_cookie(response)
    audit(db, "sign_out", user_id, None)
    return SessionOut(authenticated=False, user=None)


@router.get("/me", response_model=SessionOut)
def me(user: User = Depends(get_current_user)) -> SessionOut:
    return SessionOut(authenticated=True, user=user_to_out(user))


# --- demo mode only ------------------------------------------------------------------------


def _require_demo_mode() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/users", response_model=list[UserOut])
def list_dev_users(
    db: Session = Depends(get_db),
    _: None = Depends(_require_demo_mode),
) -> list[UserOut]:
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
    _: None = Depends(_require_demo_mode),
) -> SessionOut:
    user = load_user(db, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _start_session(db, response, user, "sign_in_demo")
