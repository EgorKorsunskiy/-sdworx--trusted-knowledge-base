from sqlalchemy.orm import Session

from app.models import SystemSetting, User


def reputation_value(db: Session, key: str) -> int:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    try:
        return int(setting.value) if setting else 0
    except ValueError:
        return 0


def award(db: Session, user: User, key: str) -> int:
    """Add the configured points for `key` to the user's reputation (no commit). Returns the points."""
    points = reputation_value(db, key)
    if points > 0:
        user.reputation = (user.reputation or 0) + points
    return max(points, 0)
