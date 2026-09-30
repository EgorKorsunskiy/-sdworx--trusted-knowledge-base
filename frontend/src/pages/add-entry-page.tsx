import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select } from "@/components/ui/select"
import { PageHeader } from "@/components/page-header"

export function AddEntryPage() {
  const navigate = useNavigate()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState("")
  const [categories, setCategories] = useState<any[]>([])
  const [categoryId, setCategoryId] = useState(1)
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [similar, setSimilar] = useState<any[]>([])

  useEffect(() => {
    api.categories().then((cats: any) => {
      setCategories(cats)
      const def = cats.find((c: any) => c.is_default) ?? cats[0]
      if (def) setCategoryId(def.id)
    })
  }, [])

  useEffect(() => {
    if (title.length < 4 || body.length < 10) {
      setSimilar([])
      return
    }
    const t = setTimeout(() => {
      api.similar(title, body).then(setSimilar).catch(() => {})
    }, 500)
    return () => clearTimeout(t)
  }, [title, body])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setSaving(true)
    setError("")
    const form = new FormData(e.currentTarget)
    try {
      const data = {
        title,
        body,
        justification: (form.get("justification") as string) || undefined,
        country: form.get("country") as string,
        scope: form.get("scope") as string,
        category_id: categoryId,
        keywords,
      }
      const entry: any = await api.entries.create(data)
      navigate(`/entries/${entry.public_id}`)
    } catch (err: any) {
      setError(err.message || "Failed to save entry")
      setSaving(false)
    }
  }

  const addKeyword = () => {
    const value = keywordInput.trim().toLowerCase()
    if (value && !keywords.includes(value)) setKeywords([...keywords, value])
    setKeywordInput("")
  }

  return (
    <div>
      <PageHeader title="Add information" subtitle="New entries start as unverified and go to verifiers in scope." />
      {similar.length > 0 && (
        <div className="mb-6 rounded-xl bg-amber-50 p-4 ring-1 ring-amber-600/20">
          <h3 className="text-sm font-medium text-amber-900">Similar information already exists</h3>
          <ul className="mt-2 space-y-1 text-sm text-amber-800">
            {similar.map((s) => (
              <li key={s.public_id}>
                <Link className="underline" to={`/entries/${s.public_id}`}>{s.public_id}</Link> · {s.title} · {Math.round(s.score * 100)}% similar
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-700">You can still submit, but consider suggesting a change to the existing entry.</p>
        </div>
      )}
      <form onSubmit={handleSubmit} className="card space-y-5">
        {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{error}</div>}
        <div>
          <label className="label">Title</label>
          <Input name="title" required className="mt-1.5" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="label">Content</label>
          <Textarea name="body" rows={6} required className="mt-1.5" value={body} onChange={(e) => setBody(e.target.value)} />
        </div>
        <div>
          <label className="label">Justification / source</label>
          <Textarea name="justification" rows={2} className="mt-1.5" />
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="label">Country</label>
            <Input name="country" required defaultValue="Belgium" className="mt-1.5" />
          </div>
          <div>
            <label className="label">Scope</label>
            <Select name="scope" defaultValue="country" className="mt-1.5">
              <option value="country">Country-specific</option>
              <option value="eu">EU-wide</option>
              <option value="universal">Universal</option>
            </Select>
          </div>
        </div>
        <div>
          <label className="label">Category</label>
          <Select value={categoryId} onChange={(e) => setCategoryId(Number(e.target.value))} className="mt-1.5">
            {categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
        <div>
          <label className="label">Keywords</label>
          <div className="mt-1.5 flex gap-2">
            <Input value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKeyword() } }} placeholder="Add a tag and press Enter" />
            <Button type="button" variant="secondary" onClick={addKeyword}>Add</Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {keywords.map((k) => <span key={k} className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-700">{k} <button type="button" onClick={() => setKeywords(keywords.filter((x) => x !== k))} className="text-stone-500 hover:text-stone-900">×</button></span>)}
          </div>
        </div>
        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={saving}>{saving ? "Submitting…" : "Submit"}</Button>
        </div>
      </form>
    </div>
  )
}
