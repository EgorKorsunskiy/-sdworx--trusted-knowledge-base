import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api, type EntryDiff, type PRApproval, type PullRequest } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { DiffView } from "@/components/diff-view"
import { PRStatusBadge } from "@/components/pr-status-badge"

type StepState = "done" | "current" | "pending" | "failed" | "skipped"

type TimelineStep = {
  label: string
  state: StepState
  who?: { id: number; display_name: string }
  at?: string
  comment?: string | null
}

const DOT: Record<StepState, string> = {
  done: "bg-emerald-500",
  current: "bg-amber-500",
  pending: "bg-stone-300",
  failed: "bg-red-500",
  skipped: "bg-stone-400",
}

function fmt(d: string) {
  return new Date(d).toLocaleString()
}

function WaitingNames({ people }: { people: { id: number; display_name: string }[] }) {
  return (
    <>
      {people.map((p, i) => (
        <span key={p.id}>
          {i > 0 && ", "}
          <Link to={`/people/${p.id}`} className="font-medium hover:underline">{p.display_name}</Link>
        </span>
      ))}
    </>
  )
}

function buildTimeline(pr: PullRequest): TimelineStep[] {
  const stepRow = (step: "author" | "verifier"): PRApproval | undefined =>
    pr.approvals.find((a) => a.step === step)
  const stage = (step: "author" | "verifier", label: string, skipLabel?: string): TimelineStep => {
    const row = stepRow(step)
    if (row) {
      const state: StepState = row.action === "approve" ? "done" : row.action === "reject" ? "failed" : "skipped"
      const text = row.action === "approve" ? label : row.action === "reject" ? `${label}: rejected` : skipLabel ?? label
      return { label: text, state, who: row.approver, at: row.created_at, comment: row.comment }
    }
    return { label, state: pr.next_step === step ? "current" : "pending" }
  }
  const last: TimelineStep =
    pr.status === "merged"
      ? { label: "Merged", state: "done", at: pr.resolved_at ?? undefined }
      : pr.status === "rejected"
        ? { label: "Rejected", state: "failed", at: pr.resolved_at ?? undefined, comment: pr.rejection_reason }
        : { label: "Merge", state: "pending" }
  return [
    { label: "Opened", state: "done", who: pr.author, at: pr.created_at, comment: pr.description },
    stage("author", "Author approval", "Author approval skipped (author is no longer active)"),
    // Only shown when the author is gone and a verifier stood in for them.
    ...(pr.next_step === "verifier" || pr.approvals.some((a) => a.step === "verifier")
      ? [stage("verifier", "Approved by a verifier in the author's place")]
      : []),
    last,
  ]
}

export function PullRequestPage() {
  const { id } = useParams<{ id: string }>()
  const [pr, setPr] = useState<PullRequest | null>(null)
  const [diff, setDiff] = useState<EntryDiff | null>(null)
  const [diffError, setDiffError] = useState("")
  const [error, setError] = useState("")
  const [actionError, setActionError] = useState("")
  const [busy, setBusy] = useState(false)
  const [showReject, setShowReject] = useState(false)
  const [reason, setReason] = useState("")

  const load = () => {
    if (!id) return
    api.pullRequests
      .get(id)
      .then((p) => {
        setPr(p)
        setError("")
      })
      .catch((e: any) => setError(e.message || "Failed to load pull request"))
    api.pullRequests
      .diff(id)
      .then((d) => {
        setDiff(d)
        setDiffError("")
      })
      .catch((e: any) => setDiffError(e.message || "Failed to load changes"))
  }

  useEffect(() => {
    setPr(null)
    setDiff(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setActionError("")
    try {
      await fn()
      setShowReject(false)
      setReason("")
      load()
    } catch (e: any) {
      setActionError(e.message || "Action failed")
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="text-red-600">{error}</div>
  if (!pr || !id) return <div className="text-stone-500">Loading…</div>

  const canApprove = pr.can_approve_as_author || pr.can_approve_as_verifier
  const timeline = buildTimeline(pr)

  return (
    <div>
      <Link
        to={`/entries/${pr.entry.public_id}`}
        className="inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-900"
      >
        <ArrowLeft className="h-4 w-4" /> Back to {pr.entry.public_id}
      </Link>

      <div className="mt-4 card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{pr.title}</h1>
            <p className="mt-1 text-sm text-stone-500">
              <Link to={`/entries/${pr.entry.public_id}`} className="hover:underline">{pr.entry.public_id}</Link>
              {" "}· opened by{" "}
              <Link to={`/people/${pr.author.id}`} className="hover:underline">{pr.author.display_name}</Link>
              {" "}· {new Date(pr.created_at).toLocaleDateString()}
            </p>
          </div>
          <PRStatusBadge status={pr.status} />
        </div>
        {pr.change_note && <p className="mt-3 text-sm italic text-stone-600">{pr.change_note}</p>}
        {pr.basis && (
          <p className="mt-2 text-xs text-stone-500">
            {pr.author.display_name}'s basis for this change: {pr.basis === "responsible" ? "Responsible" : "Relayed"}
            {pr.basis === "relayed" && pr.basis_source ? ` · source: ${pr.basis_source}` : ""}. They become a contact of the
            entry with it once the pull request is merged.
          </p>
        )}

        {pr.is_stale && (
          <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-600/20">
            The entry changed since this pull request was opened (now v{pr.entry.current_version_number}, based on v
            {pr.base_version_number}). It can no longer be approved; it can only be rejected. Open a new pull request
            instead.
          </div>
        )}

        {pr.next_step && !pr.is_stale && (
          <div
            className={`mt-4 rounded-lg p-3 text-sm ring-1 ${
              pr.next_step === "verifier" && pr.waiting_on.length === 0
                ? "bg-red-50 text-red-800 ring-red-600/20"
                : "bg-stone-50 text-stone-700 ring-stone-200"
            }`}
          >
            {pr.next_step === "author" && (
              <>
                Waiting for the entry author, <WaitingNames people={pr.waiting_on} />. Once they approve, the change is
                merged into the entry as a new Unverified version, which then goes through normal verification.
              </>
            )}
            {pr.next_step === "verifier" && pr.waiting_on.length > 0 && (
              <>
                The entry author is no longer active, so a verifier in scope can approve this in their place. Waiting for
                one of: <WaitingNames people={pr.waiting_on} />.
              </>
            )}
            {pr.next_step === "verifier" && pr.waiting_on.length === 0 && (
              <>
                The entry author is no longer active and no verifier is in scope for this entry ({pr.entry.department}),
                so nobody can approve it. An Admin needs to map a senior expert to this department, or put the entry's
                author in a team with a team lead or manager.
              </>
            )}
          </div>
        )}

        {pr.status === "merged" && pr.merged_version_number != null && (
          <div className="mt-4 text-sm">
            <Link to={`/entries/${pr.entry.public_id}`} className="font-medium text-emerald-700 hover:underline">
              Merged into {pr.entry.public_id} as v{pr.merged_version_number}
            </Link>
          </div>
        )}

        <ol className="mt-5 space-y-3 border-t border-stone-100 pt-4">
          {timeline.map((s, i) => (
            <li key={i} className="flex items-start gap-3 text-sm">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${DOT[s.state]}`} />
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={s.state === "pending" ? "text-stone-400" : "font-medium"}>{s.label}</span>
                  {s.state === "current" && <Badge variant="warning">Waiting</Badge>}
                  {s.state === "skipped" && <Badge variant="neutral">Skipped</Badge>}
                  {s.who && (
                    <Link to={`/people/${s.who.id}`} className="text-stone-600 hover:underline">{s.who.display_name}</Link>
                  )}
                  {s.at && <span className="text-xs text-stone-400">{fmt(s.at)}</span>}
                </div>
                {s.comment && <p className="mt-0.5 text-stone-600">{s.comment}</p>}
              </div>
            </li>
          ))}
        </ol>

        {actionError && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
            {actionError}
          </div>
        )}
        {(canApprove || pr.can_reject) && (
          <div className="mt-4 flex gap-2">
            {canApprove && (
              <Button disabled={busy} onClick={() => act(() => api.pullRequests.approve(id))}>
                {pr.can_approve_as_author ? "Approve and merge" : "Approve in place of the inactive author"}
              </Button>
            )}
            {pr.can_reject && (
              <Button variant="secondary" disabled={busy} onClick={() => setShowReject(true)}>Reject</Button>
            )}
          </div>
        )}
      </div>

      <div className="mt-6 card">
        <h3 className="mb-3 text-sm font-semibold">Proposed changes</h3>
        {diff ? (
          <DiffView diff={diff} />
        ) : diffError ? (
          <div className="text-sm text-red-600">{diffError}</div>
        ) : (
          <div className="text-sm text-stone-500">Loading…</div>
        )}
      </div>

      <Dialog open={showReject} onClose={() => setShowReject(false)} title="Reject pull request">
        <div className="space-y-4">
          <p className="text-sm text-stone-600">Tell {pr.author.display_name} why this change is rejected.</p>
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" />
          {actionError && <div className="text-sm text-red-600">{actionError}</div>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowReject(false)}>Cancel</Button>
            <Button
              disabled={busy || !reason.trim()}
              onClick={() => act(() => api.pullRequests.reject(id, reason.trim()))}
            >
              Reject
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
