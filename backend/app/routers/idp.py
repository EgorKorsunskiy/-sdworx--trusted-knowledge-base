"""Mock identity provider endpoints (development only). See app/services/idp.py."""

from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.services import idp

router = APIRouter(prefix="/idp", tags=["mock-idp"])


def _validated(response_type, client_id, redirect_uri, code_challenge, code_challenge_method) -> None:
    try:
        idp.validate_authorize_request(
            response_type, client_id, redirect_uri, code_challenge, code_challenge_method
        )
    except idp.IdpError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/authorize", response_class=HTMLResponse)
def authorize(
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: str = Query(""),
    scope: str = Query("openid email profile"),
    db: Session = Depends(get_db),
) -> str:
    """Stand-in for the corporate login page: pick which employee signs in."""
    _validated(response_type, client_id, redirect_uri, code_challenge, code_challenge_method)
    hidden = "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">'
        for k, v in {
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
        }.items()
    )
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id).all()
    buttons = "".join(
        f'<button type="submit" name="email" value="{escape(u.email)}">'
        f"<strong>{escape(u.display_name)}</strong><span>{escape(u.email)}</span></button>"
        for u in users
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Mock identity provider</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#fafaf9;color:#1c1917;display:flex;
justify-content:center;padding:48px 16px}}
main{{background:#fff;border:1px solid #e7e5e4;border-radius:12px;padding:24px;width:100%;max-width:420px}}
h1{{font-size:18px;margin:0 0 4px}} p{{color:#78716c;font-size:13px;margin:0 0 16px}}
button{{display:flex;flex-direction:column;align-items:flex-start;width:100%;margin-top:8px;padding:10px 14px;
border:1px solid #e7e5e4;border-radius:8px;background:#fff;cursor:pointer;font:inherit}}
button:hover{{background:#fafaf9}} span{{font-size:12px;color:#78716c}}
</style></head>
<body><main>
<h1>SD Worx sign-in (mock)</h1>
<p>Development identity provider. Choose an employee to sign in as.</p>
<form method="get" action="login">{hidden}{buttons}</form>
</main></body></html>"""


@router.get("/login")
def login(
    email: str = Query(...),
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: str = Query(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    _validated(response_type, client_id, redirect_uri, code_challenge, code_challenge_method)
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=400, detail="Unknown employee")
    code = idp.issue_code(user.email, user.display_name, client_id, redirect_uri, code_challenge)
    query = {"code": code}
    if state:
        query["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)


@router.post("/token")
def token(
    grant_type: str = Form(...),
    code: str = Form(...),
    code_verifier: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
) -> dict:
    """Standard token endpoint, for completeness. Peerpoint itself calls idp.exchange_code directly."""
    if grant_type != "authorization_code" or client_id != settings.idp_client_id:
        raise HTTPException(status_code=400, detail="invalid_request")
    try:
        id_token = idp.redeem_code(code, code_verifier, redirect_uri)
    except idp.IdpError:
        raise HTTPException(status_code=400, detail="invalid_grant")
    return {"id_token": id_token, "token_type": "Bearer", "expires_in": idp.ID_TOKEN_TTL_SECONDS}


@router.get("/jwks.json")
def jwks() -> dict:
    return {"keys": [idp.public_jwk()]}
