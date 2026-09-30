import re

from sqlalchemy.orm import Session

from app.models import Entry


def make_public_id(db: Session, country: str | None, category_code: str) -> str:
    """Generate a stable public ID like PP-BE-FRE-00042."""
    country_code = (country or "UN").upper()[:2]
    cat_code = re.sub(r"[^a-zA-Z0-9]", "", category_code)[:3].upper() or "GEN"
    prefix = f"PP-{country_code}-{cat_code}"
    existing = (
        db.query(Entry.public_id)
        .filter(Entry.public_id.startswith(prefix + "-"))
        .order_by(Entry.public_id.desc())
        .first()
    )
    if existing:
        try:
            last = int(existing.public_id.split("-")[-1])
        except ValueError:
            last = 0
    else:
        last = 0
    return f"{prefix}-{last + 1:05d}"
