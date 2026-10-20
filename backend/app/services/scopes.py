"""Company and client-project scopes (FR-E7, BR-11)."""

import re

from sqlalchemy.orm import Session

from app.models import ClientProject, Company, EntryScope

COMPANY_SCOPES = (EntryScope.COMPANY.value, EntryScope.CLIENT_PROJECT.value)


class ScopeError(ValueError):
    """A scope that cannot be saved; the message is shown to the user."""


def resolve_scope(
    db: Session,
    scope: str,
    company_id: int | None,
    client_project_id: int | None,
) -> tuple[int | None, int | None, str | None]:
    """Validate the scope pointers; returns (company_id, client_project_id, company country).

    A company scope needs a company, a client-project scope needs a client project (its company follows from it),
    and every other scope must not point at either (BR-11).
    """
    if scope == EntryScope.COMPANY.value:
        if company_id is None:
            raise ScopeError("Choose the company this entry is specific to")
        company = db.get(Company, company_id)
        if company is None:
            raise ScopeError("Company not found")
        return company.id, None, company.country
    if scope == EntryScope.CLIENT_PROJECT.value:
        if client_project_id is None:
            raise ScopeError("Choose the client project this entry is specific to")
        project = db.get(ClientProject, client_project_id)
        if project is None:
            raise ScopeError("Client project not found")
        return project.company_id, project.id, project.company.country
    return None, None, None


def named_client(db: Session, *texts: str | None) -> str | None:
    """The first client company named in these texts, if any. Content refers to the client project instead (BR-11)."""
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return None
    for (name,) in db.query(Company.name):
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", haystack, re.IGNORECASE):
            return name
    return None


def scope_label(scope: str, company: Company | None, project: ClientProject | None) -> str:
    """Human label as shown in the scope badge; the client name appears only here."""
    if project is not None:
        return f"Client project {project.name} ({project.company.name})"
    if company is not None:
        return f"Company {company.name}"
    return {
        "country": "Country-specific",
        "country-specific": "Country-specific",
        "eu": "EU-wide",
        "EU-wide": "EU-wide",
        "universal": "Universal",
    }.get(scope, scope)
