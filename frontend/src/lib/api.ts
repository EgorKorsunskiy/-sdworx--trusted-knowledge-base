const API_BASE = import.meta.env.VITE_API_URL || "/api"
const TOKEN_KEY = "peerpoint_token"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function fetchJson<T = any>(path: string, options: RequestInit = {}): Promise<T> {
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
  reputation: number
  is_active: boolean
  roles: { role: string; scope?: string | null }[]
  teams: { id: number; name: string; department: string }[]
}

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

export type Entry = {
  id: number
  public_id: string
  scope: string
  department: string
  country?: string | null
  category?: { id: number; name: string; is_default?: boolean } | null
  author: User
  team?: { id: number; name: string; department: string } | null
  tags: { id: number; name: string }[]
  current_version: EntryVersion
  created_at: string
  updated_at: string
  can_edit?: boolean
  who_to_ask?: PersonBrief[]
}

export const api = {
  listUsers: () => fetchJson<User[]>("/auth/users"),
  me: () => fetchJson<{ authenticated: boolean; user: User | null }>("/auth/me"),
  login: async (userId: number) => {
    const data = await fetchJson<{ authenticated: boolean; user: User; token?: string }>(
      "/auth/dev-login",
      { method: "POST", body: JSON.stringify({ user_id: userId }) },
    )
    if (data.token) setToken(data.token)
    return data
  },
  logout: async () => {
    await fetchJson("/auth/logout", { method: "POST" })
    setToken(null)
  },
  categories: () => fetchJson<Category[]>("/categories"),
  notifications: {
    list: () => fetchJson<any[]>("/notifications"),
    unreadCount: () => fetchJson<{ count: number }>("/notifications/unread-count"),
    markRead: (id: number) => fetchJson(`/notifications/${id}/read`, { method: "POST" }),
  },
  contributions: () => fetchJson<any>("/me/contributions"),
  admin: {
    settings: () => fetchJson<any[]>("/admin/settings"),
    updateSetting: (key: string, value: string) => fetchJson(`/admin/settings/${key}?value=${encodeURIComponent(value)}`, { method: "PUT" }),
    mappings: () => fetchJson<any[]>("/admin/verifier-mappings"),
    addMapping: (userId: number, department: string) =>
      fetchJson(`/admin/verifier-mappings?user_id=${userId}&department=${encodeURIComponent(department)}`, { method: "POST" }),
  },
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
      keywords: string[]
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
  },
  approvals: {
    pending: () => fetchJson<any[]>("/approvals/pending"),
    verify: (versionId: number) => fetchJson(`/approvals/${versionId}/verify`, { method: "POST" }),
    sendBack: (versionId: number, comment?: string) =>
      fetchJson(`/approvals/${versionId}/send-back?comment=${encodeURIComponent(comment || "")}`, { method: "POST" }),
  },
}
