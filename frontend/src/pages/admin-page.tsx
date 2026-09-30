import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { PageHeader } from "@/components/page-header"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export function AdminPage() {
  const [settings, setSettings] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [mappings, setMappings] = useState<any[]>([])
  const [selectedUser, setSelectedUser] = useState("")
  const [department, setDepartment] = useState("")

  const load = () => {
    api.admin.settings().then(setSettings).catch(console.error)
    api.listUsers().then(setUsers).catch(console.error)
    api.admin.mappings().then(setMappings).catch(console.error)
  }
  useEffect(() => { load() }, [])

  const updateSetting = async (key: string, value: string) => {
    await api.admin.updateSetting(key, value)
    load()
  }

  const addMapping = async () => {
    if (!selectedUser || !department) return
    await api.admin.addMapping(Number(selectedUser), department)
    setDepartment("")
    load()
  }

  return (
    <div>
      <PageHeader title="Admin" />
      <div className="space-y-6">
        <div className="card">
          <h3 className="text-sm font-semibold">Settings</h3>
          <div className="mt-3 space-y-3">
            {settings.map((s) => (
              <div key={s.key} className="flex items-center gap-2">
                <span className="text-sm w-64">{s.key}</span>
                <Input defaultValue={s.value} onBlur={(e) => updateSetting(s.key, e.target.value)} />
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold">Verifier department mappings</h3>
          <div className="mt-3 flex gap-2">
            <select className="input" value={selectedUser} onChange={(e) => setSelectedUser(e.target.value)}>
              <option value="">Select user</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
            <Input placeholder="Department" value={department} onChange={(e) => setDepartment(e.target.value)} />
            <Button onClick={addMapping}>Add</Button>
          </div>
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {mappings.map((m) => <li key={m.id} className="py-2">{m.user_display_name} · {m.department}</li>)}
          </ul>
        </div>
      </div>
    </div>
  )
}
