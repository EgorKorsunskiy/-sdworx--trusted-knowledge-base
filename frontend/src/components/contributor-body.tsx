import { useState } from "react"
import { Link } from "react-router-dom"
import { clsx } from "clsx"
import type { BlameFragment, ContributorsResponse } from "@/lib/api"
import { Badge } from "@/components/ui/badge"

type Props = {
  data: ContributorsResponse
  highlightUserId: number | null
  onShowChange: (version: number) => void
}

export function ContributorBody({ data, highlightUserId, onShowChange }: Props) {
  const [selected, setSelected] = useState<number | null>(null)

  // A new block (paragraph) starts whenever the separator contains a newline.
  const blocks: BlameFragment[][] = []
  for (const f of data.fragments) {
    if (blocks.length === 0 || f.separator_before.includes("\n")) blocks.push([f])
    else blocks[blocks.length - 1].push(f)
  }

  const users = new Map(data.contributors.map((c) => [c.user.id, c.user]))
  const toggle = (i: number) => setSelected((cur) => (cur === i ? null : i))

  const renderPanel = (f: BlameFragment) => (
    <div
      role="region"
      aria-label="Who to ask"
      className="mt-2 rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm"
    >
      <ul className="divide-y divide-stone-200">
        {f.contributor_ids.map((id) => {
          const u = users.get(id)
          if (!u) return null
          return (
            <li key={id} className="flex flex-wrap items-center gap-2 py-1.5">
              <Link to={`/people/${u.id}`} className="font-medium hover:underline">{u.display_name}</Link>
              <Badge variant="neutral">{u.role_badge}</Badge>
              <span className="text-xs text-stone-500">{u.reputation} rep</span>
              <a href={`mailto:${u.email}`} className="ml-auto text-xs font-medium text-emerald-700 hover:underline">
                Contact
              </a>
            </li>
          )
        })}
      </ul>
      <p className="mt-2 text-xs text-stone-500">
        Introduced in v{f.introduced_in_version}
        {f.last_edited_in_version !== f.introduced_in_version && <> · Last edited in v{f.last_edited_in_version}</>}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onShowChange(f.last_edited_in_version)}
          className="rounded-md bg-white px-2 py-1 text-xs font-medium ring-1 ring-stone-300 hover:bg-stone-100"
        >
          See change in v{f.last_edited_in_version}
        </button>
        {f.introduced_in_version !== f.last_edited_in_version && (
          <button
            type="button"
            onClick={() => onShowChange(f.introduced_in_version)}
            className="rounded-md bg-white px-2 py-1 text-xs font-medium ring-1 ring-stone-300 hover:bg-stone-100"
          >
            See change in v{f.introduced_in_version}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div className="mt-5">
      {blocks.map((block, bi) => {
        const selectedFrag = block.find((f) => f.index === selected)
        return (
          <div key={bi}>
            <p className={clsx("text-sm leading-6 text-stone-700", bi > 0 && block[0].separator_before.includes("\n\n") && "mt-3")}>
              {block.map((f, k) => {
                const highlighted = highlightUserId != null && f.contributor_ids.includes(highlightUserId)
                return (
                  <span key={f.index}>
                    {k > 0 ? f.separator_before : ""}
                    <span
                      role="button"
                      tabIndex={0}
                      aria-pressed={selected === f.index}
                      onClick={() => toggle(f.index)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          if (e.key === " ") e.preventDefault()
                          toggle(f.index)
                        }
                      }}
                      className={clsx(
                        "cursor-pointer hover:bg-stone-100",
                        highlighted && "bg-amber-100",
                        selected === f.index && "rounded ring-2 ring-emerald-500",
                      )}
                    >
                      {f.text}
                    </span>
                  </span>
                )
              })}
            </p>
            {selectedFrag && renderPanel(selectedFrag)}
          </div>
        )
      })}
    </div>
  )
}
