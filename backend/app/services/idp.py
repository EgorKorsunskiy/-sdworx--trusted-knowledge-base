"""Built-in mock OpenID Connect provider (authorization code + PKCE).

Stands in for the SD Worx identity provider during development. Peerpoint only talks to it through
`exchange_code`, so replacing it with a real provider means swapping that one function (token
endpoint call + JWKS verification) and turning off the /idp routes.
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlparse

import jwt

from app.config import settings
from app.services.tokens import ALGORITHM, private_key, public_key

CODE_TTL_SECONDS = 300
ID_TOKEN_TTL_SECONDS = 300

_codes: dict[str, dict] = {}


class IdpError(Exception):
    pass


def validate_authorize_request(
    response_type: str, client_id: str, redirect_uri: str, code_challenge: str, method: str
) -> None:
    if response_type != "code":
        raise IdpError("unsupported response_type")
    if client_id != settings.idp_client_id:
        raise IdpError("unknown client_id")
    if method != "S256" or not code_challenge:
        raise IdpError("PKCE with code_challenge_method=S256 is required")
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path != "/auth/callback":
        raise IdpError("redirect_uri must be <origin>/auth/callback")


def issue_code(email: str, name: str, client_id: str, redirect_uri: str, code_challenge: str) -> str:
    code = secrets.token_urlsafe(32)
    _codes[code] = {
        "email": email,
        "name": name,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "expires": time.time() + CODE_TTL_SECONDS,
    }
    return code


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def redeem_code(code: str, code_verifier: str, redirect_uri: str) -> str:
    """IdP side: the token endpoint. Codes are single use. Returns a signed id_token."""
    entry = _codes.pop(code, None)
    if entry is None or entry["expires"] < time.time():
        raise IdpError("invalid or expired code")
    if entry["redirect_uri"] != redirect_uri:
        raise IdpError("redirect_uri mismatch")
    if not secrets.compare_digest(_s256(code_verifier), entry["code_challenge"]):
        raise IdpError("PKCE verification failed")
    now = int(time.time())
    claims = {
        "iss": settings.idp_issuer,
        "aud": entry["client_id"],
        "sub": entry["email"],
        "email": entry["email"],
        "name": entry["name"],
        "iat": now,
        "exp": now + ID_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(claims, private_key("idp"), algorithm=ALGORITHM, headers={"kid": "idp-1"})


def verify_id_token(id_token: str) -> dict:
    """Client side: validate the id_token signature, issuer, audience and expiry."""
    try:
        return jwt.decode(
            id_token,
            public_key("idp"),
            algorithms=[ALGORITHM],
            audience=settings.idp_client_id,
            issuer=settings.idp_issuer,
            leeway=5,
            options={"require": ["exp", "iat", "sub", "email"]},
        )
    except jwt.PyJWTError as exc:
        raise IdpError(f"invalid id_token: {exc}") from exc


def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """What Peerpoint calls after the browser returns with ?code=...: returns verified id_token claims."""
    if settings.idp_mode != "mock":
        raise IdpError("only the mock identity provider is configured")
    return verify_id_token(redeem_code(code, code_verifier, redirect_uri))


def public_jwk() -> dict:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key("idp"), as_dict=True)
    jwk.update({"kid": "idp-1", "use": "sig", "alg": ALGORITHM})
    return jwk
