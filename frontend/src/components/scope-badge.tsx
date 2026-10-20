import { Building2, Briefcase } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { Entry } from "@/lib/api"

export function scopeText(entry: Pick<Entry, "scope" | "company" | "client_project">): string {
  if (entry.client_project) return `${entry.client_project.name} · ${entry.client_project.company.name}`
  if (entry.company) return entry.company.name
  switch (entry.scope) {
    case "eu":
    case "EU-wide": return "EU-wide"
    case "universal": return "Universal"
    default: return "Country-specific"
  }
}

/** Where the entry is valid. The client's name is shown here and nowhere else (BR-11). */
export function ScopeBadge({ entry }: { entry: Pick<Entry, "scope" | "company" | "client_project"> }) {
  if (entry.client_project) {
    return (
      <Badge variant="neutral" className="bg-indigo-50 text-indigo-700 ring-indigo-600/20">
        <Briefcase className="h-3.5 w-3.5" />
        Client project: {scopeText(entry)}
      </Badge>
    )
  }
  if (entry.company) {
    return (
      <Badge variant="neutral" className="bg-indigo-50 text-indigo-700 ring-indigo-600/20">
        <Building2 className="h-3.5 w-3.5" />
        Company: {entry.company.name}
      </Badge>
    )
  }
  return <Badge variant="neutral">{scopeText(entry)}</Badge>
}
