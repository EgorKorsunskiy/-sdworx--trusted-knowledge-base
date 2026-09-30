from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    scope: str | None = None


class TeamBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    department: str | None = None
    title: str | None = None
    reputation: int = 0
    is_active: bool
    roles: list[RoleOut] = []
    teams: list[TeamBrief] = []


class DevLoginRequest(BaseModel):
    user_id: int


class SessionOut(BaseModel):
    authenticated: bool
    user: UserOut | None = None
    token: str | None = None


class HealthOut(BaseModel):
    status: str
    app: str
    time: datetime


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_default: bool


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PersonBrief(BaseModel):
    id: int
    display_name: str
    title: str | None = None
    department: str | None = None
    role: str | None = None


class EntryVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    title: str
    body: str
    justification: str | None = None
    status: str
    change_note: str | None = None
    edited_by: UserOut
    created_at: datetime


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    scope: str
    department: str
    country: str | None = None
    category: CategoryOut | None = None
    author: UserOut
    team: TeamBrief | None = None
    tags: list[TagOut] = []
    current_version: EntryVersionOut | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False
    who_to_ask: list[PersonBrief] = []


class EntryVersionBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    title: str
    status: str
    created_at: datetime


class EntryDetailOut(EntryOut):
    versions: list[EntryVersionBriefOut] = []


class EntryCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    justification: str | None = None
    category_id: int
    country: str = Field(min_length=2)
    scope: Literal["country", "eu", "universal"] = "country"
    keywords: list[str] = []


class EntryUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    justification: str | None = None
    keywords: list[str] | None = None


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    verifier: UserOut
    role: str
    action: str
    comment: str | None = None
    created_at: datetime


class UsageVoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserOut
    used_at: date
    where_ref: str
    is_correct: bool
    created_at: datetime


class UsageVoteCreate(BaseModel):
    used_at: date
    where_ref: str
    is_correct: bool


class OutdatedFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserOut
    reason: str
    created_at: datetime
    resolved_at: datetime | None = None
