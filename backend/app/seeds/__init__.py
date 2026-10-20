import json

from sqlalchemy.orm import Session

from app.config import MOCK_DATA_DIR
from app.database import Base, engine
from app.models import (
    Category,
    Entry,
    EntryScope,
    EntryVersion,
    RoleType,
    SystemSetting,
    Tag,
    Team,
    TeamMembership,
    User,
    UserRole,
    VerifierDepartmentMap,
    VersionStatus,
)


def _load(name: str) -> list[dict]:
    """Read mock_data/<name>.json; a missing file means no rows of that kind."""
    path = MOCK_DATA_DIR / f"{name}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def seed_all() -> None:
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        if db.query(User).first():
            print("Database already seeded.")
            return

        categories: dict[str, Category] = {}
        for data in _load("categories"):
            category = Category(**data)
            db.add(category)
            categories[category.name] = category

        teams: dict[str, Team] = {}
        for data in _load("teams"):
            team = Team(**data)
            db.add(team)
            teams[team.name] = team
        db.flush()

        # Users are keyed by email; insertion order defines their ids
        users: dict[str, User] = {}
        user_teams: dict[str, str] = {}
        for data in _load("users"):
            u = User(
                email=data["email"],
                display_name=data["display_name"],
                department=data.get("department"),
                title=data.get("title"),
            )
            db.add(u)
            db.flush()
            users[u.email] = u
            for role in data.get("roles", [RoleType.EMPLOYEE.value]):
                db.add(UserRole(user_id=u.id, role=role))
            if data.get("team"):
                user_teams[u.email] = data["team"]
                db.add(TeamMembership(user_id=u.id, team_id=teams[data["team"]].id, is_primary=True))
            # Senior experts: departments they may verify
            for department in data.get("expert_departments", []):
                db.add(VerifierDepartmentMap(user_id=u.id, department=department))

        db.add_all(SystemSetting(**data) for data in _load("settings"))

        tags: dict[str, Tag] = {}
        entries = _load("entries")
        for data in entries:
            author = users[data["author"]]
            # Like a real submission, the entry belongs to the author's team unless set explicitly
            team_name = data.get("team") or user_teams.get(author.email)
            entry = Entry(
                public_id=data["public_id"],
                scope=data.get("scope", EntryScope.COUNTRY.value),
                department=data.get("department") or author.department or "General",
                country=data.get("country"),
                category_id=categories[data["category"]].id,
                author_id=author.id,
                team_id=teams[team_name].id if team_name else None,
            )
            db.add(entry)
            db.flush()

            for name in data.get("tags", []):
                if name not in tags:
                    tags[name] = Tag(name=name)
                    db.add(tags[name])
                    db.flush()
                entry.tags.append(tags[name])

            for number, v in enumerate(data["versions"], start=1):
                db.add(EntryVersion(
                    entry_id=entry.id,
                    version_number=number,
                    title=v["title"],
                    body=v["body"],
                    justification=v.get("justification"),
                    status=v.get("status", VersionStatus.UNVERIFIED.value),
                    change_note=v.get("change_note"),
                    edited_by_id=users[v.get("edited_by", data["author"])].id,
                ))

        db.commit()
        print(f"Seeded database from {MOCK_DATA_DIR} ({len(users)} users, {len(entries)} entries).")


if __name__ == "__main__":
    seed_all()
