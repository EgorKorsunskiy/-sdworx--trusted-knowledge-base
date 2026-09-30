from datetime import datetime

from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models import (
    Category,
    Entry,
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


def seed_all() -> None:
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        if db.query(User).first():
            print("Database already seeded.")
            return

        # Default category
        payroll_category = Category(
            name="Freelance / contractor payroll",
            description="Rules and guidance for freelance and contractor payroll in Belgium/EU",
            is_default=True,
        )
        db.add(payroll_category)
        db.flush()

        # Team: Payroll Consultants Belgium
        payroll_team = Team(
            name="Payroll Consultants Belgium",
            department="Payroll",
            description="Belgian payroll consulting team",
        )
        db.add(payroll_team)
        db.flush()

        # Users
        users_data = [
            {
                "email": "employee.a@sdworx.example",
                "display_name": "Employee A",
                "department": "Payroll",
                "title": "Payroll Consultant",
                "roles": [RoleType.EMPLOYEE.value],
            },
            {
                "email": "employee.b@sdworx.example",
                "display_name": "Employee B",
                "department": "Payroll",
                "title": "Payroll Consultant",
                "roles": [RoleType.EMPLOYEE.value],
            },
            {
                "email": "employee.c@sdworx.example",
                "display_name": "Employee C",
                "department": "Payroll",
                "title": "Payroll Consultant",
                "roles": [RoleType.EMPLOYEE.value],
            },
            {
                "email": "senior.expert@sdworx.example",
                "display_name": "Senior Expert",
                "department": "Payroll",
                "title": "Senior Payroll Expert",
                "roles": [RoleType.EMPLOYEE.value, RoleType.EXPERT.value],
            },
            {
                "email": "team.lead@sdworx.example",
                "display_name": "Team Lead",
                "department": "Payroll",
                "title": "Payroll Team Lead",
                "roles": [RoleType.EMPLOYEE.value, RoleType.TEAM_LEAD.value],
            },
            {
                "email": "manager@sdworx.example",
                "display_name": "Manager",
                "department": "Payroll",
                "title": "Payroll Manager",
                "roles": [RoleType.EMPLOYEE.value, RoleType.MANAGER.value],
            },
            {
                "email": "admin@sdworx.example",
                "display_name": "Admin",
                "department": "Platform",
                "title": "Platform Admin",
                "roles": [RoleType.EMPLOYEE.value, RoleType.ADMIN.value],
            },
        ]

        created_users: dict[str, User] = {}
        for data in users_data:
            u = User(
                email=data["email"],
                display_name=data["display_name"],
                department=data["department"],
                title=data["title"],
            )
            db.add(u)
            db.flush()
            created_users[data["display_name"]] = u
            for role in data["roles"]:
                db.add(UserRole(user_id=u.id, role=role.value if hasattr(role, "value") else role))

        # Team memberships: primary for A/B/C + lead/manager
        for name in ["Employee A", "Employee B", "Employee C", "Team Lead", "Manager"]:
            u = created_users[name]
            db.add(TeamMembership(user_id=u.id, team_id=payroll_team.id, is_primary=True))

        # Senior expert mapped to Payroll department
        expert = created_users["Senior Expert"]
        db.add(VerifierDepartmentMap(user_id=expert.id, department="Payroll"))

        # System settings
        settings = [
            SystemSetting(key="duplicate_similarity_threshold", value="0.6", value_type="float", description="Default duplicate warning threshold"),
            SystemSetting(key="stale_hint_months", value="12", value_type="int", description="Months before showing may-be-outdated hint"),
            SystemSetting(key="expert_vote_multiplier", value="1.3", value_type="float", description="Weight multiplier for senior-expert votes"),
            SystemSetting(key="reputation_verified", value="10", value_type="int", description="Reputation for verified entry"),
            SystemSetting(key="reputation_vote", value="2", value_type="int", description="Reputation for correct vote"),
            SystemSetting(key="reputation_pr_merged", value="5", value_type="int", description="Reputation for merged PR"),
            SystemSetting(key="reputation_cited", value="3", value_type="int", description="Reputation for citation"),
        ]
        db.add_all(settings)

        # Seed one sample entry from Employee A (unverified)
        author = created_users["Employee A"]
        entry = Entry(
            public_id="PP-BE-FRE-00001",
            scope="country-specific",
            department="Payroll",
            country="BE",
            category_id=payroll_category.id,
            author_id=author.id,
            team_id=payroll_team.id,
        )
        db.add(entry)
        db.flush()

        tag = Tag(name="dmfa")
        db.add(tag)
        db.flush()
        entry.tags.append(tag)
        author_tag = Tag(name=author.display_name.lower())
        db.add(author_tag)
        db.flush()
        entry.tags.append(author_tag)

        version = EntryVersion(
            entry_id=entry.id,
            version_number=1,
            title="Belgian freelancer DMFA filing deadline",
            body="Freelancers in Belgium must be reported to the DMFA at least once per quarter, via the client's payroll provider or social secretariat.",
            justification="Official DMFA guidance and internal payroll playbook",
            status=VersionStatus.UNVERIFIED.value,
            change_note="Created",
            edited_by_id=author.id,
        )
        db.add(version)

        db.commit()
        print("Seeded database with demo users and one sample entry.")


if __name__ == "__main__":
    seed_all()
