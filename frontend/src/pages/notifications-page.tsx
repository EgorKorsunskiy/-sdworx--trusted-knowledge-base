import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"

export function NotificationsPage() {
  const [notifications, setNotifications] = useState<any[]>([])

  const load = () => api.notifications.list().then(setNotifications).catch(console.error)
  useEffect(() => { load() }, [])

  const markRead = async (id: number) => {
    await api.notifications.markRead(id)
    load()
  }

  return (
    <div>
      <PageHeader title="Notifications" />
      <div className="list-panel">
        {notifications.length === 0 ? (
          <div className="p-8 text-center text-sm text-stone-500">No notifications.</div>
        ) : (
          notifications.map((n) => (
            <div key={n.id} className={`p-4 ${n.is_read ? "opacity-60" : ""}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-sm font-medium">{n.title}</h3>
                  <p className="text-sm text-stone-600">{n.body}</p>
                  <p className="mt-1 text-xs text-stone-400">{new Date(n.created_at).toLocaleString()}</p>
                </div>
                {!n.is_read && <Button size="sm" variant="secondary" onClick={() => markRead(n.id)}>Mark read</Button>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
