import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { api, type Meme, type OverviewItem } from "@/lib/api"
import { MemeCard } from "@/components/meme-card"

/** Full details of one item of the Information overview: tags, scope, all candidates, quotes and history. */
export function InformationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [meme, setMeme] = useState<Meme | null>(null)
  const [error, setError] = useState("")

  const load = useCallback(() => {
    if (!id) return
    api.information
      .meme(Number(id))
      .then((m) => {
        setMeme(m)
        setError("")
      })
      .catch((e) => setError(e.message || "Not found"))
  }, [id])

  useEffect(() => {
    setMeme(null)
    load()
  }, [load])

  const back = (
    <button
      type="button"
      onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/information"))}
      className="inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-900"
    >
      <ArrowLeft className="h-4 w-4" /> Back to the Information overview
    </button>
  )

  if (error) {
    return (
      <div>
        {back}
        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{error}</div>
        <Link to="/information" className="mt-3 inline-block text-sm underline">Go to the overview</Link>
      </div>
    )
  }
  if (!meme) return <div className="text-stone-500">Loading…</div>

  const item: OverviewItem = meme.my_suggestion_id
    ? { type: "suggestion", id: meme.my_suggestion_id, meme }
    : { type: "meme", id: meme.id, meme }

  return (
    <div>
      {back}
      <div className="mt-4 card p-0">
        <MemeCard item={item} variant="detail" onChanged={load} />
      </div>
    </div>
  )
}
