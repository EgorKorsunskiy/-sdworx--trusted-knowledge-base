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
    country: str | None = None
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
    difference_note: str | None = None


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
    difference_note: str | None = Field(default=None, max_length=1000)


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


# ---- People / teams / projects ----


class UserBrief(BaseModel):
    id: int
    display_name: str
    title: str | None = None
    department: str | None = None
    is_active: bool = True


class ProfileTeamOut(BaseModel):
    membership_id: int
    id: int
    name: str
    department: str
    role: str
    is_primary: bool


class ProfileProjectOut(BaseModel):
    membership_id: int
    id: int
    name: str
    status: str
    role: str
    start_date: date
    end_date: date | None = None
    ended: bool


class ProfileEntryOut(BaseModel):
    public_id: str
    title: str
    status: str


class ProfileOut(BaseModel):
    id: int
    email: str
    display_name: str
    title: str | None = None
    department: str | None = None
    country: str | None = None
    is_active: bool
    reputation: int = 0
    roles: list[RoleOut] = []
    teams: list[ProfileTeamOut] = []
    projects: list[ProfileProjectOut] = []
    entries: list[ProfileEntryOut] = []


class TeamMemberOut(BaseModel):
    membership_id: int
    user: UserBrief
    role: str
    is_primary: bool


class TeamListItem(BaseModel):
    id: int
    name: str
    department: str
    lead: UserBrief | None = None
    member_count: int = 0


class TeamDetailOut(BaseModel):
    id: int
    name: str
    department: str
    description: str | None = None
    lead: UserBrief | None = None
    members: list[TeamMemberOut] = []


class ProjectMemberOut(BaseModel):
    membership_id: int
    user: UserBrief
    role: str
    start_date: date
    end_date: date | None = None
    ended: bool


class ProjectListItem(BaseModel):
    id: int
    name: str
    status: str
    lead: UserBrief | None = None
    member_count: int = 0


class ProjectDetailOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    status: str
    lead: UserBrief | None = None
    members: list[ProjectMemberOut] = []


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    department: str = Field(min_length=1, max_length=255)
    description: str | None = None
    lead_user_id: int | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    lead_user_id: int | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: Literal["active", "completed"] = "active"
    lead_user_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: Literal["active", "completed"] | None = None
    lead_user_id: int | None = None


class TeamMemberCreate(BaseModel):
    user_id: int
    role: str = Field(default="Member", min_length=1, max_length=64)
    is_primary: bool = False


class ProjectMemberCreate(BaseModel):
    user_id: int
    role: str = Field(default="Member", min_length=1, max_length=64)
    start_date: date | None = None
    end_date: date | None = None


class ProjectMemberUpdate(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=64)
    end_date: date | None = None


# --- Version history & diffs ---


class AuthorRef(BaseModel):
    id: int
    display_name: str
    title: str | None = None


class ApproverOut(BaseModel):
    user: AuthorRef
    role: str
    action: str
    created_at: datetime
    source: Literal["verification", "pull_request"]


class DiffSummary(BaseModel):
    added: int
    removed: int
    edited: int
    unchanged: int


class FieldDiff(BaseModel):
    old: str | None = None
    new: str | None = None
    changed: bool


class DiffFragment(BaseModel):
    type: Literal["equal", "added", "removed", "edited"]
    old_text: str | None = None
    new_text: str | None = None
    author: AuthorRef | None = None
    parts: list[dict] | None = None


class DiffHeader(BaseModel):
    public_id: str
    kind: Literal["created", "change", "proposal"]
    from_version: int | None = None
    to_version: int | None = None
    version_id: int | None = None
    author: AuthorRef
    created_at: datetime
    change_note: str | None = None
    status: str | None = None
    approvers: list[ApproverOut] = []
    pull_request_id: int | None = None


class EntryDiffOut(BaseModel):
    header: DiffHeader
    title: FieldDiff
    justification: FieldDiff
    body: list[DiffFragment]
    summary: DiffSummary
    has_changes: bool


class HistoryItemOut(BaseModel):
    version_id: int
    version_number: int
    title: str
    status: str
    change_note: str | None = None
    created_at: datetime
    author: AuthorRef
    is_current: bool
    verifier_role: str | None = None
    approvers: list[ApproverOut] = []
    summary: DiffSummary
