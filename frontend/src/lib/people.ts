export const ROLE_LABELS: Record<string, string> = {
  employee: "Employee",
  expert: "Senior Expert",
  team_lead: "Team Lead",
  manager: "Manager",
  admin: "Admin",
}

function monthYear(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "numeric" })
}

export function formatPeriod(start: string, end?: string | null): string {
  return `${monthYear(start)} – ${end ? monthYear(end) : "present"}`
}
