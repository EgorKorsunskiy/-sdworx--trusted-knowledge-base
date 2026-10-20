import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { api, type ResponsibilityItem, type Responsibilities } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { TrustBadge } from "@/components/trust-badge"
import { BasisFields, basisIsValid, emptyBasis, type BasisValue } from "@/components/basis-fields"

const ROLE_LABEL = { author: "Author", co_author: "Co-author", contributor: "Contributor" } as const

function AreaRow({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm">
      <span className="w-28 shrink-0 text-xs text-stone-500">{label}</span>
      {values.map((v) => (
        <Badge key={v} variant="neutral">{v}</Badge>
      ))}
    </div>
  )
}

/**
 * The Responsibilities tab of a profile (FR-K8 to FR-K10): areas of responsibility first, then the entries the
 * person authored or co-authored, as Responsible and as Relayed (with the source they named).
 */
export function ResponsibilitiesTab({ userId, isSelf }: { userId: number | string; isSelf: boolean }) {
  const [data, setData] = useState<Responsibilities | null>(null)
  const [error, setError] = useState("")
  const [picked, setPicked] = useState<string[]>([])
  const [dialog, setDialog] = useState(false)
  const [value, setValue] = useState<BasisValue>(emptyBasis)
  const [saveError, setSaveError] = useState("")

  const load = () =>
    api.people
      .responsibilities(userId)
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load"))

  useEffect(() => {
    setData(null)
    setPicked([])
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId])

  if (error) return <div className="text-red-600">{error}</div>
  if (!data) return <div className="text-stone-500">Loading…</div>

  const { areas } = data
  const hasAreas = Object.values(areas).some((v) => v.length > 0)
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  const apply = async () => {
    if (!basisIsValid(value) || !value.basis) return
    setSaveError("")
    try {
      await api.people.changeMyBasis({
        public_ids: picked,
        basis: value.basis,
        source: value.source.trim() || undefined,
      })
      setDialog(false)
      setPicked([])
      setValue(emptyBasis)
      await load()
    } catch (e: any) {
      setSaveError(e.message || "Could not save")
    }
  }

  const group = (title: string, hint: string, items: ResponsibilityItem[]) => (
    <div className="list-panel">
      <h3 className="px-5 pt-4 text-sm font-semibold">{title}</h3>
      <p className="px-5 text-xs text-stone-500">{hint}</p>
      {items.length === 0 ? (
        <div className="p-5 text-sm text-stone-500">None</div>
      ) : (
        <ul className="mt-2 divide-y divide-stone-100">
          {items.map((i) => (
            <li key={i.public_id} className="flex items-start gap-3 px-5 py-3 text-sm">
              {isSelf && (
                <input
                  type="checkbox"
                  aria-label={`Select ${i.title}`}
                  checked={picked.includes(i.public_id)}
                  onChange={() => toggle(i.public_id)}
                  className="mt-1 h-4 w-4 rounded border-stone-300 accent-stone-900"
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/entries/${i.public_id}`} className="font-medium hover:underline">{i.title}</Link>
                  <span className="text-xs text-stone-400">{i.public_id}</span>
                  <TrustBadge status={i.status} />
                  <Badge variant="neutral">{ROLE_LABEL[i.role]}</Badge>
                </div>
                {i.basis === "relayed" && i.source && (
                  <div className="mt-0.5 text-xs text-stone-600">Source: {i.source}</div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="card">
        <h3 className="text-sm font-semibold">Areas of responsibility</h3>
        {hasAreas ? (
          <div className="mt-3 space-y-2">
            <AreaRow label="Categories" values={areas.categories} />
            <AreaRow label="Countries" values={areas.countries} />
            <AreaRow label="Scopes" values={areas.scopes} />
            <AreaRow label="Companies" values={areas.companies} />
            <AreaRow label="Client projects" values={areas.client_projects} />
            <div className="flex flex-wrap items-center gap-1.5 text-sm">
              {areas.tags.length > 0 && <span className="w-28 shrink-0 text-xs text-stone-500">Tags</span>}
              {areas.tags.map((t) => (
                <Link
                  key={t.id}
                  to={`/search?tag=${encodeURIComponent(t.name)}`}
                  className="rounded-full bg-stone-50 px-2 py-0.5 text-xs text-stone-700 ring-1 ring-inset ring-stone-300 hover:bg-stone-100"
                >
                  {t.name}
                </Link>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-stone-500">No areas of responsibility yet.</p>
        )}
      </div>

      {isSelf && picked.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-xl bg-stone-900 px-4 py-3 text-sm text-white">
          <span>{picked.length} selected</span>
          <Button size="sm" variant="secondary" onClick={() => { setSaveError(""); setDialog(true) }}>
            Change my basis
          </Button>
        </div>
      )}

      {group("Responsible", "Entries this person answers questions about.", data.responsible)}
      {group("Relayed", "Entries this person added from a source.", data.relayed)}

      <Dialog open={dialog} onClose={() => setDialog(false)} title={`Change basis for ${picked.length} ${picked.length === 1 ? "entry" : "entries"}`}>
        <div className="space-y-4">
          <p className="text-sm text-stone-600">
            For example after moving to another team, hand over responsibility by switching to Relayed and naming the
            team handbook. Each change is recorded in the entry's change log.
          </p>
          {saveError && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{saveError}</div>}
          <BasisFields value={value} onChange={setValue} idPrefix="bulk-basis" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDialog(false)}>Cancel</Button>
            <Button onClick={apply} disabled={!basisIsValid(value)}>Apply</Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
