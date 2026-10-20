import { Badge } from "@/components/ui/badge"
import type { PRStatus } from "@/lib/api"

export function PRStatusBadge({ status }: { status: PRStatus | string }) {
  if (status === "merged") return <Badge variant="success">Merged</Badge>
  if (status === "rejected") return <Badge variant="danger">Rejected</Badge>
  if (status === "author_approved") return <Badge variant="warning">Author approved</Badge>
  return <Badge variant="warning">Open</Badge>
}
