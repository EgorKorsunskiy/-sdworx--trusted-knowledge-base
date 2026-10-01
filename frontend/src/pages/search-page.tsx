import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"
import { TrustBadge } from "@/components/trust-badge"
import { api } from "@/lib/api"

export function SearchPage() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<any[]>([])
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState("")

  const doSearch = async () => {
    setSearched(true)
    setError("")
    try {
      setResults(await api.search(query))
    } catch (err: unknown) {
      setResults([])
      setError(err instanceof Error ? err.message : "Search failed")
    }
  }

  useEffect(() => {
    doSearch()
  }, [])

  return (
    <div>
      <PageHeader title="Search" subtitle="Everything your team knows, with a clear level of trust." />
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-5 w-5 text-stone-400" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doSearch()}
            placeholder="Search entries…"
            className="pl-10"
          />
        </div>
        <Button onClick={doSearch}>Search</Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200">Country: Belgium</span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200">Department: Payroll</span>
      </div>
      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
          {error}
        </div>
      )}
      <div className="mt-6 list-panel">
        {results.length === 0 && searched ? (
          <div className="p-8 text-center text-sm text-stone-500">No results.</div>
        ) : (
          results.map((entry) => (
            <Link
              key={entry.public_id}
              to={`/entries/${entry.public_id}`}
              className="block p-5 hover:bg-stone-50"
            >
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
          ))
        )}
      </div>
    </div>
  )
}
