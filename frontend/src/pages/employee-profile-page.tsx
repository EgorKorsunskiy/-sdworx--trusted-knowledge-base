import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { api, type Profile } from "@/lib/api"
import { ROLE_LABELS, formatPeriod } from "@/lib/people"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { TrustBadge } from "@/components/trust-badge"

export function EmployeeProfilePage() {
  const { id } = useParams<{ id: string }>()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    setProfile(null)
    setError("")
    if (!id) return
    api.people.get(id).then(setProfile).catch((e) => setError(e.message || "Failed to load profile"))
  }, [id])

  if (error) return <div className="text-red-600">{error}</div>
  if (!profile) return <div className="text-stone-500">Loading…</div>

  const subtitle = [profile.title, profile.department, profile.country, `${profile.reputation} rep`]
    .filter(Boolean)
    .join(" · ")

  return (
    <div className="space-y-6">
      <PageHeader title={profile.display_name} subtitle={subtitle} />

      <div className="card">
        <h3 className="text-sm font-semibold">Roles</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {profile.roles.map((r) => (
            <Badge key={r.role}>{ROLE_LABELS[r.role] ?? r.role}</Badge>
          ))}
          {!profile.is_active && <Badge variant="danger">Deactivated</Badge>}
        </div>
      </div>

      <div className="list-panel">
        <h3 className="px-5 pt-4 text-sm font-semibold">Teams</h3>
        {profile.teams.length === 0 ? (
          <div className="p-5 text-sm text-stone-500">No teams yet</div>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {profile.teams.map((t) => (
              <li key={t.membership_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <Link to={`/teams/${t.id}`} className="font-medium hover:underline">{t.name}</Link>
                <span className="flex items-center gap-2 text-stone-500">
                  {t.role}
                  {t.is_primary && <Badge variant="success">Primary</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="list-panel">
        <h3 className="px-5 pt-4 text-sm font-semibold">Projects</h3>
        {profile.projects.length === 0 ? (
          <div className="p-5 text-sm text-stone-500">No projects yet</div>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {profile.projects.map((p) => (
              <li key={p.membership_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <div>
                  <Link to={`/projects/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                  <div className="mt-0.5 text-xs text-stone-500">
                    {p.role} · {formatPeriod(p.start_date, p.end_date)}
                  </div>
                </div>
                <span className="flex items-center gap-2">
                  <Badge variant={p.status === "active" ? "success" : "neutral"} className="capitalize">{p.status}</Badge>
                  {p.ended && <Badge variant="neutral">Ended</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="list-panel">
        <h3 className="px-5 pt-4 text-sm font-semibold">Entries</h3>
        {profile.entries.length === 0 ? (
          <div className="p-5 text-sm text-stone-500">No entries yet</div>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {profile.entries.map((e) => (
              <li key={e.public_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <Link to={`/entries/${e.public_id}`} className="font-medium hover:underline">{e.title}</Link>
                <TrustBadge status={e.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
