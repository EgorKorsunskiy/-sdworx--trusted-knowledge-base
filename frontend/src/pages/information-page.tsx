import { useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ChevronLeft, ChevronRight, MessageCircle, Users } from "lucide-react"
import { api, type OverviewCounts, type OverviewPage, type OverviewSection } from "@/lib/api"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { MemeCard } from "@/components/meme-card"

const SECTIONS: { id: OverviewSection; label: string }[] = [
  { id: "to_decide", label: "To decide" },
  { id: "postponed", label: "Postponed" },
  { id: "decided", label: "Decided" },
  { id: "coauthor", label: "Co-author requests" },
]
const KINDS = [
  { id: "meeting", label: "Meetings", icon: Users },
  { id: "chat", label: "Group chats", icon: MessageCircle },
]
const EMPTY: Record<OverviewSection, string> = {
  to_decide: "Nothing to decide right now.",
  postponed: "No postponed suggestions.",
  decided: "No decisions yet.",
  coauthor: "No co-author requests.",
}

/**
 * Information overview (AI parser): what the bots extracted from the user's meetings and group chats.
 * Yours: the user's own suggestions (approve, reject, postpone) and co-author requests. Others: what the other
 * participants decided about their own suggestions. Click an item for the details. Tab, section, filters and page live in the URL (FR-MS10).
 */
export function InformationPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get("tab") === "others" ? "others" : "yours"
  const rawSection = params.get("section") as OverviewSection | null
  const section: OverviewSection = SECTIONS.some((s) => s.id === rawSection) ? (rawSection as OverviewSection) : "to_decide"
  const kinds = params.getAll("kind")
  const page = Math.max(Number(params.get("page") ?? 1) || 1, 1)
  // A notification link points at one item: find its tab, section and page once, then show and open it
  const focus = ["suggestion", "meme", "request"].find((k) => params.get(k))
  const focusId = focus ? Number(params.get(focus)) : null

  const [data, setData] = useState<OverviewPage | null>(null)
  const [counts, setCounts] = useState<OverviewCounts | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const located = useRef<string | null>(null)

  const paramString = params.toString()

  const load = useCallback(() => {
    const q = new URLSearchParams()
    q.set("tab", tab)
    q.set("section", section)
    q.set("page", String(page))
    kinds.forEach((k) => q.append("kind", k))
    setError("")
    return api.information
      .list(q)
      .then((res) => {
        setData(res)
        setCounts(res.counts)
      })
      .catch((e) => setError(e.message || "Failed to load"))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, section, page, kinds.join(",")])

  useEffect(() => {
    // Resolve a deep link once per link
    if (focus && focusId && located.current !== `${focus}:${focusId}`) {
      located.current = `${focus}:${focusId}`
      api.information
        .locate({ [focus]: String(focusId) })
        .then((loc) => {
          const next = new URLSearchParams(params)
          next.set("tab", loc.tab)
          if (loc.section) next.set("section", loc.section)
          else next.delete("section")
          next.set("page", String(loc.page))
          setParams(next, { replace: true })
        })
        .catch(() => load())
      return
    }
    load()
  }, [paramString, load])

  // Keep the section counts of the Yours tab current from the Others tab too
  useEffect(() => {
    if (tab === "others" && !counts) api.information.summary().then((c) => setCounts(c)).catch(() => {})
  }, [tab, counts])

  useEffect(() => {
    if (!data || !focusId) return
    const el = document.getElementById(`item-${focus === "meme" ? "meme" : focus === "request" ? "coauthor_request" : "suggestion"}-${focusId}`)
    el?.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [data, focus, focusId])

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next)
  }
  const setTab = (t: "yours" | "others") =>
    update((n) => {
      n.set("tab", t)
      n.delete("section")
      n.delete("page")
      n.delete("suggestion"); n.delete("meme"); n.delete("request")
    })
  const setSection = (s: OverviewSection) =>
    update((n) => {
      n.set("section", s)
      n.delete("page")
      n.delete("suggestion"); n.delete("meme"); n.delete("request")
    })
  const toggleKind = (k: string) =>
    update((n) => {
      const have = n.getAll("kind")
      n.delete("kind")
      ;(have.includes(k) ? have.filter((x) => x !== k) : [...have, k]).forEach((x) => n.append("kind", x))
      n.delete("page")
    })
  const setPage = (p: number) => update((n) => n.set("page", String(p)))

  const pages = data ? Math.max(Math.ceil(data.total / data.page_size), 1) : 1
  const yoursOpen = counts ? counts.to_decide + counts.coauthor : 0

  return (
    <div>
      <PageHeader
        title="Information overview"
        subtitle="Knowledge the bots found in your meetings and group chats. Every person decides on their own suggestions."
      />

      <div role="tablist" className="flex gap-1 border-b border-stone-200">
        {([
          { id: "yours", label: "Yours", badge: yoursOpen },
          { id: "others", label: "Others", badge: 0 },
        ] as const).map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium ${
              tab === t.id ? "border-stone-900 text-stone-900" : "border-transparent text-stone-500 hover:text-stone-900"
            }`}
          >
            {t.label}
            {t.badge > 0 && (
              <span className="rounded-full bg-stone-900 px-1.5 py-0.5 text-[10px] font-semibold text-white">{t.badge}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        {tab === "yours" ? (
          <div role="tablist" aria-label="Sections" className="flex flex-wrap gap-2">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                role="tab"
                type="button"
                aria-selected={section === s.id}
                onClick={() => setSection(s.id)}
                className={`rounded-full px-3 py-1 text-sm ring-1 ring-inset ${
                  section === s.id ? "bg-stone-900 text-white ring-stone-900" : "bg-white text-stone-700 ring-stone-200 hover:bg-stone-50"
                }`}
              >
                {s.label}
                {counts && <span className={`ml-1.5 text-xs ${section === s.id ? "text-stone-300" : "text-stone-400"}`}>{counts[s.id]}</span>}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-stone-500">
            What the other participants decided about their own suggestions. Open an item to see who decided what.
          </p>
        )}
        <div className="flex items-center gap-2" role="group" aria-label="Filter by source">
          <span className="text-xs text-stone-500">Show</span>
          {KINDS.map((k) => {
            const on = kinds.includes(k.id)
            return (
              <button
                key={k.id}
                type="button"
                aria-pressed={on}
                onClick={() => toggleKind(k.id)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ring-inset transition-colors ${
                  on ? "bg-stone-900 text-white ring-stone-900" : "bg-white text-stone-700 ring-stone-200 hover:bg-stone-50"
                }`}
              >
                <k.icon className="h-3.5 w-3.5" />
                {k.label}
              </button>
            )
          })}
          {kinds.length > 0 && (
            <button type="button" onClick={() => update((n) => { n.delete("kind"); n.delete("page") })}
              className="text-xs text-stone-500 underline hover:text-stone-900">
              Clear
            </button>
          )}
        </div>
      </div>

      {error && <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{error}</div>}

      <div className="mt-4 list-panel divide-y divide-stone-100">
        {loading ? (
          <div className="p-8 text-center text-sm text-stone-500">Loading…</div>
        ) : !data || data.items.length === 0 ? (
          <div className="p-8 text-center text-sm text-stone-500">
            {tab === "yours" ? EMPTY[section] : "Nothing from other participants yet."}
          </div>
        ) : (
          data.items.map((item) => (
            <MemeCard
              key={`${item.type}-${item.id}`}
              item={item}
              highlight={focusId === item.id && ((focus === "suggestion" && item.type === "suggestion") ||
                (focus === "meme" && item.type === "meme") || (focus === "request" && item.type === "coauthor_request"))}
              onChanged={load}
            />
          ))
        )}
      </div>

      {data && data.total > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-stone-600">
          <span>
            {data.total} {data.total === 1 ? "item" : "items"} · page {data.page} of {pages}
          </span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>
            <Button size="sm" variant="secondary" disabled={data.page >= pages} onClick={() => setPage(data.page + 1)}>
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
