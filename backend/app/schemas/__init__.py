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
    tag_type: str = "keyword"


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str | None = None


class ClientProjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    company: CompanyBrief


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=8)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=8)


class ClientProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company_id: int


class ClientProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company_id: int | None = None


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


class UserBrief(BaseModel):
    id: int
    display_name: str
    title: str | None = None
    department: str | None = None
    is_active: bool = True


class ContactOut(BaseModel):
    """An author or contributor in the Contacts block (FR-K3, FR-K4)."""

    user: UserBrief
    role: Literal["author", "co_author", "contributor"]
    basis: Literal["responsible", "relayed"]
    source: str | None = None
    reputation: int = 0
    email: str | None = None


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
    company: CompanyBrief | None = None
    client_project: ClientProjectBrief | None = None
    tags: list[TagOut] = []
    current_version: EntryVersionOut | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False
    who_to_ask: list[PersonBrief] = []
    difference_note: str | None = None
    has_responsible_contact: bool = False
    # Where the entry came from, when it came from an AI-parser meme (no conversation details)
    origin: dict | None = None


class EntryVersionBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    title: str
    status: str
    created_at: datetime


class EntryDetailOut(EntryOut):
    versions: list[EntryVersionBriefOut] = []
    contacts: list[ContactOut] = []
    # No active responsible person left: the block then lists the verifiers in scope instead (FR-K5)
    no_responsible_contact: bool = False
    my_contact: ContactOut | None = None


class EntryCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    justification: str | None = None
    category_id: int
    country: str = Field(min_length=2)
    scope: Literal["country", "eu", "universal", "company", "client_project"] = "country"
    company_id: int | None = None
    client_project_id: int | None = None
    keywords: list[str] = []
    # Authorship basis (FR-K1): required; Relayed needs a source
    basis: Literal["responsible", "relayed"]
    basis_source: str | None = Field(default=None, max_length=500)
    # Publishing an AI-parser meme through this form (iteration 21)
    suggestion_id: int | None = None
    sensitive_confirmed: bool = False
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
    tags: list[TagOut] = []


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


# --- Contributors / blame ---


class ContributorUser(BaseModel):
    id: int
    display_name: str
    title: str | None = None
    department: str | None = None
    email: str
    reputation: int
    role_badge: str


class BlameFragmentOut(BaseModel):
    index: int
    text: str
    separator_before: str
    contributor_ids: list[int]
    introduced_in_version: int
    last_edited_in_version: int


class ContributorOut(BaseModel):
    user: ContributorUser
    fragment_indexes: list[int]
    fragment_count: int
    first_version: int
    last_version: int


class ContributorsOut(BaseModel):
    version_number: int
    current_version_number: int
    viewer_is_contributor: bool
    fragments: list[BlameFragmentOut]
    contributors: list[ContributorOut]


# --- Pull requests ---


class PullRequestCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    proposed_title: str | None = Field(default=None, max_length=512)
    proposed_body: str | None = Field(default=None, max_length=20000)
    proposed_justification: str | None = Field(default=None, max_length=5000)
    change_note: str = Field(min_length=1, max_length=500)
    # The PR author's basis for their change (FR-K11); they become a contact with it once it is merged
    basis: Literal["responsible", "relayed"]
    basis_source: str | None = Field(default=None, max_length=500)


class BasisIn(BaseModel):
    basis: Literal["responsible", "relayed"]
    source: str | None = Field(default=None, max_length=500)


class BasisBulkIn(BaseModel):
    """Change the basis of several own entries at once (FR-K10)."""

    public_ids: list[str] = Field(min_length=1, max_length=200)
    basis: Literal["responsible", "relayed"]
    source: str | None = Field(default=None, max_length=500)


class PRApproveIn(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class PRRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class PRApprovalOut(BaseModel):
    id: int
    step: str
    action: Literal["approve", "reject", "skip"]
    comment: str | None = None
    created_at: datetime
    approver: AuthorRef


class PullRequestBrief(BaseModel):
    id: int
    title: str | None = None
    status: str
    author: AuthorRef
    created_at: datetime
    resolved_at: datetime | None = None
    change_note: str | None = None
    base_version_number: int | None = None
    is_stale: bool = False
    # The PR author's basis for their change, shown to the approver (FR-K6, FR-K11)
    basis: str | None = None
    basis_source: str | None = None


class PREntryRef(BaseModel):
    public_id: str
    title: str
    department: str


class PREntryDetail(PREntryRef):
    author: AuthorRef
    current_version_number: int


class PullRequestOut(PullRequestBrief):
    entry: PREntryDetail
    description: str | None = None
    proposed_title: str | None = None
    proposed_body: str | None = None
    proposed_justification: str | None = None
    approvals: list[PRApprovalOut] = []
    rejection_reason: str | None = None
    merged_version_number: int | None = None
    next_step: Literal["author", "verifier"] | None = None
    waiting_on: list[AuthorRef] = []
    can_approve_as_author: bool = False
    can_approve_as_verifier: bool = False
    can_reject: bool = False


class PendingPROut(PullRequestBrief):
    step: Literal["author", "verifier"]
    entry: PREntryRef
