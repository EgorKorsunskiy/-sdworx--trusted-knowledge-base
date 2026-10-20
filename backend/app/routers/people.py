from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import Entry, Project, ProjectMembership, Team, TeamMembership, User
from app.schemas import (
    TagOut,
    ProfileEntryOut,
    ProfileOut,
    ProfileProjectOut,
    ProfileTeamOut,
    ProjectDetailOut,
    ProjectListItem,
    ProjectMemberOut,
    RoleOut,
    TeamDetailOut,
    TeamListItem,
    TeamMemberOut,
    UserBrief,
)

router = APIRouter(tags=["people"], dependencies=[Depends(get_current_user)])


def is_ended(end_date: date | None) -> bool:
    return end_date is not None and end_date < date.today()


def brief(u: User | None) -> UserBrief | None:
    if u is None:
        return None
    return UserBrief(
        id=u.id,
        display_name=u.display_name,
        title=u.title,
        department=u.department,
        is_active=u.is_active,
    )


def team_detail(team: Team) -> TeamDetailOut:
    members = sorted(team.memberships, key=lambda m: m.user.display_name.lower())
    return TeamDetailOut(
        id=team.id,
        name=team.name,
        department=team.department,
        description=team.description,
        lead=brief(team.lead),
        members=[
            TeamMemberOut(
                membership_id=m.id, user=brief(m.user), role=m.role, is_primary=m.is_primary
            )
            for m in members
        ],
    )


def project_detail(project: Project) -> ProjectDetailOut:
    members = sorted(project.memberships, key=lambda m: m.user.display_name.lower())
    return ProjectDetailOut(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        lead=brief(project.lead),
        members=[
            ProjectMemberOut(
                membership_id=m.id,
                user=brief(m.user),
                role=m.role,
                start_date=m.start_date,
                end_date=m.end_date,
                ended=is_ended(m.end_date),
            )
            for m in members
        ],
    )


def load_team(db: Session, team_id: int) -> Team | None:
    return (
        db.query(Team)
        .options(joinedload(Team.lead), joinedload(Team.memberships).joinedload(TeamMembership.user))
        .filter(Team.id == team_id)
        .first()
    )


def load_project(db: Session, project_id: int) -> Project | None:
    return (
        db.query(Project)
        .options(
            joinedload(Project.lead),
            joinedload(Project.memberships).joinedload(ProjectMembership.user),
        )
        .filter(Project.id == project_id)
        .first()
    )


@router.get("/people", response_model=list[UserBrief])
def list_people(q: str | None = None, db: Session = Depends(get_db)) -> list[UserBrief]:
    query = db.query(User)
    if q and q.strip():
        query = query.filter(User.display_name.ilike(f"%{q.strip()}%"))
    return [brief(u) for u in query.order_by(User.display_name).all()]


@router.get("/people/{user_id}", response_model=ProfileOut)
def get_profile(user_id: int, db: Session = Depends(get_db)) -> ProfileOut:
    u = (
        db.query(User)
        .options(
            joinedload(User.roles),
            joinedload(User.memberships).joinedload(TeamMembership.team),
            joinedload(User.project_memberships).joinedload(ProjectMembership.project),
        )
        .filter(User.id == user_id)
        .first()
    )
    if u is None:
        raise HTTPException(status_code=404, detail="Person not found")

    teams = sorted(u.memberships, key=lambda m: (not m.is_primary, m.team.name.lower()))
    projects = sorted(
        u.project_memberships,
        key=lambda m: (is_ended(m.end_date), -m.start_date.toordinal()),
    )
    entries = (
        db.query(Entry)
        .options(joinedload(Entry.versions), joinedload(Entry.tags))
        .filter(Entry.author_id == user_id, Entry.is_published.is_(True))
        .order_by(Entry.updated_at.desc())
        .all()
    )
    return ProfileOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        title=u.title,
        department=u.department,
        country=u.country,
        is_active=u.is_active,
        reputation=u.reputation,
        roles=[RoleOut(role=r.role, scope=r.scope) for r in u.roles],
        teams=[
            ProfileTeamOut(
                membership_id=m.id,
                id=m.team.id,
                name=m.team.name,
                department=m.team.department,
                role=m.role,
                is_primary=m.is_primary,
            )
            for m in teams
        ],
        projects=[
            ProfileProjectOut(
                membership_id=m.id,
                id=m.project.id,
                name=m.project.name,
                status=m.project.status,
                role=m.role,
                start_date=m.start_date,
                end_date=m.end_date,
                ended=is_ended(m.end_date),
            )
            for m in projects
        ],
        entries=[
            ProfileEntryOut(
                public_id=e.public_id,
                title=e.versions[-1].title,
                status=e.versions[-1].status,
                tags=[TagOut.model_validate(t) for t in e.tags],
            )
            for e in entries
            if e.versions
        ],
    )


@router.get("/teams", response_model=list[TeamListItem])
def list_teams(db: Session = Depends(get_db)) -> list[TeamListItem]:
    teams = (
        db.query(Team)
        .options(joinedload(Team.lead), joinedload(Team.memberships))
        .order_by(Team.name)
        .all()
    )
    return [
        TeamListItem(
            id=t.id,
            name=t.name,
            department=t.department,
            lead=brief(t.lead),
            member_count=len(t.memberships),
        )
        for t in teams
    ]


@router.get("/teams/{team_id}", response_model=TeamDetailOut)
def get_team(team_id: int, db: Session = Depends(get_db)) -> TeamDetailOut:
    team = load_team(db, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team_detail(team)


@router.get("/projects", response_model=list[ProjectListItem])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectListItem]:
    projects = (
        db.query(Project)
        .options(joinedload(Project.lead), joinedload(Project.memberships))
        .order_by(Project.name)
        .all()
    )
    return [
        ProjectListItem(
            id=p.id,
            name=p.name,
            status=p.status,
            lead=brief(p.lead),
            member_count=len(p.memberships),
        )
        for p in projects
    ]


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectDetailOut:
    project = load_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_detail(project)
