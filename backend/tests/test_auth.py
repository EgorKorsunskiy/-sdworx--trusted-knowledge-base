import base64
import hashlib
import re
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from app.config import settings
from app.main import app
from app.services import idp
from app.services.tokens import private_key
from tests.conftest import login

COOKIE = settings.refresh_cookie_name
REDIRECT = "http://localhost:5175/auth/callback"


def _pkce():
    verifier = base64.urlsafe_b64encode(b"v" * 40).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _claims(**over):
    now = int(time.time())
    base = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": "1",
        "iat": now,
        "exp": now + 600,
        "roles": ["employee"],
    }
    base.update(over)
    return base


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- every endpoint declares an access requirement ---------------------------------------

PUBLIC_PREFIXES = ("/idp/", "/docs", "/redoc", "/openapi.json")
PUBLIC_PATHS = {"/", "/health", "/auth/config", "/auth/token", "/auth/refresh", "/auth/logout", "/auth/users", "/auth/dev-login"}


def test_every_non_public_endpoint_requires_a_token(client):
    checked = 0
    # The OpenAPI schema lists every endpoint however the framework groups its routers
    for route_path, operations in app.openapi()["paths"].items():
        if route_path in PUBLIC_PATHS or route_path.startswith(PUBLIC_PREFIXES):
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        for method in operations:
            if method.upper() in ("HEAD", "OPTIONS"):
                continue
            r = client.request(method.upper(), path, json={})
            assert r.status_code == 401, f"{method.upper()} {route_path} answered {r.status_code} without a token"
            checked += 1
    assert checked > 30


# --- token validation --------------------------------------------------------------------


def test_access_token_claims(client):
    token = client.post("/auth/dev-login", json={"user_id": 4}).json()["token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == settings.jwt_issuer and claims["aud"] == settings.jwt_audience
    assert claims["sub"] == "4" and "expert" in claims["roles"]
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert jwt.get_unverified_header(token)["alg"] == "RS256"


@pytest.mark.parametrize(
    "make_token",
    [
        lambda: "garbage",
        lambda: jwt.encode(_claims(exp=int(time.time()) - 60), private_key("peerpoint"), algorithm="RS256"),
        lambda: jwt.encode(_claims(aud="someone-else"), private_key("peerpoint"), algorithm="RS256"),
        lambda: jwt.encode(_claims(iss="not-peerpoint"), private_key("peerpoint"), algorithm="RS256"),
        lambda: jwt.encode(_claims(), rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256"),
        lambda: jwt.encode(_claims(), "secret", algorithm="HS256"),
        lambda: jwt.encode(_claims(), None, algorithm="none"),
    ],
    ids=["garbage", "expired", "wrong-audience", "wrong-issuer", "foreign-key", "hs256", "alg-none"],
)
def test_invalid_tokens_are_rejected(client, make_token):
    assert client.get("/people/1", headers=_bearer(make_token())).status_code == 401


def test_401_without_token_and_403_without_permission(client):
    assert client.get("/admin/settings").status_code == 401
    assert client.get("/admin/settings", headers=login(client, 1)).status_code == 403
    assert client.get("/admin/settings", headers=login(client, 7)).status_code == 200


def test_roles_in_token_are_not_trusted(client):
    forged = jwt.encode(_claims(sub="1", roles=["admin"]), private_key("peerpoint"), algorithm="RS256")
    assert client.get("/admin/settings", headers=_bearer(forged)).status_code == 403


def test_token_lifetime_is_configurable_by_admin(client):
    admin = login(client, 7)
    r = client.put("/admin/settings/access_token_minutes", params={"value": "1"}, headers=admin)
    assert r.status_code == 200
    token = client.post("/auth/dev-login", json={"user_id": 1}).json()["token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 60


# --- refresh tokens ----------------------------------------------------------------------


def test_refresh_rotates_and_detects_reuse(client):
    client.post("/auth/dev-login", json={"user_id": 1})
    first = client.cookies.get(COOKIE)
    assert first

    r = client.post("/auth/refresh")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == 1 and r.json()["token"]
    second = client.cookies.get(COOKIE)
    assert second and second != first
    assert client.get("/people/1", headers=_bearer(r.json()["token"])).status_code == 200

    # Replaying the already-used token fails and revokes the whole family.
    client.cookies.clear()
    assert client.post("/auth/refresh", cookies={COOKIE: first}).status_code == 401
    client.cookies.clear()
    assert client.post("/auth/refresh", cookies={COOKIE: second}).status_code == 401


def test_refresh_without_cookie_is_401(client):
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revokes_the_refresh_token(client):
    client.post("/auth/dev-login", json={"user_id": 1})
    saved = client.cookies.get(COOKIE)
    assert client.post("/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.post("/auth/refresh", cookies={COOKIE: saved}).status_code == 401


def test_admin_can_force_sign_out(client):
    client.post("/auth/dev-login", json={"user_id": 1})
    saved = client.cookies.get(COOKIE)
    client.cookies.clear()

    assert client.post("/admin/users/1/revoke-tokens", headers=login(client, 2)).status_code == 403
    r = client.post("/admin/users/1/revoke-tokens", headers=login(client, 7))
    assert r.status_code == 200 and r.json()["revoked"] >= 1

    client.cookies.clear()
    assert client.post("/auth/refresh", cookies={COOKIE: saved}).status_code == 401


# --- OAuth2 authorization code + PKCE (mock IdP) -------------------------------------------


def _authorize_params(challenge, **over):
    p = {
        "response_type": "code",
        "client_id": settings.idp_client_id,
        "redirect_uri": REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "xyz",
    }
    p.update(over)
    return p


def _get_code(client, email="employee.a@sdworx.example", **over):
    verifier, challenge = _pkce()
    params = _authorize_params(challenge, **over)
    page = client.get("/idp/authorize", params=params)
    assert page.status_code == 200 and "Employee A" in page.text
    r = client.get("/idp/login", params={**params, "email": email}, follow_redirects=False)
    assert r.status_code == 302
    location = urlparse(r.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == REDIRECT
    query = parse_qs(location.query)
    assert query["state"] == ["xyz"]
    return query["code"][0], verifier


def test_authorization_code_flow_signs_in(client):
    code, verifier = _get_code(client)
    r = client.post("/auth/token", json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["email"] == "employee.a@sdworx.example"
    assert client.cookies.get(COOKIE)
    assert client.get("/auth/me", headers=_bearer(data["token"])).json()["user"]["id"] == 1


def test_code_is_single_use_and_pkce_is_enforced(client):
    code, verifier = _get_code(client)
    wrong = client.post("/auth/token", json={"code": code, "code_verifier": "x" * 50, "redirect_uri": REDIRECT})
    assert wrong.status_code == 400  # a failed attempt burns the code
    again = client.post("/auth/token", json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT})
    assert again.status_code == 400

    code, verifier = _get_code(client)
    assert client.post("/auth/token", json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT}).status_code == 200
    assert client.post("/auth/token", json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT}).status_code == 400


def test_redirect_uri_must_match(client):
    code, verifier = _get_code(client)
    r = client.post(
        "/auth/token",
        json={"code": code, "code_verifier": verifier, "redirect_uri": "http://evil.example/auth/callback"},
    )
    assert r.status_code == 400


def test_idp_rejects_bad_authorize_requests(client):
    _, challenge = _pkce()
    assert client.get("/idp/authorize", params=_authorize_params(challenge, redirect_uri="http://x.example/steal")).status_code == 400
    assert client.get("/idp/authorize", params=_authorize_params(challenge, code_challenge_method="plain")).status_code == 400
    assert client.get("/idp/authorize", params=_authorize_params(challenge, client_id="other")).status_code == 400


def test_unknown_employee_is_denied(client):
    verifier, challenge = _pkce()
    code = idp.issue_code("ghost@sdworx.example", "Ghost", settings.idp_client_id, REDIRECT, challenge)
    r = client.post("/auth/token", json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT})
    assert r.status_code == 403
    assert not client.cookies.get(COOKIE)


def test_idp_publishes_its_signing_key(client):
    keys = client.get("/idp/jwks.json").json()["keys"]
    assert keys[0]["kty"] == "RSA" and keys[0]["kid"] == "idp-1"


# --- demo mode -----------------------------------------------------------------------------


def test_demo_picker_is_off_when_demo_mode_is_disabled(client, monkeypatch):
    assert client.get("/auth/config").json()["demo_mode"] is True
    monkeypatch.setattr(settings, "demo_mode", False)
    assert client.get("/auth/config").json()["demo_mode"] is False
    assert client.get("/auth/users").status_code == 404
    assert client.post("/auth/dev-login", json={"user_id": 1}).status_code == 404


# --- audit log -----------------------------------------------------------------------------


def test_security_events_are_audit_logged(client):
    client.post("/auth/dev-login", json={"user_id": 1})
    client.post("/auth/refresh")
    client.get("/admin/settings", headers=login(client, 1))  # 403
    client.get("/people/1", headers=_bearer("garbage"))  # 401 with a bad token
    client.post("/auth/logout")
    client.post("/auth/refresh")  # no cookie any more: 401 but no audit noise
    code, verifier = _get_code(client)
    client.post("/auth/token", json={"code": code, "code_verifier": "bad" * 20, "redirect_uri": REDIRECT})

    log = client.get("/admin/audit-log", headers=login(client, 7)).json()
    events = [e["event"] for e in log]
    for expected in ("sign_in_demo", "token_refresh", "access_denied", "sign_out", "sign_in_failed"):
        assert expected in events, expected
    denied = [e["detail"] for e in log if e["event"] == "access_denied"]
    assert any("403 GET /admin/settings" in d for d in denied)
    assert any("401 GET /people/1" in d for d in denied)
    assert client.get("/admin/audit-log", headers=login(client, 1)).status_code == 403


def test_audit_log_is_append_only():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.database import Base
    from app.models import AuditLog

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        row = AuditLog(event="x")
        db.add(row)
        db.commit()
        row.event = "changed"
        with pytest.raises(RuntimeError):
            db.commit()
        db.rollback()
        db.delete(row)
        with pytest.raises(RuntimeError):
            db.commit()
