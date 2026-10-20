from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    Entry,
    EntryVersion,
    Tag,
    Team,
    TeamMembership,
    User,
    VersionStatus,
    entry_tags,
)
from app.services.tags import normalize_tag

# Filter value -> stored values (the data holds both the seed spelling and the API spelling).
SCOPE_ALIASES = {
    "country": ["country", "country-specific"],
    "eu": ["eu", "eu-wide"],
    "universal": ["universal"],
}
STATUS_ALIASES = {
    "unverified": ["unverified"],
    "verified": ["verified"],
    "outdated": ["stale", "outdated"],
}
VERIFIER_ROLES = ["Manager", "Team Lead", "Senior Expert"]


@dataclass
class SearchFilters:
    countries: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    verifier_roles: list[str] = field(default_factory=list)
    author_ids: list[int] = field(default_factory=list)
    team_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    updated_from: date | None = None
    updated_to: date | None = None


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


def _verifier_role(version: EntryVersion) -> str | None:
    latest = None
    for ver in version.verifications:
        if ver.action == "verify":
            latest = ver
    return latest.role if latest else None


def search_entries(
    db: Session,
    query: str | None,
    user_country: str | None,
    filters: SearchFilters | None = None,
) -> list[Entry]:
    f = filters or SearchFilters()
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

    # Different filters combine with AND; several values of one filter combine with OR.
    if f.countries:
        q = q.filter(func.lower(Entry.country).in_([c.lower() for c in f.countries]))
    if f.departments:
        q = q.filter(func.lower(Entry.department).in_([d.lower() for d in f.departments]))
    if f.categories:
        q = q.join(Category, Category.id == Entry.category_id).filter(
            func.lower(Category.name).in_([c.lower() for c in f.categories])
        )
    if f.statuses:
        stored = [v for s in f.statuses for v in STATUS_ALIASES.get(s.lower(), [s.lower()])]
        q = q.filter(func.lower(EntryVersion.status).in_(stored))
    if f.scopes:
        stored = [v for s in f.scopes for v in SCOPE_ALIASES.get(s.lower(), [s.lower()])]
        q = q.filter(func.lower(Entry.scope).in_(stored))
    if f.author_ids:
        q = q.filter(Entry.author_id.in_(f.author_ids))
    if f.team_ids:
        q = q.filter(Entry.author_id.in_(
            select(TeamMembership.user_id).where(TeamMembership.team_id.in_(f.team_ids))
        ))
    if f.tags:
        # Several tags are one filter, so they combine with OR; names are matched normalized.
        wanted = [normalize_tag(t) for t in f.tags if normalize_tag(t)]
        q = q.filter(Entry.id.in_(
            select(entry_tags.c.entry_id).join(Tag, Tag.id == entry_tags.c.tag_id).where(Tag.name.in_(wanted))
        ))
    if f.updated_from:
        q = q.filter(Entry.updated_at >= datetime.combine(f.updated_from, time.min))
    if f.updated_to:
        q = q.filter(Entry.updated_at <= datetime.combine(f.updated_to, time.max))

    results = q.all()

    if f.verifier_roles:
        wanted = {r.lower() for r in f.verifier_roles}
        results = [
            (e, v) for e, v in results
            if v.status == VersionStatus.VERIFIED.value
            and (_verifier_role(v) or "").lower() in wanted
        ]

    def score(entry_version_pair):
        entry, version = entry_version_pair
        s = 0.0
        # Verification + role
        s += _role_rank(version.status, _verifier_role(version)) * 100

        # Country match: prefer the user's country or the filtered country
        target = user_country or (f.countries[0] if len(f.countries) == 1 else None)
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


def search_facets(db: Session) -> dict:
    """Options for the filter panel."""
    countries = sorted({c for (c,) in db.query(Entry.country).distinct() if c})
    departments = sorted({d for (d,) in db.query(Entry.department).distinct() if d})
    categories = [n for (n,) in db.query(Category.name).order_by(Category.name)]
    author_ids = {a for (a,) in db.query(Entry.author_id).distinct()}
    authors = (
        db.query(User).filter(User.id.in_(author_ids)).order_by(User.display_name).all()
        if author_ids else []
    )
    return {
        "countries": countries,
        "departments": departments,
        "categories": categories,
        "statuses": [
            {"value": "unverified", "label": "Unverified"},
            {"value": "verified", "label": "Verified"},
            {"value": "outdated", "label": "Outdated"},
        ],
        "scopes": [
            {"value": "country", "label": "Country-specific"},
            {"value": "eu", "label": "EU-wide"},
            {"value": "universal", "label": "Universal"},
        ],
        "verifier_roles": VERIFIER_ROLES,
        "authors": [{"id": u.id, "name": u.display_name} for u in authors],
        "teams": [{"id": t.id, "name": t.name} for t in db.query(Team).order_by(Team.name)],
    }
