import { useEffect, useState } from "react"
import { api, type EntryDiff, type PendingPullRequest } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"
import { TrustBadge } from "@/components/trust-badge"
import { DiffView } from "@/components/diff-view"
import { Link, useNavigate } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { PRStatusBadge } from "@/components/pr-status-badge"
import { TagList } from "@/components/tag-chip"

export function ApprovalsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<any[]>([])
  const [prs, setPrs] = useState<PendingPullRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [actionVersion, setActionVersion] = useState<number | null>(null)
  const [comment, setComment] = useState("")
  const [diffs, setDiffs] = useState<Record<number, EntryDiff | "loading" | "error" | null>>({})

  const load = () => {
    setLoading(true)
    api.pullRequests.pending().then(setPrs).catch(() => setPrs([]))
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

  const toggleDiff = async (item: any) => {
    const id = item.version.id
    if (diffs[id]) {
      setDiffs((d) => ({ ...d, [id]: null }))
      return
    }
    setDiffs((d) => ({ ...d, [id]: "loading" }))
    try {
      const diff = await api.entries.diff(item.entry.public_id, item.version.version_number)
      setDiffs((d) => ({ ...d, [id]: diff }))
    } catch {
      setDiffs((d) => ({ ...d, [id]: "error" }))
    }
  }

  if (loading) return <div className="text-stone-500">Loading…</div>

  return (
    <div>
      <PageHeader title="Approvals" subtitle="Pull requests and versions waiting for your review" />
      {prs.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold">Pull requests</h2>
          <div className="list-panel">
            {prs.map((p) => (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 p-5">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/pull-requests/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                    <PRStatusBadge status={p.status} />
                    {p.is_stale && <Badge variant="outdated">Stale</Badge>}
                  </div>
                  <p className="mt-1 text-sm text-stone-500">
                    {p.entry.public_id} · by{" "}
                    <Link to={`/people/${p.author.id}`} className="hover:underline">{p.author.display_name}</Link>
                    {" "}· {p.step === "author" ? "Your approval as entry author" : "Entry author inactive: your approval as verifier"}
                  </p>
                  {p.basis && (
                    <p className="mt-0.5 text-xs text-stone-500">
                      Their basis: {p.basis === "responsible" ? "Responsible" : "Relayed"}
                      {p.basis === "relayed" && p.basis_source ? ` · source: ${p.basis_source}` : ""}
                    </p>
                  )}
                </div>
                <Button size="sm" onClick={() => navigate(`/pull-requests/${p.id}`)}>Review</Button>
              </div>
            ))}
          </div>
        </div>
      )}
      {prs.length > 0 && <h2 className="mb-2 text-sm font-semibold">Versions</h2>}
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
                    {item.entry.public_id} · {item.entry.country} · by{" "}
                    <Link to={`/people/${item.entry.author.id}`} className="hover:underline">{item.entry.author.display_name}</Link>
                  </p>
                </div>
                <TrustBadge status={item.version.status} />
              </div>
              <p className="mt-2 text-sm text-stone-700 line-clamp-3">{item.version.body}</p>
              <TagList tags={item.entry.tags ?? []} className="mt-2" />
              {(item.entry.contacts ?? []).length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-stone-600">
                  {item.entry.contacts.map((c: any) => (
                    <li key={c.user.id}>
                      <Link to={`/people/${c.user.id}`} className="font-medium hover:underline">{c.user.display_name}</Link>
                      {": "}{c.basis === "responsible" ? "Responsible" : "Relayed"}
                      {c.basis === "relayed" && c.source ? ` · source: ${c.source}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              {typeof diffs[item.version.id] === "object" && diffs[item.version.id] !== null && (
                <div className="mt-3">
                  <DiffView diff={diffs[item.version.id] as EntryDiff} />
                </div>
              )}
              {diffs[item.version.id] === "loading" && <div className="mt-3 text-sm text-stone-500">Loading changes…</div>}
              {diffs[item.version.id] === "error" && <div className="mt-3 text-sm text-red-600">Failed to load changes</div>}
              {item.entry.difference_note && (
                <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-600/20">
                  <div className="text-xs font-medium text-amber-700">Author's note: why is this different?</div>
                  <p className="mt-1 whitespace-pre-wrap">{item.entry.difference_note}</p>
                </div>
              )}
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
                  {item.version.version_number > 1 && (
                    <Button variant="ghost" size="sm" onClick={() => toggleDiff(item)}>
                      {diffs[item.version.id] ? "Hide changes" : "Show changes"}
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
