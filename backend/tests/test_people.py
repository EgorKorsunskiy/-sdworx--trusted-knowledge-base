from datetime import date, timedelta

from tests.conftest import login
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_profile_teams_and_projects(client):
    r = client.get("/people/1", headers=login(client, 1))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["country"] == "BE"
    teams = {t["name"]: t for t in p["teams"]}
    assert teams["Payroll Consultants Belgium"]["is_primary"] is True
    assert teams["Payroll Consultants Belgium"]["role"] == "Member"
    assert teams["Payroll Experts"]["is_primary"] is False
    assert p["teams"][0]["name"] == "Payroll Consultants Belgium"
    projects = {x["name"]: x for x in p["projects"]}
    assert projects["Contractor Onboarding Revamp"]["ended"] is True
    assert projects["Freelancer DMFA Automation"]["ended"] is False
    assert projects["Freelancer DMFA Automation"]["role"] == "Contributor"
    assert p["projects"][-1]["name"] == "Contractor Onboarding Revamp"


def test_profile_empty_for_admin(client):
    r = client.get("/people/7", headers=login(client, 1))
    assert r.status_code == 200
    p = r.json()
    assert p["teams"] == [] and p["projects"] == [] and p["entries"] == []
    assert client.get("/people/999", headers=login(client, 1)).status_code == 404


def test_requires_auth(client):
    for url in ["/people/1", "/teams/1", "/projects/1", "/people", "/teams", "/projects"]:
        assert client.get(url).status_code == 401, url


def test_team_and_project_detail(client):
    h = login(client, 1)
    teams = client.get("/teams", headers=h).json()
    assert {t["name"] for t in teams} == {"Payroll Consultants Belgium", "Payroll Experts"}
    team = next(t for t in teams if t["name"] == "Payroll Experts")
    d = client.get(f"/teams/{team['id']}", headers=h).json()
    assert d["lead"]["id"] == 4
    assert {(m["user"]["id"], m["role"]) for m in d["members"]} == {
        (4, "Lead"), (1, "Member"), (2, "Member"),
    }
    assert all(m["is_primary"] is False for m in d["members"])

    projects = client.get("/projects", headers=h).json()
    assert len(projects) == 3
    proj = next(p for p in projects if p["name"] == "Freelancer DMFA Automation")
    d = client.get(f"/projects/{proj['id']}", headers=h).json()
    assert d["status"] == "active" and d["lead"]["id"] == 5
    assert {(m["user"]["id"], m["role"]) for m in d["members"]} == {
        (1, "Contributor"), (2, "Contributor"), (4, "SME"), (5, "Project lead"),
    }
    assert client.get("/teams/999", headers=h).status_code == 404
    assert client.get("/projects/999", headers=h).status_code == 404


def test_people_search(client):
    h = login(client, 1)
    r = client.get("/people", params={"q": "employee"}, headers=h)
    assert [u["display_name"] for u in r.json()] == ["Employee A", "Employee B", "Employee C"]
    assert len(client.get("/people", headers=h).json()) == 7


def test_admin_creates_project_and_member(client):
    admin = login(client, 7)
    r = client.post(
        "/admin/projects", headers=admin, json={"name": "New Project", "lead_user_id": 4}
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.post(
        "/admin/projects", headers=admin, json={"name": "New Project"}
    ).status_code == 409
    assert client.post(
        "/admin/projects", headers=admin, json={"name": "X", "lead_user_id": 999}
    ).status_code == 422

    r = client.post(
        f"/admin/projects/{pid}/members", headers=admin, json={"user_id": 3, "role": "Analyst"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["members"][0]["start_date"] == date.today().isoformat()
    assert client.post(
        f"/admin/projects/{pid}/members", headers=admin, json={"user_id": 3}
    ).status_code == 409

    profile = client.get("/people/3", headers=login(client, 1)).json()
    mine = next(p for p in profile["projects"] if p["name"] == "New Project")
    assert mine["role"] == "Analyst" and mine["ended"] is False

    user = login(client, 1)
    assert client.post("/admin/projects", headers=user, json={"name": "Nope"}).status_code == 403
    assert client.post(
        f"/admin/projects/{pid}/members", headers=user, json={"user_id": 2}
    ).status_code == 403


def test_membership_end_dates(client):
    admin = login(client, 7)
    pid = client.post("/admin/projects", headers=admin, json={"name": "Old"}).json()["id"]
    start = date.today() - timedelta(days=60)
    end = date.today() - timedelta(days=10)
    r = client.post(
        f"/admin/projects/{pid}/members",
        headers=admin,
        json={"user_id": 3, "start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert r.status_code == 201, r.text
    assert r.json()["members"][0]["ended"] is True
    profile = client.get("/people/3", headers=admin).json()
    assert next(p for p in profile["projects"] if p["name"] == "Old")["ended"] is True

    bad = client.post(
        f"/admin/projects/{pid}/members",
        headers=admin,
        json={"user_id": 2, "start_date": end.isoformat(), "end_date": start.isoformat()},
    )
    assert bad.status_code == 422

    mid = r.json()["members"][0]["membership_id"]
    r = client.patch(f"/admin/project-memberships/{mid}", headers=admin, json={"end_date": None})
    assert r.json()["members"][0]["ended"] is False
    assert client.delete(f"/admin/project-memberships/{mid}", headers=admin).status_code == 200
    assert client.get(f"/projects/{pid}", headers=admin).json()["members"] == []


def test_profile_lists_entries(client):
    p = client.get("/people/1", headers=login(client, 2)).json()
    e = next(x for x in p["entries"] if x["public_id"] == "PP-BE-FRE-00001")
    assert e["title"] == "Belgian freelancer DMFA filing deadline"
    assert e["status"] == "Unverified"


def test_seed_people_idempotent(client):
    from app import seeds as seeds_mod
    from app.models import Project, ProjectMembership, TeamMembership

    def counts():
        with Session(seeds_mod.engine) as db:
            return (
                db.query(Project).count(),
                db.query(ProjectMembership).count(),
                db.query(TeamMembership).count(),
            )

    before = counts()
    assert before[0] == 3
    seeds_mod.seed_people()
    seeds_mod.seed_people()
    assert counts() == before


def test_verification_regression(client):
    r = client.get("/approvals/pending", headers=login(client, 5))
    assert r.status_code == 200, r.text
    assert "PP-BE-FRE-00001" in {i["entry"]["public_id"] for i in r.json()}


def test_ensure_columns_old_schema():
    from app.database import _ensure_columns

    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text("CREATE TABLE team_memberships (id INTEGER PRIMARY KEY, is_primary BOOLEAN)")
        )
        conn.execute(text("INSERT INTO users (id) VALUES (1)"))
        conn.execute(text("INSERT INTO team_memberships (id, is_primary) VALUES (1, 1)"))
    for _ in range(2):
        _ensure_columns(eng)
    insp = inspect(eng)
    assert "country" in {c["name"] for c in insp.get_columns("users")}
    assert "lead_user_id" in {c["name"] for c in insp.get_columns("teams")}
    assert "role" in {c["name"] for c in insp.get_columns("team_memberships")}
    with eng.connect() as conn:
        assert conn.execute(text("SELECT country FROM users")).scalar() == "BE"
        assert conn.execute(text("SELECT role FROM team_memberships")).scalar() == "Member"


def test_second_primary_demotes_previous(client):
    admin = login(client, 7)
    teams = client.get("/teams", headers=admin).json()
    experts = next(t for t in teams if t["name"] == "Payroll Experts")
    r = client.post(
        f"/admin/teams/{experts['id']}/members",
        headers=admin,
        json={"user_id": 3, "is_primary": True},
    )
    assert r.status_code == 201, r.text
    assert client.post(
        f"/admin/teams/{experts['id']}/members", headers=admin, json={"user_id": 3}
    ).status_code == 409
    # Employee A (1) is already primary elsewhere; make Experts primary for them
    other = client.post(
        f"/admin/teams/{experts['id']}/members", headers=admin, json={"user_id": 7}
    )
    assert other.status_code == 201
    mid = next(m for m in other.json()["members"] if m["user"]["id"] == 7)["membership_id"]
    assert client.delete(f"/admin/team-memberships/{mid}", headers=admin).status_code == 200

    p = client.get("/people/3", headers=admin).json()
    primaries = [t["name"] for t in p["teams"] if t["is_primary"]]
    assert primaries == ["Payroll Experts"]
    assert len(p["teams"]) == 2
