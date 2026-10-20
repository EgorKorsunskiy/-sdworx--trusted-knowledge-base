from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps.auth import get_current_user, require_roles
from app.models import ClientProject, Company, Entry, User
from app.schemas import ClientProjectCreate, ClientProjectUpdate, CompanyCreate, CompanyUpdate

router = APIRouter(tags=["companies"])


def _company_out(c: Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "country": c.country,
        "client_projects": [{"id": p.id, "name": p.name, "company_id": c.id} for p in c.client_projects],
    }


def _project_out(p: ClientProject) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "company": {"id": p.company.id, "name": p.company.name, "country": p.company.country},
    }


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status_code=422, detail="A name is required")
    return name


def _check_project_name(db: Session, name: str, company_name: str, own_id: int | None = None) -> None:
    """Client-project names never name the client (BR-11) and are unique."""
    if company_name.lower() in name.lower():
        raise HTTPException(
            status_code=422,
            detail="A client-project name must not contain the client's name; use a neutral name",
        )
    clash = db.query(ClientProject).filter(ClientProject.name.ilike(name)).first()
    if clash is not None and clash.id != own_id:
        raise HTTPException(status_code=409, detail="A client project with this name already exists")


# ---- Readable by every employee (pickers, scope badges, filters) ----


@router.get("/companies")
def list_companies(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[dict]:
    rows = db.query(Company).options(joinedload(Company.client_projects)).order_by(Company.name).all()
    return [_company_out(c) for c in rows]


@router.get("/client-projects")
def list_client_projects(
    company_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    q = db.query(ClientProject).options(joinedload(ClientProject.company)).order_by(ClientProject.name)
    if company_id is not None:
        q = q.filter(ClientProject.company_id == company_id)
    return [_project_out(p) for p in q.all()]


# ---- Admin maintenance ----


@router.post("/admin/companies", status_code=201)
def create_company(
    body: CompanyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    name = _clean_name(body.name)
    if db.query(Company).filter(Company.name.ilike(name)).first():
        raise HTTPException(status_code=409, detail="A company with this name already exists")
    company = Company(name=name, country=body.country.upper() if body.country else None)
    db.add(company)
    db.commit()
    return _company_out(company)


@router.patch("/admin/companies/{company_id}")
def update_company(
    company_id: int,
    body: CompanyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if body.name is not None:
        name = _clean_name(body.name)
        clash = db.query(Company).filter(Company.name.ilike(name), Company.id != company.id).first()
        if clash:
            raise HTTPException(status_code=409, detail="A company with this name already exists")
        for p in company.client_projects:
            _check_project_name(db, p.name, name, own_id=p.id)
        company.name = name
    if body.country is not None:
        company.country = body.country.upper()
    db.commit()
    return _company_out(company)


@router.delete("/admin/companies/{company_id}", status_code=204)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> None:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if db.query(Entry).filter(Entry.company_id == company_id).first():
        raise HTTPException(status_code=409, detail="Entries are scoped to this company; it cannot be deleted")
    db.delete(company)
    db.commit()


@router.post("/admin/client-projects", status_code=201)
def create_client_project(
    body: ClientProjectCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    company = db.get(Company, body.company_id)
    if company is None:
        raise HTTPException(status_code=422, detail="Company not found")
    name = _clean_name(body.name)
    _check_project_name(db, name, company.name)
    project = ClientProject(name=name, company_id=company.id)
    db.add(project)
    db.commit()
    return _project_out(project)


@router.patch("/admin/client-projects/{project_id}")
def update_client_project(
    project_id: int,
    body: ClientProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    project = db.get(ClientProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Client project not found")
    company = project.company
    if body.company_id is not None and body.company_id != project.company_id:
        company = db.get(Company, body.company_id)
        if company is None:
            raise HTTPException(status_code=422, detail="Company not found")
    name = _clean_name(body.name) if body.name is not None else project.name
    _check_project_name(db, name, company.name, own_id=project.id)
    project.name = name
    project.company_id = company.id
    # Entries scoped to this client project follow it to its new company
    db.query(Entry).filter(Entry.client_project_id == project.id).update({Entry.company_id: company.id})
    db.commit()
    return _project_out(project)


@router.delete("/admin/client-projects/{project_id}", status_code=204)
def delete_client_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> None:
    project = db.get(ClientProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Client project not found")
    if db.query(Entry).filter(Entry.client_project_id == project_id).first():
        raise HTTPException(status_code=409, detail="Entries are scoped to this client project; it cannot be deleted")
    db.delete(project)
    db.commit()
