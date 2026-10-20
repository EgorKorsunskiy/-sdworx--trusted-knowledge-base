import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { Search, SlidersHorizontal, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"
import { TrustBadge } from "@/components/trust-badge"
import { TagList } from "@/components/tag-chip"
import { api, normalizeTag, SEARCH_DATE_KEYS, SEARCH_MULTI_KEYS, type SearchFacets, type TagSuggestion } from "@/lib/api"

type Option = { value: string; label: string }
type MultiKey = (typeof SEARCH_MULTI_KEYS)[number]

const GROUP_TITLES: Record<MultiKey, string> = {
  country: "Country",
  department: "Department",
  category: "Category",
  status: "Status",
  scope: "Scope",
  verifier_role: "Verifier role",
  author: "Author",
  team: "Team",
  tag: "Tag",
}

const DATE_LABELS: Record<(typeof SEARCH_DATE_KEYS)[number], string> = {
  updated_from: "Updated from",
  updated_to: "Updated until",
}

function optionsFor(key: MultiKey, f: SearchFacets | null): Option[] {
  if (!f) return []
  const plain = (xs: string[]) => xs.map((x) => ({ value: x, label: x }))
  const named = (xs: { id: number; name: string }[]) => xs.map((x) => ({ value: String(x.id), label: x.name }))
  switch (key) {
    case "country": return plain(f.countries)
    case "department": return plain(f.departments)
    case "category": return plain(f.categories)
    case "status": return f.statuses
    case "scope": return f.scopes
    case "verifier_role": return plain(f.verifier_roles)
    case "author": return named(f.authors)
    case "team": return named(f.teams)
    case "tag": return [] // tags are picked with suggestions, see TagFilter
  }
}

/** Pick tags with suggestions of existing ones (FR-T2); selected tags are the `tag` URL values. */
function TagFilter({ selected, onToggle }: { selected: string[]; onToggle: (name: string) => void }) {
  const [text, setText] = useState("")
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([])

  useEffect(() => {
    const q = text.trim()
    if (!q) {
      setSuggestions([])
      return
    }
    const timer = setTimeout(() => {
      api.tags.list(q, { limit: 8 }).then(setSuggestions).catch(() => setSuggestions([]))
    }, 200)
    return () => clearTimeout(timer)
  }, [text])

  const add = (name: string) => {
    const normalized = normalizeTag(name)
    if (normalized && !selected.includes(normalized)) onToggle(normalized)
    setText("")
    setSuggestions([])
  }

  return (
    <div>
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault()
            add(suggestions.find((s) => s.name === normalizeTag(text))?.name ?? text)
          }
        }}
        placeholder="Find a tag…"
        aria-label="Find a tag"
        className="mt-1.5"
      />
      {suggestions.length > 0 && (
        <ul className="mt-1 max-h-40 overflow-y-auto rounded-lg bg-white text-sm ring-1 ring-stone-200">
          {suggestions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => add(s.name)}
                className="flex w-full items-center justify-between px-3 py-1.5 text-left hover:bg-stone-50"
              >
                <span>{s.name}</span>
                <span className="text-xs text-stone-400">{s.entry_count}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {selected.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => onToggle(name)}
            className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-700 hover:bg-stone-200"
          >
            {name} <X className="h-3 w-3" />
          </button>
        ))}
      </div>
    </div>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get("q") ?? "")
  const [facets, setFacets] = useState<SearchFacets | null>(null)
  const [results, setResults] = useState<any[]>([])
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState("")

  const paramString = params.toString()

  const activeCount = useMemo(() => {
    let n = 0
    for (const k of SEARCH_MULTI_KEYS) n += params.getAll(k).length
    for (const k of SEARCH_DATE_KEYS) if (params.get(k)) n += 1
    return n
  }, [paramString])

  const [panelOpen, setPanelOpen] = useState(activeCount > 0)

  useEffect(() => {
    api.searchFacets().then(setFacets).catch(() => {})
  }, [])

  // The URL is the source of truth: back/forward and shared links restore query and filters.
  useEffect(() => {
    setQuery(params.get("q") ?? "")
    setError("")
    api.search(params)
      .then((res) => setResults(res))
      .catch((err: unknown) => {
        setResults([])
        setError(err instanceof Error ? err.message : "Search failed")
      })
      .finally(() => setSearched(true))
  }, [paramString])

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next)
  }

  const submitQuery = () =>
    update((next) => {
      const q = query.trim()
      if (q) next.set("q", q)
      else next.delete("q")
    })

  const toggleValue = (key: MultiKey, value: string) =>
    update((next) => {
      const values = next.getAll(key)
      next.delete(key)
      const updated = values.includes(value) ? values.filter((v) => v !== value) : [...values, value]
      updated.forEach((v) => next.append(key, v))
    })

  const setDate = (key: (typeof SEARCH_DATE_KEYS)[number], value: string) =>
    update((next) => {
      if (value) next.set(key, value)
      else next.delete(key)
    })

  const clearAll = () =>
    update((next) => {
      for (const k of SEARCH_MULTI_KEYS) next.delete(k)
      for (const k of SEARCH_DATE_KEYS) next.delete(k)
    })

  const labelFor = (key: MultiKey, value: string) =>
    optionsFor(key, facets).find((o) => o.value === value)?.label ?? value

  const chips: { id: string; text: string; remove: () => void }[] = []
  for (const key of SEARCH_MULTI_KEYS) {
    for (const value of params.getAll(key)) {
      chips.push({
        id: `${key}:${value}`,
        text: `${GROUP_TITLES[key]}: ${labelFor(key, value)}`,
        remove: () => toggleValue(key, value),
      })
    }
  }
  for (const key of SEARCH_DATE_KEYS) {
    const value = params.get(key)
    if (value) chips.push({ id: key, text: `${DATE_LABELS[key]}: ${value}`, remove: () => setDate(key, "") })
  }

  return (
    <div>
      <PageHeader title="Search" subtitle="Everything your team knows, with a clear level of trust." />
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-5 w-5 text-stone-400" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitQuery()}
            placeholder="Search entries…"
            className="pl-10"
          />
        </div>
        <Button variant="secondary" onClick={() => setPanelOpen((o) => !o)} aria-expanded={panelOpen}>
          <SlidersHorizontal className="h-4 w-4" />
          Filters
          {activeCount > 0 && (
            <span className="rounded-full bg-stone-900 px-1.5 py-0.5 text-[10px] font-semibold text-white">
              {activeCount}
            </span>
          )}
        </Button>
        <Button onClick={submitQuery}>Search</Button>
      </div>

      {panelOpen && (
        <div className="mt-3 card">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {SEARCH_MULTI_KEYS.map((key) => {
              const options = optionsFor(key, facets)
              const selected = params.getAll(key)
              if (key === "tag") {
                return (
                  <fieldset key={key}>
                    <legend className="label">{GROUP_TITLES[key]}</legend>
                    <TagFilter selected={selected} onToggle={(name) => toggleValue("tag", name)} />
                  </fieldset>
                )
              }
              return (
                <fieldset key={key}>
                  <legend className="label">{GROUP_TITLES[key]}</legend>
                  <div className="mt-1.5 max-h-36 space-y-1 overflow-y-auto pr-1">
                    {options.length === 0 && <p className="text-xs text-stone-400">No options</p>}
                    {options.map((o) => (
                      <label key={o.value} className="flex items-center gap-2 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={selected.includes(o.value)}
                          onChange={() => toggleValue(key, o.value)}
                          className="h-4 w-4 rounded border-stone-300 accent-stone-900"
                        />
                        {o.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              )
            })}
            <fieldset>
              <legend className="label">Last updated</legend>
              <div className="mt-1.5 space-y-2">
                {SEARCH_DATE_KEYS.map((key) => (
                  <label key={key} className="flex items-center gap-2 text-sm text-stone-600">
                    <span className="w-24 shrink-0">{key === "updated_from" ? "From" : "Until"}</span>
                    <Input
                      type="date"
                      value={params.get(key) ?? ""}
                      onChange={(e) => setDate(key, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
      )}

      {(chips.length > 0 || searched) && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          {chips.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200"
            >
              {c.text}
              <button
                type="button"
                onClick={c.remove}
                aria-label={`Remove filter ${c.text}`}
                className="text-stone-400 hover:text-stone-900"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {chips.length > 0 && (
            <button type="button" onClick={clearAll} className="text-stone-500 underline hover:text-stone-900">
              Clear all
            </button>
          )}
          {searched && (
            <span className="ml-auto text-stone-500">
              {results.length} {results.length === 1 ? "result" : "results"}
            </span>
          )}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
          {error}
        </div>
      )}
      <div className="mt-4 list-panel">
        {results.length === 0 && searched ? (
          <div className="p-8 text-center text-sm text-stone-500">No results.</div>
        ) : (
          results.map((entry) => (
            // The tags are links too, so the row cannot be one big link (no nested anchors).
            <div key={entry.public_id} className="p-5 hover:bg-stone-50">
              <Link to={`/entries/${entry.public_id}`} className="block">
                <div className="flex items-start justify-between gap-4">
                  <h3 className="font-medium">{entry.current_version.title}</h3>
                  <span className="shrink-0 text-xs text-stone-400">{entry.public_id}</span>
                </div>
                <p className="mt-1 text-sm text-stone-500 line-clamp-2">{entry.current_version.body}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <TrustBadge status={entry.current_version.status} />
                  <span className="text-stone-400">{entry.country} · {entry.department} · {entry.author.display_name}</span>
                </div>
              </Link>
              <TagList tags={entry.tags ?? []} className="mt-2" />
            </div>
          ))
        )}
      </div>
    </div>
  )
}
