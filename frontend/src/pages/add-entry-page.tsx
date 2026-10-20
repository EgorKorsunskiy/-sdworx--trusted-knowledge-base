import { useEffect, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { api, normalizeTag, type Company, type SuggestionPrefill, type TagSuggestion } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select } from "@/components/ui/select"
import { PageHeader } from "@/components/page-header"
import { BasisFields, basisIsValid, emptyBasis, type BasisValue } from "@/components/basis-fields"

const SCOPE_FROM_MEME: Record<string, string> = {
  country: "country",
  eu: "eu",
  universal: "universal",
  company: "company",
  client_project: "client_project",
}

export function AddEntryPage() {
  const navigate = useNavigate()
  // Opened from an approved suggestion of the Information overview: prefilled from the meme (FR-MP2)
  const [params] = useSearchParams()
  const suggestionId = Number(params.get("suggestion")) || null
  const [prefill, setPrefill] = useState<SuggestionPrefill | null>(null)
  const [prefillError, setPrefillError] = useState("")
  const [sensitiveConfirmed, setSensitiveConfirmed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState("")
  const [tagSuggestions, setTagSuggestions] = useState<TagSuggestion[]>([])
  const [categories, setCategories] = useState<any[]>([])
  const [categoryId, setCategoryId] = useState(1)
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [justification, setJustification] = useState("")
  const [similar, setSimilar] = useState<any[]>([])
  const [differenceNote, setDifferenceNote] = useState("")
  const [basis, setBasis] = useState<BasisValue>(emptyBasis)
  const [country, setCountry] = useState("Belgium")
  const [scope, setScope] = useState("country")
  const [companies, setCompanies] = useState<Company[]>([])
  const [companyId, setCompanyId] = useState("")
  const [clientProjectId, setClientProjectId] = useState("")

  useEffect(() => {
    api.companies().then(setCompanies).catch(() => {})
  }, [])

  const loadPrefill = () => {
    if (!suggestionId) return
    api.information
      .prefill(suggestionId)
      .then((p) => {
        setPrefill(p)
        if (p.already_published) return
        setTitle(p.title)
        setBody(p.body)
        setJustification(p.justification)
        if (p.category_id) setCategoryId(p.category_id)
        if (p.country) setCountry(p.country)
        setScope(SCOPE_FROM_MEME[p.scope] ?? "country")
        setCompanyId(p.company_id && !p.client_project_id ? String(p.company_id) : "")
        setClientProjectId(p.client_project_id ? String(p.client_project_id) : "")
        setKeywords(p.keywords)
        if (p.basis) setBasis({ basis: p.basis, source: p.basis_source ?? "" })
      })
      .catch((e) => setPrefillError(e.message || "This suggestion cannot be added"))
  }
  useEffect(loadPrefill, [suggestionId])

  // The scope names the company or client project; the company's country prefills the entry's country (BR-11).
  const pickCompany = (id: string) => {
    setCompanyId(id)
    const company = companies.find((c) => String(c.id) === id)
    if (company?.country) setCountry(company.country)
  }
  const pickClientProject = (id: string) => {
    setClientProjectId(id)
    const company = companies.find((c) => c.client_projects.some((p) => String(p.id) === id))
    if (company?.country) setCountry(company.country)
  }

  useEffect(() => {
    api.categories().then((cats: any) => {
      setCategories(cats)
      const def = cats.find((c: any) => c.is_default) ?? cats[0]
      if (def && !suggestionId) setCategoryId(def.id)
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
    try {
      const data = {
        title,
        body,
        justification: justification.trim() || undefined,
        country,
        scope,
        basis: basis.basis as "responsible" | "relayed",
        basis_source: basis.source.trim() || undefined,
        company_id: scope === "company" && companyId ? Number(companyId) : undefined,
        client_project_id: scope === "client_project" && clientProjectId ? Number(clientProjectId) : undefined,
        category_id: categoryId,
        keywords,
        difference_note: similar.length > 0 ? differenceNote.trim() || undefined : undefined,
        suggestion_id: suggestionId ?? undefined,
        sensitive_confirmed: prefill?.sensitive ? sensitiveConfirmed : undefined,
      }
      const entry: any = await api.entries.create(data)
      navigate(`/entries/${entry.public_id}`)
    } catch (err: any) {
      setError(err.message || "Failed to save entry")
      setSaving(false)
      // First save wins: another author may have published it meanwhile
      if (suggestionId && /already published/i.test(err.message || "")) loadPrefill()
    }
  }

  // Existing tags are suggested while typing; a new tag is only created when none matches (FR-T2).
  useEffect(() => {
    const q = keywordInput.trim()
    if (!q) {
      setTagSuggestions([])
      return
    }
    const timer = setTimeout(() => {
      api.tags.list(q, { type: "keyword", limit: 6 }).then(setTagSuggestions).catch(() => setTagSuggestions([]))
    }, 200)
    return () => clearTimeout(timer)
  }, [keywordInput])

  const addKeyword = (raw: string = keywordInput) => {
    const typed = normalizeTag(raw)
    // Enter on text that matches an existing tag picks that tag instead of creating another
    const value = tagSuggestions.find((s) => s.name === typed)?.name ?? typed
    if (value && !keywords.includes(value)) setKeywords([...keywords, value])
    setKeywordInput("")
    setTagSuggestions([])
  }

  if (suggestionId && prefillError) {
    return (
      <div>
        <PageHeader title="Add information" />
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">{prefillError}</div>
        <Link to="/information" className="mt-3 inline-block text-sm underline">Back to the Information overview</Link>
      </div>
    )
  }
  if (prefill?.already_published) {
    return (
      <div>
        <PageHeader title="Already published" />
        <div className="card text-sm">
          Another author already added this information to the repository
          {prefill.entry_public_id && (
            <>
              {" "}as <Link to={`/entries/${prefill.entry_public_id}`} className="font-medium underline">{prefill.entry_public_id}</Link>
            </>
          )}
          . Your suggestion is now in Decided; you are a co-author of the entry.
        </div>
        <Link to="/information?tab=yours&section=decided" className="mt-3 inline-block text-sm underline">
          Back to the Information overview
        </Link>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Add information"
        subtitle={
          prefill
            ? `From a ${prefill.source.kind === "meeting" ? "meeting" : "group chat"}: ${prefill.source.title}. Check and edit everything before saving.`
            : "New entries start as unverified and go to verifiers in scope."
        }
      />
      {prefill && (
        <div className="mb-6 rounded-xl bg-white p-4 text-sm ring-1 ring-stone-200">
          <h3 className="text-sm font-semibold">Everyone's answer</h3>
          <ul className="mt-2 space-y-1">
            {prefill.candidates.map((c) => (
              <li key={c.owner.id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.owner.display_name}{c.is_me && " (you)"}</span>
                <span className="text-stone-600">{c.label}</span>
                {c.reason && <span className="text-xs italic text-stone-500">“{c.reason}”</span>}
              </li>
            ))}
          </ul>
          {prefill.co_authors.length > 0 && (
            <p className="mt-3 text-xs text-stone-600">
              Recorded as co-authors of the entry: {prefill.co_authors.map((a) => a.display_name).join(", ")}. Candidates who
              have not decided are told that it was published and can still request co-authorship.
            </p>
          )}
        </div>
      )}
      {prefill?.sensitive && (
        <div className="mb-6 rounded-xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-600/20">
          <p className="font-medium">This information was flagged as possibly containing personal or confidential customer data.</p>
          <label className="mt-2 flex items-start gap-2">
            <input
              type="checkbox"
              checked={sensitiveConfirmed}
              onChange={(e) => setSensitiveConfirmed(e.target.checked)}
              className="mt-1 accent-stone-900"
            />
            <span>I edited the text and confirm it no longer contains such data.</span>
          </label>
        </div>
      )}
      {similar.length > 0 && (
        <div className="mb-6 rounded-xl bg-amber-50 p-4 ring-1 ring-amber-600/20">
          <h3 className="text-sm font-medium text-amber-900">Similar information already exists</h3>
          <ul className="mt-2 space-y-1 text-sm text-amber-800">
            {similar.map((s) => (
              <li key={s.public_id}>
                <Link className="underline" to={`/entries/${s.public_id}`}>{s.public_id}</Link> · {s.title} · {Math.round(s.score * 100)}% similar
                {" · "}
                <Link
                  className="font-medium underline"
                  to={`/entries/${s.public_id}/suggest`}
                  state={{ prefill: { title, body, justification }, fromDuplicate: true }}
                >
                  Create pull request
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-700">You can still submit, but consider suggesting a change to the existing entry. If you submit anyway, you can explain below why yours is different (optional).</p>
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
          <Textarea name="justification" rows={2} className="mt-1.5" value={justification} onChange={(e) => setJustification(e.target.value)} />
        </div>
        {similar.length > 0 && (
          <div className="rounded-xl bg-amber-50 p-4 ring-1 ring-amber-600/20">
            <label className="label text-amber-900">Why is this different?</label>
            <Textarea
              name="difference_note"
              rows={3}
              maxLength={1000}
              className="mt-1.5"
              value={differenceNote}
              onChange={(e) => setDifferenceNote(e.target.value)}
            />
            <p className="mt-1.5 text-xs text-amber-700">Optional. Verifiers will see this when deciding whether it is a duplicate.</p>
          </div>
        )}
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="label">Country</label>
            <Input name="country" required value={country} onChange={(e) => setCountry(e.target.value)} className="mt-1.5" />
          </div>
          <div>
            <label className="label">Scope</label>
            <Select name="scope" value={scope} onChange={(e) => setScope(e.target.value)} className="mt-1.5">
              <option value="country">Country-specific</option>
              <option value="eu">EU-wide</option>
              <option value="universal">Universal</option>
              <option value="company">Company-specific</option>
              <option value="client_project">Client-project-specific</option>
            </Select>
          </div>
        </div>
        {scope === "company" && (
          <div>
            <label className="label">Company</label>
            <Select required value={companyId} onChange={(e) => pickCompany(e.target.value)} className="mt-1.5">
              <option value="">Choose a company…</option>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
        )}
        {scope === "client_project" && (
          <div>
            <label className="label">Client project</label>
            <Select required value={clientProjectId} onChange={(e) => pickClientProject(e.target.value)} className="mt-1.5">
              <option value="">Choose a client project…</option>
              {companies.map((c) => (
                <optgroup key={c.id} label={c.name}>
                  {c.client_projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </optgroup>
              ))}
            </Select>
          </div>
        )}
        {(scope === "company" || scope === "client_project") && (
          <p className="-mt-2 text-xs text-stone-500">
            The client is named only in the scope. In the text, refer to the client project and leave out contract terms
            and personal data of the client's staff.
          </p>
        )}
        <div>
          <label className="label">Category</label>
          <Select value={categoryId} onChange={(e) => setCategoryId(Number(e.target.value))} className="mt-1.5">
            {categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
        <BasisFields
          value={basis}
          onChange={(next) => {
            // A relayed source also prefills the justification (FR-K1), as long as the user has not written one
            if (next.basis === "relayed" && next.source && (!justification.trim() || justification === basis.source)) {
              setJustification(next.source)
            }
            setBasis(next)
          }}
          idPrefix="entry-basis"
        />
        <div>
          <label className="label">Keywords</label>
          <div className="mt-1.5 flex gap-2">
            <Input value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKeyword() } }} placeholder="Add a tag and press Enter" />
            <Button type="button" variant="secondary" onClick={() => addKeyword()}>Add</Button>
          </div>
          {tagSuggestions.filter((s) => !keywords.includes(s.name)).length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
              Existing tags:
              {tagSuggestions
                .filter((s) => !keywords.includes(s.name))
                .map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => addKeyword(s.name)}
                    className="rounded-full bg-white px-2 py-0.5 text-stone-700 ring-1 ring-inset ring-stone-300 hover:bg-stone-100"
                  >
                    {s.name} <span className="text-stone-400">{s.entry_count}</span>
                  </button>
                ))}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {keywords.map((k) => <span key={k} className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-700">{k} <button type="button" onClick={() => setKeywords(keywords.filter((x) => x !== k))} className="text-stone-500 hover:text-stone-900">×</button></span>)}
          </div>
        </div>
        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={saving || !basisIsValid(basis) || (!!prefill?.sensitive && !sensitiveConfirmed)}>{saving ? "Submitting…" : "Submit"}</Button>
        </div>
      </form>
    </div>
  )
}
