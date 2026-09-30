import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"

export function SearchPage() {
  return (
    <div>
      <PageHeader
        title="Search"
        subtitle="Everything your team knows, with a clear level of trust."
      />
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-5 w-5 text-stone-400" />
          <Input placeholder="Search entries…" className="pl-10" />
        </div>
        <Button>Search</Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200">Belgium first</span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200">All departments</span>
        <span className="rounded-full bg-white px-3 py-1 ring-1 ring-inset ring-stone-200">Any status</span>
      </div>
      <div className="mt-6 list-panel">
        <div className="p-8 text-center text-sm text-stone-500">
          Search ranking arrives later. Try <strong>Add</strong>, or open the seeded demo entry{" "}
          <a className="font-medium text-stone-900 underline-offset-2 hover:underline" href="/entries/PP-BE-FRE-00001">
            PP-BE-FRE-00001
          </a>
          .
        </div>
      </div>
    </div>
  )
}
