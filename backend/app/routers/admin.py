from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user, require_roles
from app.models import SystemSetting, User, UserRole, VerifierDepartmentMap
from app.schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "display_name": u.display_name,
        "email": u.email,
        "department": u.department,
        "roles": [{"role": r.role, "scope": r.scope} for r in u.roles],
    }


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
