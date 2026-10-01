import { CheckCircle2, Clock, AlertCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"

interface TrustBadgeProps {
  status: string
  verifierRole?: string
}

export function TrustBadge({ status, verifierRole }: TrustBadgeProps) {
  const s = status.toLowerCase()
  if (s === "verified") {
    return (
      <Badge variant="verified">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Verified by {verifierRole || "Verifier"}
      </Badge>
    )
  }
  if (s === "outdated" || s === "stale") {
    return (
      <Badge variant="outdated">
        <AlertCircle className="h-3.5 w-3.5" />
        Outdated
      </Badge>
    )
  }
  return (
    <Badge variant="unverified">
      <Clock className="h-3.5 w-3.5" />
      Unverified
    </Badge>
  )
}
