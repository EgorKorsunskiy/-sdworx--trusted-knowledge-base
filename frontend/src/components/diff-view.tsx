import { Link } from "react-router-dom"
import type { AuthorRef, DiffFragment, EntryDiff, FieldDiff } from "@/lib/api"

function PersonLink({ user }: { user: AuthorRef }) {
  return (
    <Link to={`/people/${user.id}`} className="hover:underline font-medium">
      {user.display_name}
    </Link>
  )
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
        {h.kind === "proposal" ? (
          <div className="mt-1 text-stone-500">Pending</div>
        ) : (
          h.approvers.length > 0 && (
            <div className="mt-1 text-stone-600">
              Approved by{" "}
              {h.approvers.map((a, i) => (
                <span key={`${a.user.id}-${i}`}>
                  {i > 0 && ", "}
                  <PersonLink user={a.user} /> ({a.role}, {fmt(a.created_at)})
                </span>
              ))}
            </div>
          )
        )}
      </div>

      <FieldChange label="Title" diff={diff.title} />
      <FieldChange label="Justification" diff={diff.justification} />

      <div className="space-y-1">
        {diff.body.map((f, i) => (
          <Fragment key={i} f={f} />
        ))}
      </div>

      <div className="text-xs text-stone-500">
        {diff.has_changes ? `+${s.added} added · ~${s.edited} edited · −${s.removed} removed` : "No changes"}
      </div>
    </div>
  )
}
