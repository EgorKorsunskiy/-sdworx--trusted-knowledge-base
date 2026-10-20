import { Link } from "react-router-dom"
import type { Tag } from "@/lib/api"

/** A tag that opens Search with the tag pre-filled (FR-T3). The tag is part of the URL, so it can be shared. */
export function TagChip({ tag, className = "" }: { tag: Pick<Tag, "name" | "tag_type">; className?: string }) {
  const automatic = tag.tag_type === "automatic"
  return (
    <Link
      to={`/search?tag=${encodeURIComponent(tag.name)}`}
      title={automatic ? "Set by the system" : undefined}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ring-1 ring-inset transition-colors hover:bg-stone-100 ${
        automatic ? "bg-white text-stone-400 ring-stone-200" : "bg-stone-50 text-stone-700 ring-stone-300"
      } ${className}`}
    >
      {tag.name}
    </Link>
  )
}

/** Keyword tags first, then the automatic ones. */
export function TagList({ tags, className = "" }: { tags: Pick<Tag, "name" | "tag_type" | "id">[]; className?: string }) {
  if (!tags.length) return null
  const sorted = [...tags].sort((a, b) => Number(a.tag_type === "automatic") - Number(b.tag_type === "automatic"))
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {sorted.map((t) => (
        <TagChip key={t.id} tag={t} />
      ))}
    </div>
  )
}
