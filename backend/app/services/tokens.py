"""JWT access tokens, rotating refresh tokens, signing keys and the audit log."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, RefreshToken, SystemSetting, User

ALGORITHM = "RS256"

_keys: dict[str, tuple] = {}


def _load_keypair(name: str) -> tuple:
    """RSA keypair stored in settings.keys_dir; generated on first use."""
    if name not in _keys:
        settings.keys_dir.mkdir(parents=True, exist_ok=True)
        path = settings.keys_dir / f"{name}.pem"
        if path.exists():
            private = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            path.write_bytes(
                private.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            path.chmod(0o600)
        _keys[name] = (private, private.public_key())
    return _keys[name]


def private_key(name: str):
    return _load_keypair(name)[0]


def public_key(name: str):
    return _load_keypair(name)[1]


def get_int_setting(db: Session, key: str, default: int) -> int:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    try:
        return int(row.value) if row else default
    except ValueError:
        return default


# --- access tokens -----------------------------------------------------------------------


def create_access_token(db: Session, user: User) -> str:
    minutes = get_int_setting(db, "access_token_minutes", settings.access_token_minutes)
    now = datetime.now(timezone.utc)
    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user.id),
        "email": user.email,
        "roles": [r.role for r in user.roles],
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, private_key("peerpoint"), algorithm=ALGORITHM, headers={"kid": "peerpoint-1"})


def decode_access_token(token: str) -> dict:
    """Validates signature, expiry, issuer and audience. Raises jwt.PyJWTError."""
    return jwt.decode(
        token,
        public_key("peerpoint"),
        algorithms=[ALGORITHM],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        leeway=5,
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
    )


# --- refresh tokens ----------------------------------------------------------------------


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


def refresh_lifetime_hours(db: Session) -> int:
    return get_int_setting(db, "refresh_token_hours", settings.refresh_token_hours)


def issue_refresh_token(db: Session, user: User, family_id: str | None = None) -> tuple[str, RefreshToken]:
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        user_id=user.id,
        token_hash=_hash(raw),
        family_id=family_id or uuid.uuid4().hex,
        expires_at=_now() + timedelta(hours=refresh_lifetime_hours(db)),
    )
    db.add(row)
    db.flush()
    return raw, row


def revoke_family(db: Session, family_id: str) -> None:
    for row in db.query(RefreshToken).filter_by(family_id=family_id, revoked_at=None).all():
        row.revoked_at = _now()


def revoke_all_for_user(db: Session, user_id: int) -> int:
    rows = db.query(RefreshToken).filter_by(user_id=user_id, revoked_at=None).all()
    for row in rows:
        row.revoked_at = _now()
    return len(rows)


def rotate_refresh_token(db: Session, raw: str) -> tuple[User | None, str | None, str]:
    """Returns (user, new_raw_token, reason). On failure user and token are None."""
    row = db.query(RefreshToken).filter_by(token_hash=_hash(raw)).first()
    if row is None:
        return None, None, "unknown token"
    if row.revoked_at is not None:
        # A used or revoked token came back: assume theft and kill the whole family.
        revoke_family(db, row.family_id)
        db.commit()
        return None, None, "token reuse detected"
    if row.expires_at < _now():
        return None, None, "expired"
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or not user.is_active:
        revoke_family(db, row.family_id)
        db.commit()
        return None, None, "inactive employee"
    row.revoked_at = _now()
    new_raw, new_row = issue_refresh_token(db, user, family_id=row.family_id)
    row.replaced_by_id = new_row.id
    db.commit()
    return user, new_raw, "ok"


def revoke_refresh_token(db: Session, raw: str) -> int | None:
    """Revokes the presented token and returns its user id (None if unknown)."""
    row = db.query(RefreshToken).filter_by(token_hash=_hash(raw)).first()
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()
    return row.user_id


# --- audit log ---------------------------------------------------------------------------


def audit(db: Session, event: str, user_id: int | None = None, detail: str | None = None) -> None:
    db.add(AuditLog(event=event, user_id=user_id, detail=detail))
    db.commit()
