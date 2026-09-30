import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"
import { TrustBadge } from "@/components/trust-badge"
import { Link } from "react-router-dom"

export function ApprovalsPage() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [actionVersion, setActionVersion] = useState<number | null>(null)
  const [comment, setComment] = useState("")

  const load = () => {
    setLoading(true)
    api.approvals.pending()
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const verify = async (versionId: number) => {
    await api.approvals.verify(versionId)
    load()
  }

  const sendBack = async (versionId: number) => {
    await api.approvals.sendBack(versionId, comment)
    setComment("")
    setActionVersion(null)
    load()
  }

  if (loading) return <div className="text-stone-500">Loading…</div>

  return (
    <div>
      <PageHeader title="Approvals" subtitle="Pending versions in your scope" />
      <div className="list-panel">
        {items.length === 0 ? (
          <div className="p-8 text-center text-sm text-stone-500">No pending approvals in your scope.</div>
        ) : (
          items.map((item) => (
            <div key={item.version.id} className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-medium">{item.version.title}</h3>
                  <p className="mt-1 text-sm text-stone-500">
                    {item.entry.public_id} · {item.entry.country} · by {item.entry.author.display_name}
                  </p>
                </div>
                <TrustBadge status={item.version.status} />
              </div>
              <p className="mt-2 text-sm text-stone-700 line-clamp-3">{item.version.body}</p>
              {actionVersion === item.version.id ? (
                <div className="mt-3 space-y-2">
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Comment (optional for send back)"
                    className="input"
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <Button onClick={() => verify(item.version.id)}>Approve</Button>
                    <Button variant="secondary" onClick={() => sendBack(item.version.id)}>Request changes</Button>
                    <Button variant="ghost" onClick={() => setActionVersion(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setActionVersion(item.version.id)}>Review</Button>
                  <Link to={`/entries/${item.entry.public_id}`}>
                    <Button variant="secondary" size="sm">View entry</Button>
                  </Link>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
