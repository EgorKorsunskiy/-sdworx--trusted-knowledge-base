import { Input } from "@/components/ui/input"

export type Basis = "responsible" | "relayed"
export type BasisValue = { basis: Basis | ""; source: string }

export const emptyBasis: BasisValue = { basis: "", source: "" }

/** A basis is complete when one is chosen and a Relayed one names its source (FR-K1, FR-MO15). */
export const basisIsValid = (v: BasisValue) => v.basis === "responsible" || (v.basis === "relayed" && v.source.trim() !== "")

export const basisLabel = (basis: string) => (basis === "responsible" ? "Responsible" : "Relayed")

/** Authorship basis chooser: Responsible, or Relayed with the source the information came from. */
export function BasisFields({
  value,
  onChange,
  idPrefix = "basis",
}: {
  value: BasisValue
  onChange: (next: BasisValue) => void
  idPrefix?: string
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="label">Your authorship basis</legend>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="radio"
          name={`${idPrefix}-basis`}
          checked={value.basis === "responsible"}
          onChange={() => onChange({ ...value, basis: "responsible" })}
          className="mt-1 accent-stone-900"
        />
        <span>
          <span className="font-medium">Responsible</span>
          <span className="block text-xs text-stone-500">
            Answering questions on this topic is part of my job. I expect to be asked and will answer.
          </span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="radio"
          name={`${idPrefix}-basis`}
          checked={value.basis === "relayed"}
          onChange={() => onChange({ ...value, basis: "relayed" })}
          className="mt-1 accent-stone-900"
        />
        <span>
          <span className="font-medium">Relayed</span>
          <span className="block text-xs text-stone-500">
            I read or heard this and added it. I name where it comes from.
          </span>
        </span>
      </label>
      {value.basis === "relayed" && (
        <div>
          <Input
            aria-label="Source"
            placeholder="Source: document, link, regulation, newsletter or colleague"
            maxLength={500}
            value={value.source}
            onChange={(e) => onChange({ ...value, source: e.target.value })}
          />
          <p className="mt-1 text-xs text-stone-500">
            Every reader sees the source, so keep customer data and conversation quotes out of it.
          </p>
        </div>
      )}
    </fieldset>
  )
}
