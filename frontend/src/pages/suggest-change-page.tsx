import { useEffect, useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api, type Entry } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PageHeader } from "@/components/page-header"

type Prefill = { title?: string; body?: string; justification?: string }

export function SuggestChangePage() {
  const { publicId } = useParams<{ publicId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const state = (location.state ?? {}) as { prefill?: Prefill; fromDuplicate?: boolean }

  const [entry, setEntry] = useState<Entry | null>(null)
  const [loadError, setLoadError] = useState("")
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [justification, setJustification] = useState("")
  const [changeNote, setChangeNote] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!publicId) return
    api.entries
      .get(publicId)
      .then((e) => {
        setEntry(e)
        const p = state.prefill
        setTitle(p?.title ?? e.current_version.title)
        setBody(p?.body ?? e.current_version.body)
        setJustification(p?.justification ?? e.current_version.justification ?? "")
      })
      .catch((err: any) => setLoadError(err.message || "Failed to load entry"))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publicId])

  if (loadError) return <div className="text-red-600">{loadError}</div>
  if (!entry || !publicId) return <div className="text-stone-500">Loading…</div>

  const cur = entry.current_version
  const changed =
    title.trim() !== cur.title.trim() ||
    body.trim() !== (cur.body ?? "").trim() ||
    justification.trim() !== (cur.justification ?? "").trim()
  const canSubmit = changed && changeNote.trim().length > 0 && !saving

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSaving(true)
    setError("")
    try {
      const pr = await api.pullRequests.create(publicId, {
        proposed_title: title.trim(),
        proposed_body: body.trim(),
        proposed_justification: justification.trim() || undefined,
        change_note: changeNote.trim(),
      })
      navigate(`/pull-requests/${pr.id}`)
    } catch (err: any) {
      setError(err.message || "Failed to create pull request")
      setSaving(false)
    }
  }

  return (
    <div>
      <Link to={`/entries/${publicId}`} className="inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-900">
        <ArrowLeft className="h-4 w-4" /> Back to {publicId}
      </Link>
      <div className="mt-4">
        <PageHeader
          title="Suggest a change"
          subtitle={`${publicId} · currently v${cur.version_number}. If the entry author approves, it becomes a new Unverified version.`}
        />
      </div>
      {state.fromDuplicate && (
        <div className="mb-6 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-600/20">
          Your draft was copied here from the duplicate warning. Review it against the existing entry and explain what
          you change.
        </div>
      )}
      <form onSubmit={submit} className="card space-y-5">
        {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{error}</div>}
        <div>
          <label className="label">Title</label>
          <Input className="mt-1.5" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="label">Content</label>
          <Textarea rows={8} className="mt-1.5" value={body} onChange={(e) => setBody(e.target.value)} />
        </div>
        <div>
          <label className="label">Justification / source</label>
          <Textarea rows={2} className="mt-1.5" value={justification} onChange={(e) => setJustification(e.target.value)} />
        </div>
        <div>
          <label className="label">Change note (required)</label>
          <Input
            className="mt-1.5"
            maxLength={500}
            value={changeNote}
            onChange={(e) => setChangeNote(e.target.value)}
            placeholder="What did you change and why?"
          />
        </div>
        <div className="flex items-center justify-end gap-3 pt-2">
          {!changed && <span className="text-xs text-stone-500">Change something to enable submit.</span>}
          <Button type="submit" disabled={!canSubmit}>
            {saving ? "Submitting…" : "Create pull request"}
          </Button>
        </div>
      </form>
    </div>
  )
}
