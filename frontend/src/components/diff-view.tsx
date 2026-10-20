import { useState } from "react"
import { Link } from "react-router-dom"
import type { AuthorRef, DiffFragment, EntryDiff, FieldDiff } from "@/lib/api"

function PersonLink({ user }: { user: AuthorRef }) {
  return (
    <Link to={`/people/${user.id}`} className="hover:underline font-medium">
      {user.display_name}
    </Link>
  )
}

const PR_STATUS_LABEL: Record<string, string> = {
  open: "Open",
  author_approved: "Author approved",
  verifier_approved: "Verifier approved",
  merged: "Merged",
  rejected: "Rejected",
}

function fmt(date: string) {
  return new Date(date).toLocaleDateString()
}

function FieldChange({ label, diff }: { label: string; diff: FieldDiff }) {
  if (!diff.changed) return null
  return (
    <div className="text-sm">
      <div className="text-xs font-medium text-stone-500">{label}</div>
      {diff.old ? <div className="rounded bg-red-50 px-2 py-1 text-red-800 line-through">{diff.old}</div> : null}
      {diff.new ? <div className="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-900">{diff.new}</div> : null}
    </div>
  )
}

function Fragment({ f }: { f: DiffFragment }) {
  const by = (verb: string) => (
    <div className="mt-0.5 text-xs text-stone-500">
      {verb} {f.author ? <PersonLink user={f.author} /> : null}
    </div>
  )
  if (f.type === "equal") return <div className="px-2 py-1 text-sm text-stone-500">{f.new_text}</div>
  if (f.type === "added")
    return (
      <div className="rounded bg-emerald-50 px-2 py-1 text-sm text-emerald-900">
        + {f.new_text}
        {by("added by")}
      </div>
    )
  if (f.type === "removed")
    return (
      <div className="rounded bg-red-50 px-2 py-1 text-sm text-red-800">
        <span className="line-through">{f.old_text}</span>
        {by("removed by")}
      </div>
    )
  const parts = f.parts ?? []
  return (
    <div className="rounded px-2 py-1 text-sm">
      <div className="rounded bg-red-50 px-2 py-1 text-red-800 line-through">
        {parts.length
          ? parts
              .filter((p) => p.op !== "insert")
              .map((p, i) => (
                <span key={i} className={p.op === "delete" ? "bg-red-200 font-medium" : undefined}>
                  {p.text}{" "}
                </span>
              ))
          : f.old_text}
      </div>
      <div className="mt-1 rounded bg-emerald-50 px-2 py-1 text-emerald-900">
        {parts.length
          ? parts
              .filter((p) => p.op !== "delete")
              .map((p, i) => (
                <span key={i} className={p.op === "insert" ? "bg-emerald-200 font-medium" : undefined}>
                  {p.text}{" "}
                </span>
              ))
          : f.new_text}
      </div>
      {by("edited by")}
    </div>
  )
}

const CONTEXT = 1 // unchanged fragments kept on each side of a change, like a GitHub diff

type Row = { kind: "fragment"; index: number } | { kind: "gap"; start: number; end: number }

/** Changed fragments with a little context; long unchanged stretches collapse into "N unchanged lines". */
function BodyFragments({ fragments }: { fragments: DiffFragment[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const visible = fragments.map(() => false)
  fragments.forEach((f, i) => {
    if (f.type === "equal") return
    for (let j = Math.max(0, i - CONTEXT); j <= Math.min(fragments.length - 1, i + CONTEXT); j++) visible[j] = true
  })

  const rows: Row[] = []
  for (let i = 0; i < fragments.length; ) {
    if (visible[i]) {
      rows.push({ kind: "fragment", index: i })
      i++
      continue
    }
    let end = i
    while (end + 1 < fragments.length && !visible[end + 1]) end++
    // A single hidden line is not worth a placeholder.
    if (end === i || expanded.has(i)) for (let j = i; j <= end; j++) rows.push({ kind: "fragment", index: j })
    else rows.push({ kind: "gap", start: i, end })
    i = end + 1
  }

  return (
    <div className="space-y-1">
      {rows.map((r) =>
        r.kind === "fragment" ? (
          <Fragment key={r.index} f={fragments[r.index]} />
        ) : (
          <button
            key={`gap-${r.start}`}
            type="button"
            onClick={() => setExpanded((prev) => new Set(prev).add(r.start))}
            className="w-full rounded bg-stone-50 px-2 py-1 text-left text-xs text-stone-500 hover:bg-stone-100"
          >
            ⋯ {r.end - r.start + 1} unchanged lines (click to show)
          </button>
        ),
      )}
    </div>
  )
}

/** Reusable diff display (version change log now, pull request proposals later). */
export function DiffView({ diff }: { diff: EntryDiff }) {
  const h = diff.header
  const s = diff.summary
  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-stone-50 p-3 text-sm">
        <div>
          <span className="font-medium">
            {h.kind === "created" ? "Created" : `v${h.from_version} → v${h.to_version ?? "proposed"}`}
          </span>{" "}
          by <PersonLink user={h.author} /> · {fmt(h.created_at)}
        </div>
        {h.change_note && <div className="mt-1 italic text-stone-600">{h.change_note}</div>}
        {h.kind === "proposal" && h.status && (
          <div className="mt-1 text-stone-500">{PR_STATUS_LABEL[h.status] ?? h.status}</div>
        )}
        {h.approvers.length > 0 && (
          <div className="mt-1 text-stone-600">
            Approved by{" "}
            {h.approvers.map((a, i) => (
              <span key={`${a.user.id}-${i}`}>
                {i > 0 && ", "}
                <PersonLink user={a.user} /> ({a.role}, {fmt(a.created_at)})
              </span>
            ))}
          </div>
        )}
      </div>

      <FieldChange label="Title" diff={diff.title} />
      <FieldChange label="Justification" diff={diff.justification} />

      <BodyFragments fragments={diff.body} />

      <div className="text-xs text-stone-500">
        {diff.has_changes ? `+${s.added} added · ~${s.edited} edited · −${s.removed} removed` : "No changes"}
      </div>
    </div>
  )
}
