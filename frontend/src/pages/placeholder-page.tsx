import { PageHeader } from "@/components/page-header"

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <PageHeader title={title} />
      <div className="card text-sm text-stone-500">This screen is not implemented yet.</div>
    </div>
  )
}
