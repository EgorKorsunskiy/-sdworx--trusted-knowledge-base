import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { api } from "@/lib/api"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"

export function ContributionsPage() {
  const [data, setData] = useState<any>(null)

  useEffect(() => {
    api.contributions().then(setData).catch(console.error)
  }, [])

  if (!data) return <div className="text-stone-500">Loading…</div>

  return (
    <div>
      <PageHeader title="My contributions" subtitle={`${data.user.display_name} · ${data.reputation} reputation`} />
      <div className="card">
        <h3 className="text-sm font-semibold">My entries</h3>
        <ul className="mt-3 divide-y divide-stone-100">
          {data.entries.map((e: any) => (
            <li key={e.public_id} className="py-3">
              <Link to={`/entries/${e.public_id}`} className="font-medium hover:underline">{e.title}</Link>
              <div className="mt-1 text-xs text-stone-500"><Badge variant="neutral">{e.status}</Badge> · {new Date(e.updated_at).toLocaleDateString()}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
