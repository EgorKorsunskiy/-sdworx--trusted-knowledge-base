import { useState } from "react"
import { Link } from "react-router-dom"
import { MessageSquare, Mail } from "lucide-react"
import { api, type Contact, type PersonBrief } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { BasisFields, basisIsValid, type BasisValue } from "@/components/basis-fields"

const ROLE_LABEL: Record<Contact["role"], string> = {
  author: "Author",
  co_author: "Co-author",
  contributor: "Contributor",
}

export function ContactActions({ email }: { email?: string | null }) {
  if (!email) return null
  return (
    <span className="flex items-center gap-1">
      <a
        href={`https://teams.microsoft.com/l/chat/0/0?users=${encodeURIComponent(email)}`}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-stone-600 ring-1 ring-stone-300 hover:bg-stone-100"
      >
        <MessageSquare className="h-3 w-3" /> Teams
      </a>
      <a
        href={`mailto:${email}`}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-stone-600 ring-1 ring-stone-300 hover:bg-stone-100"
      >
        <Mail className="h-3 w-3" /> E-mail
      </a>
    </span>
  )
}

/**
 * The people to ask about an entry, with their basis (FR-K3 to FR-K5): responsible ones first, then the ones who
 * relayed it with their source. Without an active responsible person, the verifiers in scope are listed instead.
 */
export function ContactsCard({
  publicId,
  contacts,
  mine,
  noResponsible,
  verifiers,
  onChanged,
}: {
  publicId: string
  contacts: Contact[]
  mine?: Contact | null
  noResponsible: boolean
  verifiers: PersonBrief[]
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState<BasisValue>({ basis: "", source: "" })
  const [error, setError] = useState("")

  const responsible = contacts.filter((c) => c.basis === "responsible")
  const relayed = contacts.filter((c) => c.basis === "relayed")

  const startEdit = () => {
    setValue({ basis: mine?.basis ?? "", source: mine?.source ?? "" })
    setError("")
    setEditing(true)
  }

  const save = async () => {
    if (!basisIsValid(value) || !value.basis) return
    try {
      await api.entries.setMyBasis(publicId, { basis: value.basis, source: value.source || undefined })
      setEditing(false)
      onChanged()
    } catch (e: any) {
      setError(e.message || "Could not save")
    }
  }

  const row = (c: Contact) => (
    <li key={c.user.id} className="flex flex-wrap items-center gap-2 py-2.5">
      <div className="min-w-0 flex-1">
        <Link to={`/people/${c.user.id}`} className="font-medium hover:underline">{c.user.display_name}</Link>
        <Badge variant="neutral" className="ml-2">{ROLE_LABEL[c.role]}</Badge>
        <div className="text-xs text-stone-500">
          {[c.user.title, c.user.department].filter(Boolean).join(" · ")} · {c.reputation} rep
        </div>
        {c.basis === "relayed" && c.source && <div className="mt-0.5 text-xs text-stone-600">Source: {c.source}</div>}
      </div>
      <ContactActions email={c.email} />
    </li>
  )

  return (
    <div className="mt-6 card">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Contacts</h3>
        {mine && (
          <Button variant="ghost" size="sm" onClick={startEdit}>
            Change my basis
          </Button>
        )}
      </div>

      {responsible.length > 0 && (
        <>
          <div className="mt-3 text-xs font-medium uppercase tracking-wide text-emerald-700">Responsible for this topic</div>
          <ul className="divide-y divide-stone-100 text-sm">{responsible.map(row)}</ul>
        </>
      )}
      {relayed.length > 0 && (
        <>
          <div className="mt-3 text-xs font-medium uppercase tracking-wide text-stone-500">Added from source</div>
          <ul className="divide-y divide-stone-100 text-sm">{relayed.map(row)}</ul>
        </>
      )}

      {noResponsible && (
        <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-600/20">
          <div className="font-medium">No responsible contact</div>
          {verifiers.length > 0 && (
            <>
              <p className="mt-1 text-xs text-amber-800">These verifiers in scope can help:</p>
              <ul className="mt-1 text-sm">
                {verifiers.map((p) => (
                  <li key={p.id}>
                    <Link to={`/people/${p.id}`} className="font-medium hover:underline">{p.display_name}</Link>
                    <span className="text-xs text-amber-800">
                      {" "}· {[p.title, p.role && p.role.replace(/_/g, " ")].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <Dialog open={editing} onClose={() => setEditing(false)} title="Change my authorship basis">
        <div className="space-y-4">
          <p className="text-sm text-stone-600">
            The change is recorded in the change log. It does not create a new version or reset verification.
          </p>
          {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
          <BasisFields value={value} onChange={setValue} idPrefix="entry-basis" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            <Button onClick={save} disabled={!basisIsValid(value)}>Save</Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
