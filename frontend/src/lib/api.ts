export const API_BASE = import.meta.env.VITE_API_URL || "/api"

// The access token lives in memory only (never localStorage). The refresh token is an HttpOnly
// cookie the browser sends to /auth/refresh; JavaScript never sees it.
let accessToken: string | null = null

export function getToken(): string | null {
  return accessToken
}

export function setToken(token: string | null) {
  accessToken = token
}

export const SIGNED_OUT_EVENT = "peerpoint:signed-out"

export type Session = { authenticated: boolean; user: User | null; token?: string | null }

let refreshInFlight: Promise<Session | null> | null = null

/** Trade the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<Session | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" })
        if (!res.ok) {
          accessToken = null
          return null
        }
        const session: Session = await res.json()
        accessToken = session.token ?? null
        return session
      } catch {
        return null
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

async function fetchJson<T = any>(path: string, options: RequestInit = {}, retried = false): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json")
  }
  const token = getToken()
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  })
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
    // Access token expired: renew silently and retry once, otherwise send the user to sign in.
    if (await refreshSession()) return fetchJson<T>(path, options, true)
    window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      detail = await res.text().catch(() => "Request failed")
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export type User = {
  id: number
  email: string
  display_name: string
  department?: string | null
  title?: string | null
  country?: string | null
  reputation: number
  is_active: boolean
  roles: { role: string; scope?: string | null }[]
  teams: { id: number; name: string; department: string }[]
}

// Shared entity: "keyword" tags are set by people, "automatic" ones (country:be, author:..., ...) by the system.
export type Tag = { id: number; name: string; tag_type: "keyword" | "automatic" | string }
export type TagSuggestion = Tag & { entry_count: number }

export const normalizeTag = (name: string) => name.trim().replace(/\s+/g, " ").toLowerCase()

export type CompanyBrief = { id: number; name: string; country?: string | null }
export type ClientProjectBrief = { id: number; name: string; company: CompanyBrief }
export type Company = CompanyBrief & { client_projects: { id: number; name: string; company_id: number }[] }

export type Category = {
  id: number
  name: string
  description?: string | null
  is_default: boolean
}

export type EntryVersion = {
  id: number
  version_number: number
  title: string
  body: string
  justification?: string | null
  status: string
  change_note?: string | null
  edited_by: User
  created_at: string
}

export type PersonBrief = {
  id: number
  display_name: string
  title?: string | null
  department?: string | null
  role?: string | null
}

export type Contact = {
  user: UserBrief
  role: "author" | "co_author" | "contributor"
  basis: "responsible" | "relayed"
  source?: string | null
  reputation: number
  email?: string | null
}

export type BasisChange = {
  id: number
  created_at: string
  user: { id: number; display_name: string }
  old_basis: string | null
  old_source: string | null
  new_basis: string
  new_source: string | null
}

export type ResponsibilityItem = {
  public_id: string
  title: string
  status: string
  role: "author" | "co_author" | "contributor"
  basis: "responsible" | "relayed"
  source?: string | null
  scope: string
  category?: string | null
  updated_at: string
}

export type Responsibilities = {
  areas: {
    categories: string[]
    countries: string[]
    scopes: string[]
    companies: string[]
    client_projects: string[]
    tags: { id: number; name: string }[]
  }
  responsible: ResponsibilityItem[]
  relayed: ResponsibilityItem[]
}

export type Entry = {
  id: number
  public_id: string
  scope: string
  department: string
  country?: string | null
  category?: { id: number; name: string; is_default?: boolean } | null
  author: User
  team?: { id: number; name: string; department: string } | null
  company?: CompanyBrief | null
  client_project?: ClientProjectBrief | null
  tags: Tag[]
  current_version: EntryVersion
  created_at: string
  updated_at: string
  can_edit?: boolean
  who_to_ask?: PersonBrief[]
  difference_note?: string | null
  has_responsible_contact?: boolean
  contacts?: Contact[]
  no_responsible_contact?: boolean
  my_contact?: Contact | null
  origin?: {
    kind: "meeting" | "chat"
    date_from: string
    date_to: string | null
    is_participant: boolean
    meme_id: number | null
    is_author?: boolean
    can_request_coauthorship?: boolean
    request_blocked_reason?: string | null
    my_request_status?: string | null
    pending_requests?: number
  } | null
}

export type UserBrief = {
  id: number
  display_name: string
  title?: string | null
  department?: string | null
  is_active: boolean
}

export type Profile = {
  id: number
  email: string
  display_name: string
  title?: string | null
  department?: string | null
  country?: string | null
  is_active: boolean
  reputation: number
  roles: { role: string; scope?: string | null }[]
  teams: { membership_id: number; id: number; name: string; department: string; role: string; is_primary: boolean }[]
  projects: {
    membership_id: number
    id: number
    name: string
    status: string
    role: string
    start_date: string
    end_date?: string | null
    ended: boolean
  }[]
  entries: { public_id: string; title: string; status: string; tags: Tag[] }[]
}

export type TeamDetail = {
  id: number
  name: string
  department: string
  description?: string | null
  lead?: UserBrief | null
  members: { membership_id: number; user: UserBrief; role: string; is_primary: boolean }[]
}

export type ProjectDetail = {
  id: number
  name: string
  description?: string | null
  status: string
  lead?: UserBrief | null
  members: {
    membership_id: number
    user: UserBrief
    role: string
    start_date: string
    end_date?: string | null
    ended: boolean
  }[]
}

export type AuthorRef = { id: number; display_name: string; title?: string | null }

export type DiffApprover = {
  user: AuthorRef
  role: string
  action: string
  created_at: string
  source: "verification" | "pull_request"
}

export type DiffFragment = {
  type: "equal" | "added" | "removed" | "edited"
  old_text: string | null
  new_text: string | null
  author: AuthorRef | null
  parts?: { op: "equal" | "delete" | "insert"; text: string }[] | null
}

export type FieldDiff = { old: string | null; new: string | null; changed: boolean }

export type DiffSummary = { added: number; removed: number; edited: number; unchanged: number }

export type EntryDiff = {
  header: {
    public_id: string
    kind: "created" | "change" | "proposal"
    from_version: number | null
    to_version: number | null
    version_id: number | null
    author: AuthorRef
    created_at: string
    change_note: string | null
    status: string | null
    approvers: DiffApprover[]
    pull_request_id: number | null
  }
  title: FieldDiff
  justification: FieldDiff
  body: DiffFragment[]
  summary: DiffSummary
  has_changes: boolean
}

export type HistoryItem = {
  version_id: number
  version_number: number
  title: string
  status: string
  change_note: string | null
  created_at: string
  author: AuthorRef
  is_current: boolean
  verifier_role: string | null
  approvers: DiffApprover[]
  summary: DiffSummary
}

export type ContributorUser = {
  id: number
  display_name: string
  title: string | null
  department: string | null
  email: string
  reputation: number
  role_badge: string
}

export type BlameFragment = {
  index: number
  text: string
  separator_before: string
  contributor_ids: number[]
  introduced_in_version: number
  last_edited_in_version: number
}

export type ContributorEntry = {
  user: ContributorUser
  fragment_indexes: number[]
  fragment_count: number
  first_version: number
  last_version: number
}

export type ContributorsResponse = {
  version_number: number
  current_version_number: number
  viewer_is_contributor: boolean
  fragments: BlameFragment[]
  contributors: ContributorEntry[]
}

export type PRStatus = "open" | "author_approved" | "verifier_approved" | "merged" | "rejected"

export type PRApproval = {
  id: number
  step: "author" | "verifier"
  action: "approve" | "reject" | "skip"
  comment: string | null
  created_at: string
  approver: AuthorRef
}

export type PullRequestBrief = {
  basis?: string | null
  basis_source?: string | null
  id: number
  title: string | null
  status: PRStatus
  author: AuthorRef
  created_at: string
  resolved_at: string | null
  change_note: string | null
  base_version_number: number | null
  is_stale: boolean
}

export type PullRequest = PullRequestBrief & {
  entry: {
    public_id: string
    title: string
    department: string
    author: AuthorRef
    current_version_number: number
  }
  description: string | null
  proposed_title: string | null
  proposed_body: string | null
  proposed_justification: string | null
  approvals: PRApproval[]
  rejection_reason: string | null
  merged_version_number: number | null
  next_step: "author" | "verifier" | null
  waiting_on: AuthorRef[]
  can_approve_as_author: boolean
  can_approve_as_verifier: boolean
  can_reject: boolean
}

export type PendingPullRequest = PullRequestBrief & {
  step: "author" | "verifier"
  entry: { public_id: string; title: string; department: string }
}

export type PullRequestCreate = {
  title?: string
  description?: string
  proposed_title?: string
  proposed_body?: string
  proposed_justification?: string
  change_note: string
  basis: "responsible" | "relayed"
  basis_source?: string
}

// ---- AI parser: Information overview ----

export type MemePerson = { id: number; display_name: string; title?: string | null; department?: string | null }
export type SuggestionEventOut = {
  id: number
  action: "created" | "approve" | "reject" | "postpone" | "reopen" | "withdraw" | "closed" | "joined"
  basis: string | null
  source: string | null
  reason: string | null
  created_at: string
}
export type SuggestionState = "pending" | "postponed" | "accepted" | "declined" | "closed"
export type MemeSuggestion = {
  id: number
  owner: MemePerson
  is_mine: boolean
  role: "speaker" | "confirmer"
  state: SuggestionState
  label: string
  basis: "responsible" | "relayed" | null
  source: string | null
  reason: string | null
  decided_at: string | null
  basis_hint: { basis: "responsible" | "relayed"; source?: string } | null
  history: SuggestionEventOut[]
}
export type CoauthorRequestOut = {
  id: number
  requester: MemePerson
  basis: "responsible" | "relayed"
  source: string | null
  note: string | null
  evidence: string | null
  evidence_quote: { text: string; at: string } | null
  status: "pending" | "accepted" | "declined"
  decided_by: MemePerson | null
  decision_reason: string | null
  decided_at: string | null
  created_at: string
  is_mine: boolean
}
export type MemeStatus = "new" | "preparing" | "published" | "declined"
export type Meme = {
  id: number
  title: string
  statement: string
  kind: string
  status: MemeStatus
  sensitive: boolean
  category: string | null
  country: string | null
  scope: string
  scope_label: string
  company: { id: number; name: string } | null
  client_project: { id: number; name: string; company: string } | null
  tags: Tag[]
  similar_entries: { public_id: string; title: string; status: string; score: number }[]
  source: { id: number; kind: "meeting" | "chat"; title: string; date_from: string; date_to: string | null }
  speaker: MemePerson
  confirmers: MemePerson[]
  quotes: {
    id: number
    user: MemePerson
    text: string
    at: string
    is_confirmation: boolean
    context: { at: string; speaker: string; text: string; quote: boolean }[]
  }[]
  suggestions: MemeSuggestion[]
  my_suggestion_id: number | null
  votes: { useful: number; not_useful: number; my_vote: boolean | null; blocked_reason: string | null }
  entry: { public_id: string; status: string } | null
  authors: { user: MemePerson; basis: "responsible" | "relayed"; source: string | null; is_me: boolean }[]
  is_author: boolean
  is_candidate: boolean
  can_request_coauthorship: boolean
  request_blocked_reason: string | null
  my_request: CoauthorRequestOut | null
}
export type OverviewItem =
  | { type: "suggestion"; id: number; meme: Meme }
  | { type: "meme"; id: number; meme: Meme }
  | { type: "coauthor_request"; id: number; meme: Meme; request: CoauthorRequestOut }
export type OverviewSection = "to_decide" | "postponed" | "decided" | "coauthor"
export type OverviewCounts = Record<OverviewSection, number>
export type OverviewPage = {
  tab: "yours" | "others"
  section: OverviewSection | null
  counts: OverviewCounts
  items: OverviewItem[]
  total: number
  page: number
  page_size: number
}
export type SuggestionPrefill = {
  suggestion_id: number
  meme_id: number
  already_published: boolean
  entry_public_id: string | null
  title: string
  body: string
  justification: string
  category_id: number | null
  country: string | null
  scope: string
  company_id: number | null
  client_project_id: number | null
  keywords: string[]
  basis: "responsible" | "relayed" | null
  basis_source: string | null
  sensitive: boolean
  source: { kind: string; title: string; date_from: string; date_to: string | null }
  candidates: {
    owner: { id: number; display_name: string }
    role: string
    state: SuggestionState
    label: string
    reason: string | null
    is_me: boolean
  }[]
  co_authors: { id: number; display_name: string; basis: string; source: string | null }[]
}

const jsonBody = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })

export type AuthConfig = {
  demo_mode: boolean
  idp: { client_id: string; authorize_url: string; scope: string }
}

export type SearchFacets = {
  countries: string[]
  departments: string[]
  categories: string[]
  statuses: { value: string; label: string }[]
  scopes: { value: string; label: string }[]
  verifier_roles: string[]
  authors: { id: number; name: string }[]
  teams: { id: number; name: string }[]
  companies: { id: number; name: string }[]
  client_projects: { id: number; name: string; company: string }[]
}

// Query-string keys that can hold several values (OR within one filter).
export const SEARCH_MULTI_KEYS = [
  "country",
  "department",
  "category",
  "status",
  "scope",
  "verifier_role",
  "author",
  "team",
  "company",
  "client_project",
  "tag",
] as const
export const SEARCH_DATE_KEYS = ["updated_from", "updated_to"] as const

export const api = {
  authConfig: () => fetchJson<AuthConfig>("/auth/config"),
  // Demo mode only (404 otherwise).
  listUsers: () => fetchJson<User[]>("/auth/users"),
  login: async (userId: number) => {
    const data = await fetchJson<Session>("/auth/dev-login", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    })
    setToken(data.token ?? null)
    return data
  },
  // Last step of the OAuth2 authorization code flow.
  exchangeCode: async (body: { code: string; code_verifier: string; redirect_uri: string }) => {
    const data = await fetchJson<Session>("/auth/token", { method: "POST", body: JSON.stringify(body) })
    setToken(data.token ?? null)
    return data
  },
  logout: async () => {
    try {
      await fetchJson("/auth/logout", { method: "POST" })
    } finally {
      setToken(null)
    }
  },
  categories: () => fetchJson<Category[]>("/categories"),
  notifications: {
    list: () => fetchJson<any[]>("/notifications"),
    unreadCount: () => fetchJson<{ count: number }>("/notifications/unread-count"),
    markRead: (id: number) => fetchJson(`/notifications/${id}/read`, { method: "POST" }),
  },
  contributions: () => fetchJson<any>("/me/contributions"),
  companies: () => fetchJson<Company[]>("/companies"),
  information: {
    summary: () => fetchJson<OverviewCounts & { badge: number }>("/information/summary"),
    list: (params: URLSearchParams) => fetchJson<OverviewPage>(`/information?${params.toString()}`),
    locate: (params: Record<string, string>) =>
      fetchJson<{ tab: "yours" | "others"; section: OverviewSection | null; page: number }>(
        `/information/locate?${new URLSearchParams(params).toString()}`,
      ),
    meme: (id: number) => fetchJson<Meme>(`/information/memes/${id}`),
    approve: (id: number, body: { basis: "responsible" | "relayed"; source?: string }) =>
      fetchJson<{ id: number; meme: Meme }>(`/information/suggestions/${id}/approve`, jsonBody("POST", body)),
    reject: (id: number, reason?: string) =>
      fetchJson<{ id: number; meme: Meme }>(`/information/suggestions/${id}/reject`, jsonBody("POST", { reason })),
    postpone: (id: number) => fetchJson(`/information/suggestions/${id}/postpone`, { method: "POST" }),
    reopen: (id: number) => fetchJson(`/information/suggestions/${id}/reopen`, { method: "POST" }),
    withdraw: (id: number) => fetchJson(`/information/suggestions/${id}/withdraw`, { method: "POST" }),
    prefill: (id: number) => fetchJson<SuggestionPrefill>(`/information/suggestions/${id}/prefill`),
    vote: (memeId: number, useful: boolean) =>
      fetchJson<Meme>(`/information/memes/${memeId}/vote`, jsonBody("PUT", { useful })),
    withdrawVote: (memeId: number) => fetchJson<Meme>(`/information/memes/${memeId}/vote`, { method: "DELETE" }),
    requestCoauthorship: (
      memeId: number,
      body: { basis: "responsible" | "relayed"; source?: string; note?: string; evidence?: string },
    ) => fetchJson<Meme>(`/information/memes/${memeId}/coauthor-requests`, jsonBody("POST", body)),
    acceptRequest: (id: number, reason?: string) =>
      fetchJson(`/information/coauthor-requests/${id}/accept`, jsonBody("POST", { reason })),
    declineRequest: (id: number, reason?: string) =>
      fetchJson(`/information/coauthor-requests/${id}/decline`, jsonBody("POST", { reason })),
  },
  tags: {
    // Existing tags matching `q` (most used first); used for suggestions while typing.
    list: (q = "", opts: { type?: "keyword" | "automatic"; limit?: number } = {}) => {
      const params = new URLSearchParams()
      if (q) params.set("q", q)
      if (opts.type) params.set("type", opts.type)
      if (opts.limit) params.set("limit", String(opts.limit))
      const qs = params.toString()
      return fetchJson<TagSuggestion[]>(`/tags${qs ? `?${qs}` : ""}`)
    },
  },
  admin: {
    renameTag: (id: number, name: string) => fetchJson<TagSuggestion>(`/admin/tags/${id}`, jsonBody("PATCH", { name })),
    mergeTag: (id: number, intoId: number) =>
      fetchJson<TagSuggestion>(`/admin/tags/${id}/merge`, jsonBody("POST", { into_id: intoId })),
    createCompany: (body: { name: string; country?: string }) =>
      fetchJson<Company>("/admin/companies", jsonBody("POST", body)),
    updateCompany: (id: number, body: { name?: string; country?: string }) =>
      fetchJson<Company>(`/admin/companies/${id}`, jsonBody("PATCH", body)),
    deleteCompany: (id: number) => fetchJson(`/admin/companies/${id}`, { method: "DELETE" }),
    createClientProject: (body: { name: string; company_id: number }) =>
      fetchJson(`/admin/client-projects`, jsonBody("POST", body)),
    updateClientProject: (id: number, body: { name?: string; company_id?: number }) =>
      fetchJson(`/admin/client-projects/${id}`, jsonBody("PATCH", body)),
    deleteClientProject: (id: number) => fetchJson(`/admin/client-projects/${id}`, { method: "DELETE" }),
    settings: () => fetchJson<any[]>("/admin/settings"),
    updateSetting: (key: string, value: string) => fetchJson(`/admin/settings/${key}?value=${encodeURIComponent(value)}`, { method: "PUT" }),
    mappings: () => fetchJson<any[]>("/admin/verifier-mappings"),
    addMapping: (userId: number, department: string) =>
      fetchJson(`/admin/verifier-mappings?user_id=${userId}&department=${encodeURIComponent(department)}`, { method: "POST" }),
    createTeam: (body: { name: string; department: string; description?: string; lead_user_id?: number | null }) =>
      fetchJson<TeamDetail>("/admin/teams", jsonBody("POST", body)),
    updateTeam: (id: number, body: Record<string, unknown>) =>
      fetchJson<TeamDetail>(`/admin/teams/${id}`, jsonBody("PATCH", body)),
    createProject: (body: { name: string; description?: string; status?: string; lead_user_id?: number | null }) =>
      fetchJson<ProjectDetail>("/admin/projects", jsonBody("POST", body)),
    updateProject: (id: number, body: Record<string, unknown>) =>
      fetchJson<ProjectDetail>(`/admin/projects/${id}`, jsonBody("PATCH", body)),
    addTeamMember: (teamId: number, body: { user_id: number; role?: string; is_primary?: boolean }) =>
      fetchJson<TeamDetail>(`/admin/teams/${teamId}/members`, jsonBody("POST", body)),
    removeTeamMember: (membershipId: number) =>
      fetchJson(`/admin/team-memberships/${membershipId}`, { method: "DELETE" }),
    addProjectMember: (
      projectId: number,
      body: { user_id: number; role?: string; start_date?: string; end_date?: string | null },
    ) => fetchJson<ProjectDetail>(`/admin/projects/${projectId}/members`, jsonBody("POST", body)),
    updateProjectMember: (membershipId: number, body: { role?: string; end_date?: string | null }) =>
      fetchJson<ProjectDetail>(`/admin/project-memberships/${membershipId}`, jsonBody("PATCH", body)),
    removeProjectMember: (membershipId: number) =>
      fetchJson(`/admin/project-memberships/${membershipId}`, { method: "DELETE" }),
  },
  people: {
    list: (q = "") => fetchJson<UserBrief[]>(`/people${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    get: (id: number | string) => fetchJson<Profile>(`/people/${id}`),
    responsibilities: (id: number | string) => fetchJson<Responsibilities>(`/people/${id}/responsibilities`),
    changeMyBasis: (body: { public_ids: string[]; basis: "responsible" | "relayed"; source?: string }) =>
      fetchJson<{ changed: number }>("/me/responsibilities", jsonBody("PATCH", body)),
  },
  teams: {
    list: () => fetchJson<any[]>("/teams"),
    get: (id: number | string) => fetchJson<TeamDetail>(`/teams/${id}`),
  },
  projects: {
    list: () => fetchJson<any[]>("/projects"),
    get: (id: number | string) => fetchJson<ProjectDetail>(`/projects/${id}`),
  },
  // `params` is a URLSearchParams with `q` and the repeated filter keys (see SEARCH_MULTI_KEYS).
  search: (params: URLSearchParams = new URLSearchParams()) => {
    const qs = params.toString()
    return fetchJson<Entry[]>(`/search${qs ? `?${qs}` : ""}`)
  },
  searchFacets: () => fetchJson<SearchFacets>("/search/facets"),
  similar: (title: string, body: string) =>
    fetchJson(`/entries/similar?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`),
  outdated: {
    mark: (publicId: string, reason: string) =>
      fetchJson(`/entries/${publicId}/outdated?reason=${encodeURIComponent(reason)}`, { method: "POST" }),
    confirm: (publicId: string) => fetchJson(`/entries/${publicId}/confirm-still-valid`, { method: "POST" }),
  },
  votes: {
    list: (publicId: string) => fetchJson<any[]>(`/entries/${publicId}/votes`),
    create: (publicId: string, data: { used_at: string; where_ref: string; is_correct: boolean }) =>
      fetchJson(`/entries/${publicId}/votes`, { method: "POST", body: JSON.stringify(data) }),
    withdraw: (publicId: string, voteId: number) =>
      fetchJson(`/entries/${publicId}/votes/${voteId}`, { method: "DELETE" }),
  },
  entries: {
    create: (data: {
      title: string
      body: string
      justification?: string
      category_id: number
      country: string
      scope: string
      basis: "responsible" | "relayed"
      basis_source?: string
      company_id?: number | null
      client_project_id?: number | null
      keywords: string[]
      difference_note?: string
      suggestion_id?: number
      sensitive_confirmed?: boolean
    }) => fetchJson<Entry>("/entries", { method: "POST", body: JSON.stringify(data) }),
    get: (publicId: string) => fetchJson<Entry>(`/entries/${encodeURIComponent(publicId)}`),
    update: (
      publicId: string,
      data: { title?: string; body?: string; justification?: string; keywords?: string[] },
    ) =>
      fetchJson<Entry>(`/entries/${encodeURIComponent(publicId)}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    setMyBasis: (publicId: string, body: { basis: "responsible" | "relayed"; source?: string }) =>
      fetchJson<Contact>(`/entries/${encodeURIComponent(publicId)}/my-basis`, jsonBody("PUT", body)),
    basisLog: (publicId: string) => fetchJson<BasisChange[]>(`/entries/${encodeURIComponent(publicId)}/basis-log`),
    history: (publicId: string) =>
      fetchJson<HistoryItem[]>(`/entries/${encodeURIComponent(publicId)}/history`),
    contributors: (publicId: string, version?: number) =>
      fetchJson<ContributorsResponse>(
        `/entries/${encodeURIComponent(publicId)}/contributors${version != null ? `?version=${version}` : ""}`,
      ),
    diff: (publicId: string, version: number, against?: number) =>
      fetchJson<EntryDiff>(
        `/entries/${encodeURIComponent(publicId)}/versions/${version}/diff${against != null ? `?against=${against}` : ""}`,
      ),
  },
  pullRequests: {
    create: (publicId: string, body: PullRequestCreate) =>
      fetchJson<PullRequest>(`/entries/${encodeURIComponent(publicId)}/pull-requests`, jsonBody("POST", body)),
    listForEntry: (publicId: string, openOnly = false) =>
      fetchJson<PullRequestBrief[]>(
        `/entries/${encodeURIComponent(publicId)}/pull-requests?open_only=${openOnly}`,
      ),
    get: (id: number | string) => fetchJson<PullRequest>(`/pull-requests/${id}`),
    diff: (id: number | string) => fetchJson<EntryDiff>(`/pull-requests/${id}/diff`),
    approve: (id: number | string, comment?: string) =>
      fetchJson<PullRequest>(`/pull-requests/${id}/approve`, jsonBody("POST", { comment: comment || null })),
    reject: (id: number | string, reason: string) =>
      fetchJson<PullRequest>(`/pull-requests/${id}/reject`, jsonBody("POST", { reason })),
    pending: () => fetchJson<PendingPullRequest[]>("/pull-requests/pending"),
  },
  approvals: {
    pending: () => fetchJson<any[]>("/approvals/pending"),
    verify: (versionId: number) => fetchJson(`/approvals/${versionId}/verify`, { method: "POST" }),
    sendBack: (versionId: number, comment?: string) =>
      fetchJson(`/approvals/${versionId}/send-back?comment=${encodeURIComponent(comment || "")}`, { method: "POST" }),
  },
}
