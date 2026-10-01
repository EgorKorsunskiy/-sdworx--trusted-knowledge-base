from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models import Category, Entry, EntryVersion, VersionStatus


def _role_rank(status: str, role: str | None) -> int:
    if status != VersionStatus.VERIFIED.value:
        return 0
    if role == "Manager":
        return 4
    if role == "Team Lead":
        return 3
    if role == "Senior Expert":
        return 2
    return 1


def search_entries(
    db: Session,
    query: str | None,
    user_country: str | None,
    country: str | None,
    department: str | None,
    category: str | None,
    status: str | None,
) -> list[Entry]:
    q = (
        db.query(Entry, EntryVersion)
        .join(EntryVersion, Entry.id == EntryVersion.entry_id)
        .filter(EntryVersion.version_number == (
            db.query(func.max(EntryVersion.version_number))
            .filter(EntryVersion.entry_id == Entry.id)
            .correlate(Entry)
            .scalar_subquery()
        ))
    )

    if query:
        like = f"%{query}%"
        q = q.filter(or_(EntryVersion.title.ilike(like), EntryVersion.body.ilike(like)))
    if country:
        q = q.filter(Entry.country.ilike(country))
    if department:
        q = q.filter(Entry.department.ilike(department))
    if category:
        q = q.join(Category).filter(Category.name.ilike(category))
    if status:
        q = q.filter(EntryVersion.status.ilike(status))

    results = q.options().all()

    def score(entry_version_pair):
        entry, version = entry_version_pair
        s = 0.0
        # Verification + role
        latest_verification = None
        for ver in version.verifications:
            if ver.action == "verify":
                latest_verification = ver
        role = latest_verification.role if latest_verification else None
        s += _role_rank(version.status, role) * 100

        # Country match: prefer user's country or requested country
        target = user_country or country
        entry_country = (entry.country or "").lower()
        if target and entry_country and target.lower()[:2] == entry_country[:2]:
            s += 20
        if entry.scope in ("universal",):
            s += 10
        if entry.scope in ("eu", "EU-wide"):
            s += 5

        # Freshness / outdated penalty
        if version.status == VersionStatus.OUTDATED.value:
            s -= 50
        elif version.created_at is not None:
            created = version.created_at
            now = datetime.now(timezone.utc) if created.tzinfo else datetime.utcnow()
            if created.tzinfo is None and now.tzinfo:
                created = created.replace(tzinfo=timezone.utc)
            age_days = max((now - created).days, 0)
            s -= min(age_days, 365) / 365 * 5

        # Author reputation tie-break
        s += entry.author.reputation / 100

        # Text relevance rough boost
        if query and query.lower() in version.title.lower():
            s += 15

        return s

    results.sort(key=score, reverse=True)
    return [entry for entry, _ in results]
