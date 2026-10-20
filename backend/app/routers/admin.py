from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, require_roles
from app.services.tokens import audit, revoke_all_for_user
from app.models import (
    AuditLog,
    Project,
    ProjectMembership,
    SystemSetting,
    Team,
    TeamMembership,
    User,
    UserRole,
    VerifierDepartmentMap,
)
from app.routers.people import load_project, load_team, project_detail, team_detail
from app.schemas import (
    ProjectCreate,
    ProjectDetailOut,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    ProjectUpdate,
    TeamCreate,
    TeamDetailOut,
    TeamMemberCreate,
    TeamUpdate,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "display_name": u.display_name,
        "email": u.email,
        "department": u.department,
        "roles": [{"role": r.role, "scope": r.scope} for r in u.roles],
    }


# Ranges of the AI parser's agent settings (BR-M4, BR-M6, BR-M7)
SETTING_RANGES = {
    "parser_confidence_threshold": (0.0, 1.0),
    "parser_useful_vote_threshold": (1, 1000),
    "parser_raw_retention_days": (1, 3650),
}


def _checked_setting(setting: SystemSetting, value: str) -> str:
    """A typed setting must parse as its type (and stay in range for the agent settings); a bad value is a 422."""
    value = value.strip()
    kind = {"int": int, "float": float}.get(setting.value_type)
    if kind is not None:
        try:
            number = kind(value)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{setting.key} must be a {setting.value_type}")
        low, high = SETTING_RANGES.get(setting.key, (None, None))
        if low is not None and not low <= number <= high:
            raise HTTPException(status_code=422, detail=f"{setting.key} must be between {low} and {high}")
        return str(number)
    return value


@router.get("/settings")
def list_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> list[dict]:
    rows = db.query(SystemSetting).order_by(SystemSetting.key).all()
    return [
        {
            "key": s.key,
            "value": s.value,
            "value_type": s.value_type,
            "description": s.description,
        }
        for s in rows
    ]


@router.put("/settings/{key}")
def update_setting(
    key: str,
    value: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    value = _checked_setting(s, value)
    s.value = value
    db.commit()
    return {"status": "ok"}


@router.get("/verifier-mappings")
def list_mappings(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> list[dict]:
    rows = db.query(VerifierDepartmentMap).all()
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "user_display_name": m.user.display_name,
            "department": m.department,
        }
        for m in rows
    ]


@router.post("/verifier-mappings")
def add_mapping(
    user_id: int,
    department: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not any(r.role in {"expert", "team_lead", "manager"} for r in target.roles):
        # Add expert role automatically for mapping
        db.add(UserRole(user_id=user_id, role="expert"))
    db.add(VerifierDepartmentMap(user_id=user_id, department=department.strip()))
    db.commit()
    return {"status": "ok"}


# ---- Teams & projects ----


def _check_lead(db: Session, lead_user_id: int | None) -> None:
    if lead_user_id is not None and db.get(User, lead_user_id) is None:
        raise HTTPException(status_code=422, detail="Unknown lead user")


def _get_user(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=422, detail="Unknown user")
    return target


@router.post("/teams", status_code=201, response_model=TeamDetailOut)
def create_team(
    body: TeamCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> TeamDetailOut:
    name = body.name.strip()
    if db.query(Team).filter(Team.name == name).first():
        raise HTTPException(status_code=409, detail="A team with this name already exists")
    _check_lead(db, body.lead_user_id)
    team = Team(
        name=name,
        department=body.department.strip(),
        description=body.description,
        lead_user_id=body.lead_user_id,
    )
    db.add(team)
    db.commit()
    return team_detail(load_team(db, team.id))


@router.patch("/teams/{team_id}", response_model=TeamDetailOut)
def update_team(
    team_id: int,
    body: TeamUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> TeamDetailOut:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    data = body.model_dump(exclude_unset=True)
    if "lead_user_id" in data:
        _check_lead(db, data["lead_user_id"])
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
        dup = db.query(Team).filter(Team.name == data["name"], Team.id != team_id).first()
        if dup:
            raise HTTPException(status_code=409, detail="A team with this name already exists")
    for key, value in data.items():
        if key in {"name", "department"} and value is None:
            continue
        setattr(team, key, value)
    db.commit()
    return team_detail(load_team(db, team_id))


@router.post("/projects", status_code=201, response_model=ProjectDetailOut)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ProjectDetailOut:
    name = body.name.strip()
    if db.query(Project).filter(Project.name == name).first():
        raise HTTPException(status_code=409, detail="A project with this name already exists")
    _check_lead(db, body.lead_user_id)
    project = Project(
        name=name,
        description=body.description,
        status=body.status,
        lead_user_id=body.lead_user_id,
    )
    db.add(project)
    db.commit()
    return project_detail(load_project(db, project.id))


@router.patch("/projects/{project_id}", response_model=ProjectDetailOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ProjectDetailOut:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = body.model_dump(exclude_unset=True)
    if "lead_user_id" in data:
        _check_lead(db, data["lead_user_id"])
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
        dup = db.query(Project).filter(Project.name == data["name"], Project.id != project_id).first()
        if dup:
            raise HTTPException(status_code=409, detail="A project with this name already exists")
    for key, value in data.items():
        if key in {"name", "status"} and value is None:
            continue
        setattr(project, key, value)
    db.commit()
    return project_detail(load_project(db, project_id))


@router.post("/teams/{team_id}/members", status_code=201, response_model=TeamDetailOut)
def add_team_member(
    team_id: int,
    body: TeamMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> TeamDetailOut:
    if db.get(Team, team_id) is None:
        raise HTTPException(status_code=404, detail="Team not found")
    _get_user(db, body.user_id)
    existing = (
        db.query(TeamMembership).filter_by(team_id=team_id, user_id=body.user_id).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this team")
    if body.is_primary:
        for m in db.query(TeamMembership).filter_by(user_id=body.user_id, is_primary=True).all():
            m.is_primary = False
    db.add(
        TeamMembership(
            team_id=team_id, user_id=body.user_id, role=body.role.strip(), is_primary=body.is_primary
        )
    )
    db.commit()
    return team_detail(load_team(db, team_id))


@router.delete("/team-memberships/{membership_id}")
def remove_team_member(
    membership_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    m = db.get(TeamMembership, membership_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    db.delete(m)
    db.commit()
    return {"status": "ok"}


@router.post("/projects/{project_id}/members", status_code=201, response_model=ProjectDetailOut)
def add_project_member(
    project_id: int,
    body: ProjectMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ProjectDetailOut:
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _get_user(db, body.user_id)
    start = body.start_date or date.today()
    if body.end_date is not None and body.end_date < start:
        raise HTTPException(status_code=422, detail="End date cannot be before start date")
    existing = (
        db.query(ProjectMembership).filter_by(project_id=project_id, user_id=body.user_id).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this project")
    db.add(
        ProjectMembership(
            project_id=project_id,
            user_id=body.user_id,
            role=body.role.strip(),
            start_date=start,
            end_date=body.end_date,
        )
    )
    db.commit()
    return project_detail(load_project(db, project_id))


@router.patch("/project-memberships/{membership_id}", response_model=ProjectDetailOut)
def update_project_member(
    membership_id: int,
    body: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> ProjectDetailOut:
    m = db.get(ProjectMembership, membership_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("role") is not None:
        m.role = data["role"].strip()
    if "end_date" in data:
        if data["end_date"] is not None and data["end_date"] < m.start_date:
            raise HTTPException(status_code=422, detail="End date cannot be before start date")
        m.end_date = data["end_date"]
    db.commit()
    return project_detail(load_project(db, m.project_id))


@router.delete("/project-memberships/{membership_id}")
def remove_project_member(
    membership_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    m = db.get(ProjectMembership, membership_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    db.delete(m)
    db.commit()
    return {"status": "ok"}


@router.post("/users/{user_id}/revoke-tokens")
def revoke_user_tokens(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
) -> dict:
    """Force sign-out: the employee's refresh tokens stop working; access tokens expire on their own."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    count = revoke_all_for_user(db, user_id)
    db.commit()
    audit(db, "tokens_revoked", admin.id, f"revoked {count} refresh token(s) of user {user_id}")
    return {"status": "ok", "revoked": count}


@router.get("/audit-log")
def list_audit_log(
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)).all()
    return [
        {
            "id": r.id,
            "event": r.event,
            "user_id": r.user_id,
            "detail": r.detail,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
