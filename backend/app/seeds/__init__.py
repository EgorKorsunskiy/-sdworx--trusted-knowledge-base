import json
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import MOCK_DATA_DIR
from app.database import Base, engine
from app.services.public_id import make_public_id
from app.models import (
    Category,
    ClientProject,
    Company,
    Entry,
    EntryScope,
    EntryVersion,
    Project,
    ProjectMembership,
    RoleType,
    SystemSetting,
    Tag,
    Team,
    TeamMembership,
    User,
    UserRole,
    VerifierDepartmentMap,
    Verification,
    VersionStatus,
)

HISTORY_DEMO_TAG = "history-demo"


def _load(name: str) -> list[dict]:
    """Read mock_data/<name>.json; a missing file means no rows of that kind."""
    path = MOCK_DATA_DIR / f"{name}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _tag(db: Session, name: str) -> Tag:
    """Shared tag entity for a mock-data tag name (normalized; 'kind:value' names are automatic)."""
    from app.services.tags import AUTOMATIC, KEYWORD, get_or_create_tag, is_automatic_name

    return get_or_create_tag(db, name, AUTOMATIC if is_automatic_name(name) else KEYWORD)


def _add_entry(db: Session, data: dict, users: dict[str, User], now: datetime) -> Entry:
    """Create one entry from its mock_data form; see mock_data/README.md for the fields."""
    author = users[data["author"]]
    category = db.query(Category).filter(Category.name == data["category"]).one()
    if data.get("team"):
        team = db.query(Team).filter(Team.name == data["team"]).one()
    else:
        # Like a real submission, the entry belongs to the author's primary team
        membership = db.query(TeamMembership).filter_by(user_id=author.id, is_primary=True).first()
        team = membership.team if membership else None

    def at(days_ago: int | None) -> datetime:
        return now - timedelta(days=days_ago) if days_ago is not None else now

    versions = data["versions"]
    country = data.get("country")
    entry = Entry(
        public_id=data.get("public_id") or make_public_id(db, country, category.name),
        scope=data.get("scope", EntryScope.COUNTRY.value),
        department=data.get("department") or author.department or "General",
        country=country,
        category_id=category.id,
        author_id=author.id,
        team_id=team.id if team else None,
        created_at=at(versions[0].get("created_days_ago")),
        updated_at=at(versions[-1].get("created_days_ago")),
    )
    db.add(entry)
    db.flush()
    # The author is a contact with the basis from the mock data (default: Responsible)
    from app.services.contacts import add_contact

    add_contact(db, entry, author.id, data.get("basis", "responsible"), data.get("basis_source"), role="author")

    for name in data.get("tags", []):
        tag = _tag(db, name)
        if tag not in entry.tags:
            entry.tags.append(tag)
    from app.services.tags import add_auto_tags

    add_auto_tags(db, entry, author)  # country, date, author, department, role (FR-E2)

    for number, v in enumerate(versions, start=1):
        version = EntryVersion(
            entry_id=entry.id,
            version_number=number,
            title=v["title"],
            body=v["body"],
            justification=v.get("justification"),
            status=v.get("status", VersionStatus.UNVERIFIED.value),
            change_note=v.get("change_note"),
            edited_by_id=users[v.get("edited_by", data["author"])].id,
            created_at=at(v.get("created_days_ago")),
        )
        db.add(version)
        db.flush()
        for ver in v.get("verifications", []):
            db.add(Verification(
                version_id=version.id,
                verifier_id=users[ver["verifier"]].id,
                role=ver["role"],
                action="verify",
                created_at=at(ver.get("days_ago")),
            ))
    return entry


def seed_all() -> None:
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        if db.query(User).first():
            print("Database already seeded.")
            return

        for data in _load("categories"):
            db.add(Category(**data))

        teams = _load("teams")
        for data in teams:
            db.add(Team(name=data["name"], department=data["department"], description=data.get("description")))
        db.flush()

        # Users are keyed by email; insertion order defines their ids
        users: dict[str, User] = {}
        for data in _load("users"):
            u = User(
                email=data["email"],
                display_name=data["display_name"],
                department=data.get("department"),
                title=data.get("title"),
                country=data.get("country"),
            )
            db.add(u)
            db.flush()
            users[u.email] = u
            for role in data.get("roles", [RoleType.EMPLOYEE.value]):
                db.add(UserRole(user_id=u.id, role=role))
            # Senior experts: departments they may verify
            for department in data.get("expert_departments", []):
                db.add(VerifierDepartmentMap(user_id=u.id, department=department))

        for data in teams:
            team = db.query(Team).filter(Team.name == data["name"]).one()
            team.lead_user_id = users[data["lead"]].id if data.get("lead") else None
            for m in data.get("members", []):
                db.add(TeamMembership(
                    user_id=users[m["user"]].id,
                    team_id=team.id,
                    is_primary=m.get("primary", False),
                    role=m.get("role", "Member"),
                ))
        db.flush()

        entries = _load("entries")
        now = datetime.utcnow()
        for data in entries:
            _add_entry(db, data, users, now)

        db.commit()
        print(f"Seeded database from {MOCK_DATA_DIR} ({len(users)} users, {len(entries)} entries).")

    seed_people()
    seed_settings()
    seed_companies()
    backfill_contacts()


def backfill_contacts() -> None:
    """Authors of entries from before authorship bases existed become Responsible contacts (idempotent)."""
    from app.services.contacts import backfill_author_contacts

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        backfill_author_contacts(db)


def seed_parser_demo() -> None:
    """Run the stub parser agent over the mock meetings and chats (idempotent; Admins' agent settings apply)."""
    from app.services.parser_agent import load_mock_sources, purge_expired_sources

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if db.query(User).filter(User.email == "employee.a@sdworx.example").first() is None:
            return  # not the demo dataset
        count = load_mock_sources(db)
        purge_expired_sources(db)
        if count:
            print(f"Imported {count} mock sources through the stub parser agent.")


def seed_companies() -> None:
    """Client companies and their client projects from companies.json (idempotent, fills an already-seeded DB)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if db.query(Company).first():
            return
        for data in _load("companies"):
            company = Company(name=data["name"], country=data.get("country"))
            db.add(company)
            db.flush()
            for name in data.get("client_projects", []):
                db.add(ClientProject(name=name, company_id=company.id))
        db.commit()


def normalize_tags() -> None:
    """Bring tags created before tags were entities in line (names, types, country tags); idempotent."""
    from app.services.tags import normalize_existing_tags

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        normalize_existing_tags(db)


def finish_legacy_pull_requests() -> None:
    """PRs the old two-step rule left 'author_approved' are merged now (idempotent)."""
    from app.services.pull_requests import finish_legacy_author_approved

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        finish_legacy_author_approved(db)


def seed_settings() -> None:
    """Add settings from settings.json that the database lacks (idempotent, also fills an already-seeded DB).

    This includes the token lifetimes (access_token_minutes, refresh_token_hours) Admins can change."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        existing = {s.key for s in db.query(SystemSetting).all()}
        for data in _load("settings"):
            if data["key"] not in existing:
                db.add(SystemSetting(**data))
        db.commit()


def seed_people() -> None:
    """Internal projects and their members from projects.json (idempotent, also fills an already-seeded DB)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if db.query(Project).first():
            return
        projects = _load("projects")
        emails = {p["lead"] for p in projects} | {m["user"] for p in projects for m in p["members"]}
        users = {u.email: u for u in db.query(User).filter(User.email.in_(emails))}
        if len(users) < len(emails):
            return  # not the demo dataset

        for data in projects:
            project = Project(
                name=data["name"],
                description=data.get("description"),
                status=data.get("status", "active"),
                lead_user_id=users[data["lead"]].id,
            )
            db.add(project)
            db.flush()
            for m in data["members"]:
                db.add(ProjectMembership(
                    user_id=users[m["user"]].id,
                    project_id=project.id,
                    role=m.get("role", "Member"),
                    start_date=date.fromisoformat(m["start_date"]),
                    end_date=date.fromisoformat(m["end_date"]) if m.get("end_date") else None,
                ))
        db.commit()
        print("Seeded projects.")


def _insert_demo_entry(db: Session) -> str | None:
    """Insert the multi-version entry from history_demo.json for the change log demo. Returns its public id."""
    if db.query(Entry).join(Entry.tags).filter(Tag.name == HISTORY_DEMO_TAG).first():
        return None
    entries = _load("history_demo")
    emails = {d["author"] for d in entries} | {
        email
        for d in entries
        for v in d["versions"]
        for email in [v.get("edited_by", d["author"]), *(x["verifier"] for x in v.get("verifications", []))]
    }
    users = {u.email: u for u in db.query(User).filter(User.email.in_(emails))}
    if not entries or len(users) < len(emails):
        return None  # not the demo dataset
    now = datetime.utcnow()
    public_ids = [_add_entry(db, data, users, now).public_id for data in entries]
    db.commit()
    return public_ids[0]


def seed_history_demo() -> None:
    """Demo entry with 3 versions for the change log / diff view (idempotent)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        public_id = _insert_demo_entry(db)
        if public_id:
            print(f"Seeded history demo entry {public_id}.")


if __name__ == "__main__":
    seed_all()
