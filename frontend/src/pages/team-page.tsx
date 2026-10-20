import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { api, type TeamDetail } from "@/lib/api"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"

export function TeamPage() {
  const { id } = useParams<{ id: string }>()
  const [team, setTeam] = useState<TeamDetail | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    setTeam(null)
    setError("")
    if (!id) return
    api.teams.get(id).then(setTeam).catch((e) => setError(e.message || "Failed to load team"))
  }, [id])

  if (error) return <div className="text-red-600">{error}</div>
  if (!team) return <div className="text-stone-500">Loading…</div>

  return (
    <div className="space-y-6">
      <PageHeader title={team.name} subtitle={team.department} />

      <div className="card text-sm">
        {team.description && <p className="text-stone-700">{team.description}</p>}
        <p className={team.description ? "mt-3" : ""}>
          <span className="text-stone-500">Lead: </span>
          {team.lead ? (
            <Link to={`/people/${team.lead.id}`} className="font-medium hover:underline">{team.lead.display_name}</Link>
          ) : (
            <span className="text-stone-500">No lead assigned</span>
          )}
        </p>
      </div>

      <div className="list-panel">
        <h3 className="px-5 pt-4 text-sm font-semibold">Members ({team.members.length})</h3>
        {team.members.length === 0 ? (
          <div className="p-5 text-sm text-stone-500">No members yet</div>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {team.members.map((m) => (
              <li key={m.membership_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <Link to={`/people/${m.user.id}`} className="font-medium hover:underline">{m.user.display_name}</Link>
                <span className="flex items-center gap-2 text-stone-500">
                  {m.role}
                  {m.is_primary && <Badge variant="success">Primary</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
