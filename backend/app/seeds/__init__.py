from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import Base, engine
from app.services.public_id import make_public_id
from app.models import (
    Category,
    Entry,
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

    seed_people()
    seed_auth_settings()


def finish_legacy_pull_requests() -> None:
    """PRs the old two-step rule left 'author_approved' are merged now (idempotent)."""
    from app.services.pull_requests import finish_legacy_author_approved

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        finish_legacy_author_approved(db)


AUTH_SETTINGS = [
    ("access_token_minutes", "15", "int", "Lifetime of an access token (JWT) in minutes"),
    ("refresh_token_hours", "8", "int", "Lifetime of a refresh token in hours"),
]


def seed_auth_settings() -> None:
    """Token lifetime settings Admins can change (idempotent, also fills an already-seeded DB)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        existing = {s.key for s in db.query(SystemSetting).all()}
        for key, value, value_type, description in AUTH_SETTINGS:
            if key not in existing:
                db.add(SystemSetting(key=key, value=value, value_type=value_type, description=description))
        db.commit()


PEOPLE_EMAILS = {
    "Employee A": "employee.a@sdworx.example",
    "Employee B": "employee.b@sdworx.example",
    "Employee C": "employee.c@sdworx.example",
    "Senior Expert": "senior.expert@sdworx.example",
    "Team Lead": "team.lead@sdworx.example",
    "Manager": "manager@sdworx.example",
}


def seed_people() -> None:
    """Demo teams/projects/roles for the employee profile pages (idempotent)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if db.query(Project).first():
            return
        users: dict[str, User] = {}
        for label, email in PEOPLE_EMAILS.items():
            u = db.query(User).filter(User.email == email).first()
            if u is None:
                return  # not the demo dataset
            users[label] = u

        for u in db.query(User).filter(User.country.is_(None)).all():
            u.country = "BE"

        # Backfill the existing team: lead + membership roles
        team = db.query(Team).filter(Team.name == "Payroll Consultants Belgium").first()
        if team is not None:
            team.lead_user_id = users["Team Lead"].id
            for m in team.memberships:
                if m.user_id == users["Team Lead"].id:
                    m.role = "Lead"
                elif m.user_id == users["Manager"].id:
                    m.role = "Manager"

        # Second team: all memberships non-primary (verification relies on primary teams)
        experts = Team(
            name="Payroll Experts",
            department="Payroll",
            description="Cross-team payroll subject matter experts",
            lead_user_id=users["Senior Expert"].id,
        )
        db.add(experts)
        db.flush()
        for label, role in [("Senior Expert", "Lead"), ("Employee A", "Member"), ("Employee B", "Member")]:
            db.add(
                TeamMembership(
                    user_id=users[label].id, team_id=experts.id, is_primary=False, role=role
                )
            )

        def add_project(name, description, status, lead, members):
            p = Project(
                name=name,
                description=description,
                status=status,
                lead_user_id=users[lead].id,
            )
            db.add(p)
            db.flush()
            for label, role, start, end in members:
                db.add(
                    ProjectMembership(
                        user_id=users[label].id,
                        project_id=p.id,
                        role=role,
                        start_date=start,
                        end_date=end,
                    )
                )

        add_project(
            "Freelancer DMFA Automation",
            "Automate quarterly DMFA reporting for freelancers and contractors.",
            "active",
            "Team Lead",
            [
                ("Employee A", "Contributor", date(2026, 1, 15), None),
                ("Employee B", "Contributor", date(2026, 3, 1), None),
                ("Senior Expert", "SME", date(2026, 1, 15), None),
                ("Team Lead", "Project lead", date(2026, 1, 15), None),
            ],
        )
        add_project(
            "Contractor Onboarding Revamp",
            "Redesign of the contractor onboarding process (finished).",
            "completed",
            "Manager",
            [
                ("Employee A", "Contributor", date(2025, 3, 1), date(2025, 9, 30)),
                ("Employee C", "Contributor", date(2025, 3, 1), date(2025, 9, 30)),
                ("Senior Expert", "SME", date(2025, 3, 1), date(2025, 9, 30)),
                ("Manager", "Sponsor", date(2025, 3, 1), date(2025, 9, 30)),
            ],
        )
        add_project(
            "Quarterly Compliance Review",
            "Quarterly review of payroll compliance rules and knowledge base entries.",
            "active",
            "Senior Expert",
            [
                ("Senior Expert", "Lead", date(2026, 4, 1), None),
                ("Employee B", "Contributor", date(2026, 4, 1), None),
                ("Employee C", "Contributor", date(2026, 4, 1), None),
            ],
        )
        db.commit()
        print("Seeded teams and projects.")


HISTORY_DEMO_TAG = "history-demo"


def _insert_demo_entry(db: Session) -> str | None:
    """Insert a 3-version entry (Created / Clarified / Fixed) for the change log demo. Returns its public id."""
    users = {}
    for label, email in PEOPLE_EMAILS.items():
        u = db.query(User).filter(User.email == email).first()
        if u is None:
            return None
        users[label] = u
    if (
        db.query(Entry)
        .join(Entry.tags)
        .filter(Tag.name == HISTORY_DEMO_TAG)
        .first()
    ):
        return None
    category = db.query(Category).filter(Category.is_default.is_(True)).first()
    team = db.query(Team).filter(Team.name == "Payroll Consultants Belgium").first()
    if category is None:
        return None

    now = datetime.utcnow()
    t1, t2, t3 = now - timedelta(days=42), now - timedelta(days=21), now - timedelta(days=5)

    s1 = "Belgian freelancers pay social-security contributions through a social insurance fund."
    s2 = "The contribution rate is 20.5% of net taxable income."
    s2b = "The contribution rate is 20.5% of net taxable income, payable quarterly in advance."
    s3 = "Freelancers must register with a social insurance fund within 90 days of starting."
    s4 = "Freelancers who also work as employees may qualify for an exemption."

    entry = Entry(
        public_id=make_public_id(db, "BE", category.name),
        scope="country-specific",
        department="Payroll",
        country="BE",
        category_id=category.id,
        author_id=users["Employee A"].id,
        team_id=team.id if team else None,
        created_at=t1,
        updated_at=t3,
    )
    db.add(entry)
    db.flush()
    for name in (HISTORY_DEMO_TAG, "social-security"):
        tag = db.query(Tag).filter(Tag.name == name).first()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        entry.tags.append(tag)

    def add_version(n, user, when, title, body, justification, status, note):
        v = EntryVersion(
            entry_id=entry.id,
            version_number=n,
            title=title,
            body=body,
            justification=justification,
            status=status,
            change_note=note,
            edited_by_id=users[user].id,
            created_at=when,
        )
        db.add(v)
        db.flush()
        return v

    v1 = add_version(
        1, "Employee A", t1,
        "Belgian freelancer social-security contributions",
        " ".join([s1, s2, s3]),
        "NSSO guidance",
        VersionStatus.VERIFIED.value,
        "Created",
    )
    v2 = add_version(
        2, "Employee B", t2,
        "Belgian freelancer social-security contributions",
        " ".join([s1, s2b, s3, s4]),
        "NSSO guidance",
        VersionStatus.VERIFIED.value,
        "Clarified quarterly rate and added exemption",
    )
    add_version(
        3, "Senior Expert", t3,
        "Belgian freelancer social-security contributions (2026)",
        " ".join([s2b, s3, s4]),
        "NSSO guidance and the 2026 payroll playbook",
        VersionStatus.UNVERIFIED.value,
        "Fixed title, removed outdated sentence",
    )
    db.add(
        Verification(
            version_id=v1.id, verifier_id=users["Senior Expert"].id, role="Senior Expert",
            action="verify", created_at=t1 + timedelta(days=1),
        )
    )
    db.add(
        Verification(
            version_id=v2.id, verifier_id=users["Team Lead"].id, role="Team Lead",
            action="verify", created_at=t2 + timedelta(days=1),
        )
    )
    db.commit()
    return entry.public_id


def seed_history_demo() -> None:
    """Demo entry with 3 versions for the change log / diff view (idempotent)."""
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        public_id = _insert_demo_entry(db)
        if public_id:
            print(f"Seeded history demo entry {public_id}.")


if __name__ == "__main__":
    seed_all()
