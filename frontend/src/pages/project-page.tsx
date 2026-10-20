import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { api, type ProjectDetail } from "@/lib/api"
import { formatPeriod } from "@/lib/people"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"

export function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    setProject(null)
    setError("")
    if (!id) return
    api.projects.get(id).then(setProject).catch((e) => setError(e.message || "Failed to load project"))
  }, [id])

  if (error) return <div className="text-red-600">{error}</div>
  if (!project) return <div className="text-stone-500">Loading…</div>

  return (
    <div className="space-y-6">
      <PageHeader title={project.name} />

      <div className="card text-sm">
        <Badge variant={project.status === "active" ? "success" : "neutral"} className="capitalize">{project.status}</Badge>
        {project.description && <p className="mt-3 text-stone-700">{project.description}</p>}
        <p className="mt-3">
          <span className="text-stone-500">Lead: </span>
          {project.lead ? (
            <Link to={`/people/${project.lead.id}`} className="font-medium hover:underline">{project.lead.display_name}</Link>
          ) : (
            <span className="text-stone-500">No lead assigned</span>
          )}
        </p>
      </div>

      <div className="list-panel">
        <h3 className="px-5 pt-4 text-sm font-semibold">Members ({project.members.length})</h3>
        {project.members.length === 0 ? (
          <div className="p-5 text-sm text-stone-500">No members yet</div>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {project.members.map((m) => (
              <li key={m.membership_id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <div>
                  <Link to={`/people/${m.user.id}`} className="font-medium hover:underline">{m.user.display_name}</Link>
                  <div className="mt-0.5 text-xs text-stone-500">
                    {m.role} · {formatPeriod(m.start_date, m.end_date)}
                  </div>
                </div>
                {m.ended && <Badge variant="neutral">Ended</Badge>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
