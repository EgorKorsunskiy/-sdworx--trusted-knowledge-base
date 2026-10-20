import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { CalendarDays, MessageCircle, Users, TriangleAlert } from "lucide-react"
import {
  api,
  type CoauthorRequestOut,
  type Meme,
  type MemeSuggestion,
  type OverviewItem,
} from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Input, Select } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { TagChip } from "@/components/tag-chip"
import { TrustBadge } from "@/components/trust-badge"
import { BasisFields, basisIsValid, basisLabel, type BasisValue } from "@/components/basis-fields"

const STATUS: Record<Meme["status"], { label: string; variant: "neutral" | "warning" | "success" | "danger" }> = {
  new: { label: "New", variant: "neutral" },
  preparing: { label: "Preparing", variant: "warning" },
  published: { label: "Published", variant: "success" },
  declined: { label: "Declined", variant: "danger" },
}

const ACTION_LABEL: Record<string, string> = {
  created: "Suggestion received",
  approve: "Approved",
  reject: "Rejected",
  postpone: "Postponed",
  reopen: "Moved back to To decide",
  withdraw: "Withdrew approval",
  closed: "Closed: published without them",
  joined: "Became a co-author",
}

const REASONS = ["Not relevant", "Incorrect", "I didn't say / confirm this"]

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString()
const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

function sourceDates(m: Meme) {
  const { date_from, date_to } = m.source
  return date_to ? `${fmtDate(date_from)} – ${fmtDate(date_to)}` : fmtDate(date_from)
}

function Person({ p }: { p: { id: number; display_name: string } }) {
  return <Link to={`/people/${p.id}`} className="font-medium hover:underline">{p.display_name}</Link>
}

function Decision({ s }: { s: MemeSuggestion }) {
  const variant = s.state === "accepted" ? "success" : s.state === "declined" ? "danger" : s.state === "postponed" ? "warning" : "neutral"
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <Person p={s.owner} />
      <Badge variant={variant}>{s.label}</Badge>
      {s.decided_at && <span className="text-xs text-stone-500">{fmtDate(s.decided_at)}</span>}
      {s.basis && (
        <span className="text-xs text-stone-600">
          {basisLabel(s.basis)}
          {s.basis === "relayed" && s.source ? `: ${s.source}` : ""}
        </span>
      )}
      {s.reason && <span className="text-xs italic text-stone-600">“{s.reason}”</span>}
    </li>
  )
}

function History({ suggestions }: { suggestions: MemeSuggestion[] }) {
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Decision history</div>
      {suggestions.map((s) => (
        <div key={s.id}>
          <div className="text-sm font-medium">
            <Person p={s.owner} />
            {s.is_mine && <span className="ml-1 text-xs text-stone-500">(you)</span>}
          </div>
          <ol className="mt-1 space-y-0.5 border-l border-stone-200 pl-3 text-xs text-stone-600">
            {s.history.map((e) => (
              <li key={e.id}>
                <span className="font-medium text-stone-800">{ACTION_LABEL[e.action] ?? e.action}</span>
                <span className="text-stone-400"> · {fmtDateTime(e.created_at)}</span>
                {e.basis && (
                  <span> · {basisLabel(e.basis)}{e.basis === "relayed" && e.source ? `, source: ${e.source}` : ""}</span>
                )}
                {e.reason && <span className="italic"> · “{e.reason}”</span>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

function Quotes({ meme }: { meme: Meme }) {
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Quotes and context</div>
      {meme.quotes.map((q) => (
        <div key={q.id} className="rounded-lg bg-stone-50 p-3 text-xs">
          <div className="mb-1 text-stone-500">
            {q.is_confirmation ? "Confirmation by " : "Said by "}
            <Person p={q.user} /> · {q.at}
          </div>
          <ul className="space-y-0.5">
            {q.context.length === 0 && <li className="text-stone-700">“{q.text}”</li>}
            {q.context.map((l, i) => (
              <li key={i} className={l.quote ? "rounded bg-amber-100 px-1.5 py-0.5 text-stone-900" : "px-1.5 text-stone-500"}>
                <span className="font-medium">{l.speaker}:</span> {l.text}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

/** Approve with an authorship basis, then go to the prefilled Add entry form (FR-MS12, FR-MP10). */
function ApproveDialog({ suggestion, onClose, onDone }: { suggestion: MemeSuggestion; onClose: () => void; onDone: () => void }) {
  const navigate = useNavigate()
  const hint = suggestion.basis_hint
  // The agent's hint only prefills; the author confirms or changes it (FR-MO16)
  const [value, setValue] = useState<BasisValue>({
    basis: hint?.basis ?? suggestion.basis ?? "",
    source: hint?.source ?? suggestion.source ?? "",
  })
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!value.basis) return
    setBusy(true)
    setError("")
    try {
      await api.information.approve(suggestion.id, { basis: value.basis, source: value.source.trim() || undefined })
      onDone()
      navigate(`/add?suggestion=${suggestion.id}`)
    } catch (e: any) {
      setError(e.message || "Could not approve")
      setBusy(false)
    }
  }

  return (
    <Dialog open onClose={onClose} title="Approve and add to the repository">
      <div className="space-y-4">
        <p className="text-sm text-stone-600">
          You become an author of this information. Choose your basis; the Add entry form opens next, prefilled.
        </p>
        {hint && <p className="text-xs text-stone-500">Suggested from the conversation. Please confirm or change it.</p>}
        {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        <BasisFields value={value} onChange={setValue} idPrefix={`approve-${suggestion.id}`} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={!basisIsValid(value) || busy}>Approve</Button>
        </div>
      </div>
    </Dialog>
  )
}

function RejectDialog({ suggestion, onClose, onDone }: { suggestion: MemeSuggestion; onClose: () => void; onDone: () => void }) {
  const [preset, setPreset] = useState("")
  const [text, setText] = useState("")
  const [error, setError] = useState("")

  const submit = async () => {
    try {
      await api.information.reject(suggestion.id, (text.trim() || preset) || undefined)
      onDone()
    } catch (e: any) {
      setError(e.message || "Could not reject")
    }
  }

  return (
    <Dialog open onClose={onClose} title="Reject this suggestion">
      <div className="space-y-4">
        <p className="text-sm text-stone-600">
          Rejecting is final for your suggestion. Other candidates keep their own, and your reason is visible to them.
          Do not put personal or confidential customer data in it.
        </p>
        {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        <div>
          <label className="label">Reason (optional)</label>
          <Select value={preset} onChange={(e) => setPreset(e.target.value)} className="mt-1.5">
            <option value="">No reason</option>
            {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </Select>
          <Input className="mt-2" placeholder="Or write your own" maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Reject</Button>
        </div>
      </div>
    </Dialog>
  )
}

/** Co-authorship request for a published meme (FR-MS19). */
export function CoauthorDialog({ meme, onClose, onDone }: { meme: Meme; onClose: () => void; onDone: () => void }) {
  const { user } = useAuth()
  const ownQuote = meme.quotes.find((q) => q.user.id === user?.id)
  const [value, setValue] = useState<BasisValue>({ basis: "", source: "" })
  const [note, setNote] = useState("")
  const [evidence, setEvidence] = useState("")
  const [error, setError] = useState("")

  const submit = async () => {
    if (!value.basis) return
    try {
      await api.information.requestCoauthorship(meme.id, {
        basis: value.basis,
        source: value.source.trim() || undefined,
        note: note.trim() || undefined,
        evidence: ownQuote ? undefined : evidence.trim() || undefined,
      })
      onDone()
    } catch (e: any) {
      setError(e.message || "Could not send the request")
    }
  }

  return (
    <Dialog open onClose={onClose} title="Request co-authorship">
      <div className="space-y-4">
        <p className="text-sm text-stone-600">
          The authors of “{meme.title}” decide; the first to answer decides. The text and its verification do not change.
        </p>
        {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        <BasisFields value={value} onChange={setValue} idPrefix={`coauthor-${meme.id}`} />
        <div>
          <label className="label">Note (optional)</label>
          <Textarea rows={2} maxLength={1000} className="mt-1.5 min-h-0" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div>
          <label className="label">Evidence</label>
          {ownQuote ? (
            <blockquote className="mt-1.5 rounded-lg bg-stone-50 p-2 text-sm italic text-stone-700">
              “{ownQuote.text}” <span className="not-italic text-stone-400">· {ownQuote.at}</span>
            </blockquote>
          ) : (
            <Input
              className="mt-1.5"
              placeholder="Timestamp or message where you said or confirmed it"
              maxLength={500}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          )}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={!basisIsValid(value)}>Send request</Button>
        </div>
      </div>
    </Dialog>
  )
}

function DecideRequestDialog({
  request,
  accept,
  onClose,
  onDone,
}: {
  request: CoauthorRequestOut
  accept: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")
  const submit = async () => {
    try {
      if (accept) await api.information.acceptRequest(request.id, reason.trim() || undefined)
      else await api.information.declineRequest(request.id, reason.trim() || undefined)
      onDone()
    } catch (e: any) {
      setError(e.message || "Could not save")
      // someone else may have answered first
      setTimeout(onDone, 1500)
    }
  }
  return (
    <Dialog open onClose={onClose} title={accept ? "Accept co-author" : "Decline request"}>
      <div className="space-y-4">
        {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
        <p className="text-sm text-stone-600">
          {accept
            ? `${request.requester.display_name} becomes a co-author, with their basis. No new version is created.`
            : `${request.requester.display_name} cannot ask again for this meme.`}
        </p>
        <Input placeholder="Reason (optional)" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>{accept ? "Accept" : "Decline"}</Button>
        </div>
      </div>
    </Dialog>
  )
}

type DialogState =
  | { kind: "approve" | "reject"; suggestion: MemeSuggestion }
  | { kind: "coauthor" }
  | { kind: "accept" | "decline"; request: CoauthorRequestOut }
  | null

/**
 * One item of the Information overview.
 *
 * In the list (`variant="list"`) an item is compact: statement, source, who said and confirmed it, the user's own
 * decision and the actions. Clicking it opens the detail page (`variant="detail"`), which adds scope, category, tags,
 * the other candidates and their decisions, authors, similar entries, quotes with context and the decision history.
 * Decision buttons exist only on the user's own suggestions.
 */
export function MemeCard({
  item,
  variant = "list",
  highlight,
  onChanged,
}: {
  item: OverviewItem
  variant?: "list" | "detail"
  highlight?: boolean
  onChanged: () => void
}) {
  const navigate = useNavigate()
  const detail = variant === "detail"
  const meme = item.meme
  const mine = meme.suggestions.find((s) => s.is_mine) ?? null
  const others = meme.suggestions.filter((s) => !s.is_mine)
  const [dialog, setDialog] = useState<DialogState>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError("")
    try {
      await fn()
      onChanged()
    } catch (e: any) {
      setError(e.message || "Action failed")
    } finally {
      setBusy(false)
    }
  }
  const done = () => {
    setDialog(null)
    onChanged()
  }

  const status = STATUS[meme.status]
  const isYoursSuggestion = item.type === "suggestion" && mine !== null
  const open_ = mine && (mine.state === "pending" || mine.state === "postponed")
  const requestable = meme.can_request_coauthorship && !meme.is_author && !(item.type === "suggestion" && open_)
  const detailPath = `/information/memes/${meme.id}`

  // In the list the whole card opens the detail page, except where the click was meant for a button or link
  const openDetail = (e: React.MouseEvent) => {
    if (detail) return
    if ((e.target as HTMLElement).closest("a, button, input, select, textarea, [role=dialog]")) return
    navigate(detailPath)
  }

  return (
    <div
      id={`item-${item.type}-${item.id}`}
      onClick={openDetail}
      className={`p-5 ${highlight ? "bg-amber-50/50" : ""} ${detail ? "" : "cursor-pointer hover:bg-stone-50"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className={detail ? "text-xl font-semibold tracking-tight" : "font-medium"}>
            {detail ? meme.title : <Link to={detailPath} className="hover:underline">{meme.title}</Link>}
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-stone-500">
            {meme.source.kind === "meeting" ? <Users className="h-3.5 w-3.5" /> : <MessageCircle className="h-3.5 w-3.5" />}
            {meme.source.kind === "meeting" ? "Meeting" : "Group chat"}: {meme.source.title}
            <CalendarDays className="h-3.5 w-3.5" /> {sourceDates(meme)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {meme.is_author && <Badge variant="success">Author</Badge>}
          <Badge variant={status.variant}>{status.label}</Badge>
          {meme.entry && <TrustBadge status={meme.entry.status} />}
        </div>
      </div>

      <p className={`mt-3 text-sm leading-6 text-stone-800 ${detail ? "" : "line-clamp-3"}`}>{meme.statement}</p>

      {meme.sensitive && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-800">
          <TriangleAlert className="h-3.5 w-3.5" />
          Flagged: may contain personal or confidential customer data. Check the text before it is published.
        </div>
      )}

      {detail && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <Badge variant="neutral">{meme.scope_label}</Badge>
          {meme.category && <span className="text-stone-500">{meme.category}</span>}
          {meme.country && <span className="text-stone-500">· {meme.country}</span>}
          {meme.tags.map((t) => <TagChip key={t.id} tag={t} />)}
        </div>
      )}

      <dl className="mt-3 space-y-1 text-sm">
        <div className="flex flex-wrap gap-x-2">
          <dt className="text-stone-500">Said by</dt>
          <dd><Person p={meme.speaker} /></dd>
          {meme.confirmers.length > 0 && (
            <>
              <dt className="text-stone-500">· confirmed by</dt>
              <dd className="flex flex-wrap gap-x-2">
                {meme.confirmers.map((c) => <Person key={c.id} p={c} />)}
              </dd>
            </>
          )}
        </div>
        {detail && meme.authors.length > 0 && (
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-stone-500">{meme.status === "published" ? "Authors" : "Approved by"}</dt>
            <dd className="flex flex-wrap gap-x-3">
              {meme.authors.map((a) => (
                <span key={a.user.id}>
                  <Person p={a.user} />{a.is_me && " (you)"}{" "}
                  <span className="text-xs text-stone-500">
                    {basisLabel(a.basis)}{a.basis === "relayed" && a.source ? `: ${a.source}` : ""}
                  </span>
                </span>
              ))}
            </dd>
          </div>
        )}
      </dl>

      {meme.entry && (
        <p className="mt-2 text-sm">
          In the repository as{" "}
          <Link to={`/entries/${meme.entry.public_id}`} className="font-medium underline">{meme.entry.public_id}</Link>
        </p>
      )}

      {detail && meme.similar_entries.length > 0 && (
        <p className="mt-2 text-xs text-stone-600">
          Similar entries:{" "}
          {meme.similar_entries.map((s, i) => (
            <span key={s.public_id}>
              {i > 0 && ", "}
              <Link to={`/entries/${s.public_id}`} className="underline">{s.public_id}</Link> ({Math.round(s.score * 100)}%)
            </span>
          ))}
        </p>
      )}

      {/* The user's own decision */}
      {isYoursSuggestion && mine && (
        <div className="mt-3 rounded-lg bg-stone-50 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-stone-500">Your suggestion</span>
            <Badge variant={mine.state === "accepted" ? "success" : mine.state === "declined" ? "danger" : mine.state === "postponed" ? "warning" : "neutral"}>
              {mine.label}
            </Badge>
            {mine.decided_at && <span className="text-xs text-stone-500">{fmtDate(mine.decided_at)}</span>}
            {mine.role === "confirmer" && <span className="text-xs text-stone-500">You confirmed this statement</span>}
          </div>
          {mine.role === "confirmer" && (
            <p className="mt-1 text-xs italic text-stone-600">
              “{meme.quotes.find((q) => q.is_confirmation && q.user.id === mine.owner.id)?.text}”
            </p>
          )}
        </div>
      )}

      {/* The other candidates and their decisions are part of the details */}
      {detail && others.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium uppercase tracking-wide text-stone-500">
            {isYoursSuggestion ? "Other candidates" : "Candidates"}
          </div>
          <ul className="mt-1 space-y-1">{others.map((s) => <Decision key={s.id} s={s} />)}</ul>
        </div>
      )}

      {item.type === "coauthor_request" && (
        <RequestBox request={item.request} />
      )}
      {detail && item.type !== "coauthor_request" && meme.pending_requests.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-stone-500">Co-author requests</div>
          {meme.pending_requests.map((r) => (
            <div key={r.id}>
              <RequestBox request={r} />
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => setDialog({ kind: "accept", request: r })}>Accept</Button>
                <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "decline", request: r })}>Decline</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {meme.my_request && item.type !== "coauthor_request" && (
        <p className="mt-2 text-xs text-stone-600">
          Your co-authorship request:{" "}
          <b className="capitalize">{meme.my_request.status}</b>
          {meme.my_request.decision_reason && ` · “${meme.my_request.decision_reason}”`}
        </p>
      )}

      {error && <div className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}

      {/* Actions */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {isYoursSuggestion && mine && open_ && (
          <>
            <Button size="sm" disabled={busy} onClick={() => setDialog({ kind: "approve", suggestion: mine })}>Approve</Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setDialog({ kind: "reject", suggestion: mine })}>Reject</Button>
            {mine.state === "pending" ? (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api.information.postpone(mine.id))}>Postpone</Button>
            ) : (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api.information.reopen(mine.id))}>
                Move back to To decide
              </Button>
            )}
          </>
        )}
        {isYoursSuggestion && mine && mine.state === "accepted" && meme.status === "preparing" && (
          <>
            <Button size="sm" onClick={() => navigate(`/add?suggestion=${mine.id}`)}>Add to repository</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => api.information.withdraw(mine.id))}>
              Withdraw
            </Button>
          </>
        )}
        {item.type === "coauthor_request" && item.request.status === "pending" && (
          <>
            <Button size="sm" onClick={() => setDialog({ kind: "accept", request: item.request })}>Accept</Button>
            <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "decline", request: item.request })}>Decline</Button>
          </>
        )}
        {requestable && item.type !== "coauthor_request" && (
          <span title={meme.request_blocked_reason ?? undefined}>
            <Button size="sm" variant="secondary" disabled={!!meme.request_blocked_reason} onClick={() => setDialog({ kind: "coauthor" })}>
              Request co-authorship
            </Button>
          </span>
        )}
        {!detail && (
          <Link to={detailPath} className="ml-auto text-xs font-medium text-stone-600 hover:text-stone-900 hover:underline">
            Details
          </Link>
        )}
      </div>
      {requestable && meme.request_blocked_reason && item.type !== "coauthor_request" && (
        <p className="mt-1 text-xs text-stone-500">{meme.request_blocked_reason}</p>
      )}

      {detail && (
        <div className="mt-5 grid gap-5 border-t border-stone-100 pt-4 md:grid-cols-2">
          <Quotes meme={meme} />
          <History suggestions={meme.suggestions} />
        </div>
      )}

      {dialog?.kind === "approve" && <ApproveDialog suggestion={dialog.suggestion} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.kind === "reject" && <RejectDialog suggestion={dialog.suggestion} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.kind === "coauthor" && <CoauthorDialog meme={meme} onClose={() => setDialog(null)} onDone={done} />}
      {(dialog?.kind === "accept" || dialog?.kind === "decline") && (
        <DecideRequestDialog request={dialog.request} accept={dialog.kind === "accept"} onClose={() => setDialog(null)} onDone={done} />
      )}
    </div>
  )
}

function RequestBox({ request }: { request: CoauthorRequestOut }) {
  return (
    <div className="mt-3 rounded-lg bg-indigo-50 p-3 text-sm ring-1 ring-indigo-600/10">
      <div>
        <Person p={request.requester} /> asks to be a co-author, as <b>{basisLabel(request.basis)}</b>
        {request.basis === "relayed" && request.source ? ` (source: ${request.source})` : ""}.
      </div>
      {request.note && <p className="mt-1 text-stone-700">“{request.note}”</p>}
      <p className="mt-1 text-xs text-stone-600">
        Evidence:{" "}
        {request.evidence_quote ? `“${request.evidence_quote.text}” (${request.evidence_quote.at})` : request.evidence || "none given"}
      </p>
      {request.status !== "pending" && (
        <p className="mt-2 text-xs font-medium text-stone-700">
          {request.status === "accepted" ? "Accepted" : "Declined"} by {request.decided_by && <Person p={request.decided_by} />}
          {request.decided_at && ` · ${fmtDate(request.decided_at)}`}
          {request.decision_reason && ` · “${request.decision_reason}”`}
        </p>
      )}
    </div>
  )
}
