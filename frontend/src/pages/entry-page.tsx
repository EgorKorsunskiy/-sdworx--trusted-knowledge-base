import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Dialog } from "@/components/ui/dialog"
import { TrustBadge } from "@/components/trust-badge"

export function EntryPage() {
  const { publicId } = useParams<{ publicId: string }>()
  const [entry, setEntry] = useState<any>(null)
  const [votes, setVotes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)
  const [showVoteModal, setShowVoteModal] = useState(false)
  const [voteDate, setVoteDate] = useState("")
  const [voteWhere, setVoteWhere] = useState("")
  const [voteCorrect, setVoteCorrect] = useState<boolean>(true)
  const [showOutdatedModal, setShowOutdatedModal] = useState(false)
  const [outdatedReason, setOutdatedReason] = useState("")

  const load = () => {
    if (!publicId) return
    api.entries.get(publicId)
      .then((res: any) => setEntry(res))
      .catch((err: any) => setError(err.message || "Failed to load entry"))
    api.votes.list(publicId)
      .then((res: any) => setVotes(res))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [publicId])

  const submitVote = async () => {
    if (!publicId || !voteDate || !voteWhere) return
    await api.votes.create(publicId, { used_at: voteDate, where_ref: voteWhere, is_correct: voteCorrect })
    setShowVoteModal(false)
    setVoteWhere("")
    load()
  }

  const markOutdated = async () => {
    if (!publicId || !outdatedReason.trim()) return
    await api.outdated.mark(publicId, outdatedReason)
    setShowOutdatedModal(false)
    setOutdatedReason("")
    load()
  }

  const copyReference = () => {
    if (!entry) return
    navigator.clipboard.writeText(`${entry.public_id}@v${entry.current_version.version_number}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (loading) return <div className="text-stone-500">Loading…</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!entry) return null

  const v = entry.current_version
  const correctCount = votes.filter((x) => x.is_correct).length
  const incorrectCount = votes.filter((x) => !x.is_correct).length

  return (
    <div>
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-900">
        <ArrowLeft className="h-4 w-4" /> Back to results
      </Link>

      <div className="mt-4 card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{v.title}</h1>
            <p className="mt-1 text-sm text-stone-500">
              {entry.public_id} · Version {v.version_number} · Updated {new Date(v.created_at).toLocaleDateString()}
            </p>
          </div>
          <Button variant="secondary" size="sm">Suggest a change</Button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <TrustBadge status={v.status} />
          <Badge variant="success">{correctCount} correct</Badge>
          <Badge variant="danger">{incorrectCount} incorrect</Badge>
        </div>

        <p className="mt-5 text-sm leading-6 text-stone-700 whitespace-pre-wrap">{v.body}</p>

        {v.justification && (
          <div className="mt-5 rounded-lg bg-stone-50 p-3 text-sm text-stone-600">
            <span className="font-medium">Justification:</span> {v.justification}
          </div>
        )}

        <dl className="mt-6 divide-y divide-stone-100 border-t border-stone-100 text-sm">
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Author</dt>
            <dd>{entry.author.display_name} · {entry.author.reputation} rep</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Country · Department</dt>
            <dd>{entry.country} · {entry.department}</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Scope</dt>
            <dd className="capitalize">{entry.scope}</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Tags</dt>
            <dd className="flex flex-wrap gap-1">
              {entry.tags.map((t: any) => <Badge key={t.id} variant="neutral">{t.name}</Badge>)}
            </dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={() => setShowVoteModal(true)}>Report usage</Button>
          <Button variant="secondary" onClick={copyReference}>{copied ? "Copied" : "Copy reference"}</Button>
          <Button variant="ghost" onClick={() => setShowOutdatedModal(true)}>Mark outdated</Button>
        </div>
      </div>

      {votes.length > 0 && (
        <div className="mt-6 card">
          <h3 className="text-sm font-semibold">Usage records</h3>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {votes.map((vote) => (
              <li key={vote.id} className="flex justify-between py-2">
                <span>{vote.user.display_name} · {vote.where_ref} · {vote.used_at}</span>
                <Badge variant={vote.is_correct ? "success" : "danger"}>{vote.is_correct ? "Correct" : "Incorrect"}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Dialog open={showOutdatedModal} onClose={() => setShowOutdatedModal(false)} title="Mark as outdated">
        <div className="space-y-4">
          <p className="text-sm text-stone-600">Explain what changed so the author and verifiers can update the entry.</p>
          <textarea
            value={outdatedReason}
            onChange={(e) => setOutdatedReason(e.target.value)}
            placeholder="Reason"
            className="input"
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowOutdatedModal(false)}>Cancel</Button>
            <Button onClick={markOutdated} disabled={!outdatedReason.trim()}>Mark outdated</Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={showVoteModal} onClose={() => setShowVoteModal(false)} title="Report usage">
        <div className="space-y-4">
          <p className="text-sm text-stone-600">This records that you used this information, where, and whether it was correct.</p>
          <div>
            <label className="label">Date of use</label>
            <Input type="date" value={voteDate} onChange={(e) => setVoteDate(e.target.value)} />
          </div>
          <div>
            <label className="label">Where applied (case / process)</label>
            <Input value={voteWhere} onChange={(e) => setVoteWhere(e.target.value)} placeholder="e.g. payroll run #42" />
          </div>
          <div className="flex items-center gap-3">
            <Button variant={voteCorrect ? "primary" : "secondary"} onClick={() => setVoteCorrect(true)}>Correct</Button>
            <Button variant={!voteCorrect ? "primary" : "secondary"} onClick={() => setVoteCorrect(false)}>Incorrect</Button>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowVoteModal(false)}>Cancel</Button>
            <Button onClick={submitVote} disabled={!voteDate || !voteWhere}>Confirm</Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
