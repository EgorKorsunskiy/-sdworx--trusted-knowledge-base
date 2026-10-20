import { useEffect, useState } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api, type BasisChange, type ContributorsResponse, type Meme, type EntryDiff, type HistoryItem, type PullRequestBrief } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Dialog } from "@/components/ui/dialog"
import { TrustBadge } from "@/components/trust-badge"
import { TagList } from "@/components/tag-chip"
import { ScopeBadge } from "@/components/scope-badge"
import { DiffView } from "@/components/diff-view"
import { PRStatusBadge } from "@/components/pr-status-badge"
import { ContributorBody } from "@/components/contributor-body"
import { ContactsCard } from "@/components/contacts-card"
import { CoauthorDialog } from "@/components/meme-card"
import { basisLabel } from "@/components/basis-fields"

export function EntryPage() {
  const { publicId } = useParams<{ publicId: string }>()
  const navigate = useNavigate()
  const [openPRs, setOpenPRs] = useState<PullRequestBrief[]>([])
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
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [basisLog, setBasisLog] = useState<BasisChange[]>([])
  const [openVersion, setOpenVersion] = useState<number | null>(null)
  const [diffs, setDiffs] = useState<Record<number, EntryDiff>>({})
  const [diffError, setDiffError] = useState("")
  const [contrib, setContrib] = useState<ContributorsResponse | null>(null)
  const [highlightUser, setHighlightUser] = useState<number | null>(null)
  const [scrollTo, setScrollTo] = useState<number | null>(null)
  const [voteError, setVoteError] = useState("")
  const [coauthorMeme, setCoauthorMeme] = useState<Meme | null>(null)

  const load = () => {
    if (!publicId) return
    api.entries.get(publicId)
      .then((res: any) => setEntry(res))
      .catch((err: any) => setError(err.message || "Failed to load entry"))
    api.entries.history(publicId)
      .then(setHistory)
      .catch(() => {})
    api.entries.basisLog(publicId)
      .then(setBasisLog)
      .catch(() => setBasisLog([]))
    api.entries.contributors(publicId)
      .then(setContrib)
      .catch(() => setContrib(null))
    api.pullRequests.listForEntry(publicId, true)
      .then(setOpenPRs)
      .catch(() => {})
    api.votes.list(publicId)
      .then((res: any) => setVotes(res))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    setHistory([])
    setBasisLog([])
    setOpenPRs([])
    setDiffs({})
    setOpenVersion(null)
    setDiffError("")
    setContrib(null)
    setHighlightUser(null)
    load()
  }, [publicId])

  useEffect(() => {
    if (scrollTo == null) return
    const el = document.getElementById(`history-v${scrollTo}`)
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "start" })
    setScrollTo(null)
  }, [scrollTo, diffs, openVersion, history])

  const openDiff = async (n: number) => {
    if (!publicId) return
    setDiffError("")
    setOpenVersion(n)
    if (diffs[n]) return
    try {
      const d = await api.entries.diff(publicId, n)
      setDiffs((prev) => ({ ...prev, [n]: d }))
    } catch (err: any) {
      setDiffError(err.message || "Failed to load changes")
    }
  }

  const toggleDiff = async (n: number) => {
    if (openVersion === n) {
      setDiffError("")
      setOpenVersion(null)
      return
    }
    await openDiff(n)
  }

  const showChange = (n: number) => {
    openDiff(n)
    setScrollTo(n)
  }

  const submitVote = async () => {
    if (!publicId || !voteDate || !voteWhere) return
    setVoteError("")
    try {
      await api.votes.create(publicId, { used_at: voteDate, where_ref: voteWhere, is_correct: voteCorrect })
    } catch (err: any) {
      setVoteError(err.message || "Failed to report usage")
      return
    }
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

  const openCoauthorRequest = async () => {
    const id = entry?.origin?.meme_id
    if (!id) return
    try {
      setCoauthorMeme(await api.information.meme(id))
    } catch (err: any) {
      setError(err.message || "Failed to open the request")
    }
  }

  if (loading) return <div className="text-stone-500">Loading…</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!entry) return null

  const v = entry.current_version
  // The change log: versions and changes of authorship basis (which make no new version), newest first
  const changeLog = [
    ...history.map((h) => ({ kind: "version" as const, at: new Date(h.created_at).getTime(), h })),
    ...basisLog.map((change) => ({ kind: "basis" as const, at: new Date(change.created_at).getTime(), change })),
  ].sort((a, b) => b.at - a.at)
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
            {entry.origin && (
              <p className="mt-0.5 text-xs text-stone-500">
                From a {entry.origin.kind === "meeting" ? "meeting" : "group chat"},{" "}
                {new Date(entry.origin.date_from).toLocaleDateString()}
                {entry.origin.date_to ? ` – ${new Date(entry.origin.date_to).toLocaleDateString()}` : ""}
              </p>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate(`/entries/${entry.public_id}/suggest`)}>
            Suggest a change
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <TrustBadge status={v.status} />
          <Badge variant="success">{correctCount} correct</Badge>
          <Badge variant="danger">{incorrectCount} incorrect</Badge>
        </div>

        {!!entry.origin?.pending_requests && (
          <div className="mt-4 rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900 ring-1 ring-indigo-600/10">
            {entry.origin.pending_requests === 1
              ? "A colleague asks to be a co-author of this entry."
              : `${entry.origin.pending_requests} colleagues ask to be co-authors of this entry.`}{" "}
            <Link to="/information?tab=yours&section=coauthor" className="font-medium underline">Review the requests</Link>
          </div>
        )}

        {contrib && contrib.fragments.length > 0 ? (
          <ContributorBody data={contrib} highlightUserId={highlightUser} onShowChange={showChange} />
        ) : (
          <p className="mt-5 text-sm leading-6 text-stone-700 whitespace-pre-wrap">{v.body}</p>
        )}

        {v.justification && (
          <div className="mt-5 rounded-lg bg-stone-50 p-3 text-sm text-stone-600">
            <span className="font-medium">Justification:</span> {v.justification}
          </div>
        )}

        {entry.difference_note && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-600/20">
            <div className="text-xs font-medium text-amber-700">Note to verifiers</div>
            <p className="mt-1 whitespace-pre-wrap">{entry.difference_note}</p>
          </div>
        )}

        <dl className="mt-6 divide-y divide-stone-100 border-t border-stone-100 text-sm">
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Author</dt>
            <dd>
              <Link to={`/people/${entry.author.id}`} className="hover:underline">{entry.author.display_name}</Link>
              {" "}· {entry.author.reputation} rep
            </dd>
          </div>
          {v.edited_by && v.edited_by.id !== entry.author.id && (
            <div className="flex justify-between py-3">
              <dt className="text-stone-500">Last edited by</dt>
              <dd>
                <Link to={`/people/${v.edited_by.id}`} className="hover:underline">{v.edited_by.display_name}</Link>
              </dd>
            </div>
          )}
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Country · Department</dt>
            <dd>{entry.country} · {entry.department}</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Scope</dt>
            <dd><ScopeBadge entry={entry} /></dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Tags</dt>
            <dd className="max-w-[70%] justify-end">
              <TagList tags={entry.tags} className="justify-end" />
            </dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {contrib?.viewer_is_contributor ? (
            <span className="text-xs text-stone-500">
              Authors and contributors cannot report usage on their own entry.
            </span>
          ) : (
            <Button onClick={() => { setVoteError(""); setShowVoteModal(true) }}>Report usage</Button>
          )}
          <Button variant="secondary" onClick={copyReference}>{copied ? "Copied" : "Copy reference"}</Button>
          <Button variant="ghost" onClick={() => setShowOutdatedModal(true)}>Mark outdated</Button>
          {entry.origin?.is_participant && entry.origin.can_request_coauthorship && (
            <span title={entry.origin.request_blocked_reason ?? undefined}>
              <Button variant="secondary" disabled={!!entry.origin.request_blocked_reason} onClick={openCoauthorRequest}>
                Request co-authorship
              </Button>
            </span>
          )}
        </div>
        {entry.origin?.is_participant && entry.origin.can_request_coauthorship && entry.origin.request_blocked_reason && (
          <p className="mt-2 text-xs text-stone-500">{entry.origin.request_blocked_reason}</p>
        )}
      </div>

      {contrib && contrib.contributors.length > 0 && (
        <div className="mt-6 card">
          <h3 className="text-sm font-semibold">Contributors</h3>
          <p className="mt-1 text-xs text-stone-500">Click a contributor to highlight their text</p>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {contrib.contributors.map((c) => {
              const active = highlightUser === c.user.id
              return (
                <li key={c.user.id} className="flex items-center gap-2 py-2">
                  <Link to={`/people/${c.user.id}`} className="font-medium hover:underline">{c.user.display_name}</Link>
                  <Badge variant="neutral">{c.user.role_badge}</Badge>
                  <span className="text-xs text-stone-500">{c.user.reputation} rep</span>
                  {c.fragment_count === 0 ? (
                    <span className="ml-auto text-xs text-stone-500">Co-author, no lines of their own</span>
                  ) : (
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setHighlightUser(active ? null : c.user.id)}
                    className={`ml-auto rounded-md px-2 py-1 text-xs font-medium ring-1 ring-stone-300 hover:bg-stone-100 ${active ? "bg-amber-100" : "bg-white"}`}
                  >
                    {active ? "Highlighted" : `${c.fragment_count} ${c.fragment_count === 1 ? "line" : "lines"}`}
                  </button>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <ContactsCard
        publicId={entry.public_id}
        contacts={entry.contacts ?? []}
        mine={entry.my_contact}
        noResponsible={!!entry.no_responsible_contact}
        verifiers={entry.who_to_ask ?? []}
        onChanged={load}
      />

      {votes.length > 0 && (
        <div className="mt-6 card">
          <h3 className="text-sm font-semibold">Usage records</h3>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {votes.map((vote) => (
              <li key={vote.id} className="flex justify-between py-2">
                <span>
                  <Link to={`/people/${vote.user.id}`} className="hover:underline">{vote.user.display_name}</Link>
                  {" "}· {vote.where_ref} · {vote.used_at}</span>
                <Badge variant={vote.is_correct ? "success" : "danger"}>{vote.is_correct ? "Correct" : "Incorrect"}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      {openPRs.length > 0 && (
        <div className="mt-6 card">
          <h3 className="text-sm font-semibold">Open pull requests</h3>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {openPRs.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 py-2">
                <Link to={`/pull-requests/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                <PRStatusBadge status={p.status} />
                <Link to={`/people/${p.author.id}`} className="text-stone-600 hover:underline">{p.author.display_name}</Link>
                <span className="text-stone-500">{new Date(p.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-6 card">
          <h3 className="text-sm font-semibold">History</h3>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {changeLog.map((item) => {
              if (item.kind === "basis") return (
              <li key={`basis-${item.change.id}`} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="neutral">basis</Badge>
                  <Link to={`/people/${item.change.user.id}`} className="font-medium hover:underline">{item.change.user.display_name}</Link>
                  <span className="text-stone-500">{new Date(item.change.created_at).toLocaleDateString()}</span>
                  <span className="italic text-stone-600">
                    changed their basis from {item.change.old_basis ? basisLabel(item.change.old_basis) : "none"} to{" "}
                    {basisLabel(item.change.new_basis)}
                    {item.change.new_source ? ` (source: ${item.change.new_source})` : ""}
                  </span>
                  <span className="text-xs text-stone-500">no new version</span>
                </div>
              </li>
              )
              const h = item.h
              return (
              <li key={h.version_id} id={`history-v${h.version_number}`} className="scroll-mt-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="neutral">v{h.version_number}</Badge>
                  {h.is_current && <Badge variant="success">current</Badge>}
                  <Link to={`/people/${h.author.id}`} className="font-medium hover:underline">{h.author.display_name}</Link>
                  <span className="text-stone-500">{new Date(h.created_at).toLocaleDateString()}</span>
                  <span className="italic text-stone-600">{h.change_note}</span>
                  <TrustBadge status={h.status} verifierRole={h.verifier_role ?? undefined} />
                  <span className="text-xs text-stone-500">
                    +{h.summary.added} ~{h.summary.edited} −{h.summary.removed}
                  </span>
                  <button
                    type="button"
                    onClick={() => toggleDiff(h.version_number)}
                    className="ml-auto text-xs font-medium text-stone-600 hover:text-stone-900 hover:underline"
                  >
                    {openVersion === h.version_number ? "Hide" : "Show changes"}
                  </button>
                </div>
                {openVersion === h.version_number && (
                  <div className="mt-3">
                    {diffs[h.version_number] ? (
                      <DiffView diff={diffs[h.version_number]} />
                    ) : diffError ? (
                      <div className="text-red-600">{diffError}</div>
                    ) : (
                      <div className="text-stone-500">Loading…</div>
                    )}
                  </div>
                )}
              </li>
              )
            })}
          </ul>
        </div>
      )}

      {coauthorMeme && (
        <CoauthorDialog
          meme={coauthorMeme}
          onClose={() => setCoauthorMeme(null)}
          onDone={() => {
            setCoauthorMeme(null)
            load()
          }}
        />
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
          {voteError && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{voteError}</div>}
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
