import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { TrustBadge } from "@/components/trust-badge"

export function EntryPage() {
  const { publicId } = useParams<{ publicId: string }>()
  const [entry, setEntry] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!publicId) return
    api.entries.get(publicId)
      .then((res: any) => setEntry(res))
      .catch((err: any) => setError(err.message || "Failed to load entry"))
      .finally(() => setLoading(false))
  }, [publicId])

  const copyReference = () => {
    if (!entry) return
    navigator.clipboard.writeText(`${entry.public_id}@v${entry.current_version.version_number}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (loading) return <div className="text-stone-500">Loading…</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!entry) return null

  const v = entry.current_version

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
          </div>
          <Button variant="secondary" size="sm">
            Suggest a change
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <TrustBadge status={v.status} />
        </div>

        <p className="mt-5 text-sm leading-6 text-stone-700 whitespace-pre-wrap">{v.body}</p>

        {v.justification && (
          <div className="mt-5 rounded-lg bg-stone-50 p-3 text-sm text-stone-600">
            <span className="font-medium">Justification:</span> {v.justification}
          </div>
        )}

        <dl className="mt-6 divide-y divide-stone-100 border-t border-stone-100 text-sm">
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Author</dt>
            <dd>{entry.author.display_name} · {entry.author.reputation} rep</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Country · Department</dt>
            <dd>{entry.country} · {entry.department}</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Scope</dt>
            <dd className="capitalize">{entry.scope}</dd>
          </div>
          <div className="flex justify-between py-3">
            <dt className="text-stone-500">Tags</dt>
            <dd className="flex flex-wrap gap-1">
              {entry.tags.map((t: any) => (
                <Badge key={t.id} variant="neutral">{t.name}</Badge>
              ))}
            </dd>
          </div>
        </dl>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button>Report usage</Button>
          <Button variant="secondary" onClick={copyReference}>
            {copied ? "Copied" : "Copy reference"}
          </Button>
        </div>
      </div>
    </div>
  )
}
