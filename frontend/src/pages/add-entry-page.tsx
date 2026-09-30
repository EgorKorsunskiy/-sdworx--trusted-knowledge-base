import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, type Category } from "@/lib/api"
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
  const [categories, setCategories] = useState<Category[]>([])
  const [categoryId, setCategoryId] = useState(1)

  useEffect(() => {
    void api.categories().then((cats) => {
      setCategories(cats)
      const def = cats.find((c) => c.is_default) ?? cats[0]
      if (def) setCategoryId(def.id)
    })
  }, [])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setSaving(true)
    setError("")
    const form = new FormData(e.currentTarget)
    try {
      const data = {
        title: form.get("title") as string,
        body: form.get("body") as string,
        justification: (form.get("justification") as string) || undefined,
        country: form.get("country") as string,
        scope: form.get("scope") as string,
        category_id: categoryId,
        keywords,
      }
      const entry = await api.entries.create(data)
      navigate(`/entries/${entry.public_id}`)
    } catch (err: any) {
      setError(err.message || "Failed to save entry")
      setSaving(false)
    }
  }

  const addKeyword = () => {
    const value = keywordInput.trim()
    if (value && !keywords.some((k) => k.toLowerCase() === value.toLowerCase())) {
      setKeywords([...keywords, value])
    }
    setKeywordInput("")
  }

  return (
    <div>
      <PageHeader
        title="Add entry"
        subtitle="New entries start as Unverified and can be edited by the author until verified."
      />
      <form onSubmit={handleSubmit} className="card space-y-5">
        {error && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="title" className="label">
            Title
          </label>
          <Input id="title" name="title" required className="mt-1.5" />
        </div>
        <div>
          <label htmlFor="body" className="label">
            Content
          </label>
          <Textarea id="body" name="body" rows={6} required className="mt-1.5" />
        </div>
        <div>
          <label htmlFor="justification" className="label">
            Justification / source
          </label>
          <Textarea id="justification" name="justification" rows={2} className="mt-1.5" />
        </div>
        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <label htmlFor="category" className="label">
              Category
            </label>
            <Select
              id="category"
              name="category"
              className="mt-1.5"
              value={categoryId}
              onChange={(e) => setCategoryId(Number(e.target.value))}
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="country" className="label">
              Country
            </label>
            <Select id="country" name="country" required defaultValue="BE" className="mt-1.5">
              <option value="BE">Belgium (BE)</option>
              <option value="NL">Netherlands (NL)</option>
              <option value="DE">Germany (DE)</option>
              <option value="FR">France (FR)</option>
              <option value="EU">EU</option>
            </Select>
          </div>
          <div>
            <label htmlFor="scope" className="label">
              Scope
            </label>
            <Select id="scope" name="scope" defaultValue="country-specific" className="mt-1.5">
              <option value="country-specific">Country-specific</option>
              <option value="EU-wide">EU-wide</option>
              <option value="universal">Universal</option>
            </Select>
          </div>
        </div>
        <div>
          <label className="label">Keywords</label>
          <div className="mt-1.5 flex gap-2">
            <Input
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  addKeyword()
                }
              }}
              placeholder="Add a tag and press Enter"
            />
            <Button type="button" variant="secondary" onClick={addKeyword}>
              Add
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {keywords.map((k) => (
              <span
                key={k}
                className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-700"
              >
                {k}
                <button
                  type="button"
                  onClick={() => setKeywords(keywords.filter((x) => x !== k))}
                  className="text-stone-500 hover:text-stone-900"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={saving}>
            {saving ? "Submitting…" : "Submit"}
          </Button>
        </div>
      </form>
    </div>
  )
}
