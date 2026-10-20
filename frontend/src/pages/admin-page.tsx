import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { api, type ProjectDetail, type TeamDetail } from "@/lib/api"
import { formatPeriod } from "@/lib/people"
import { PageHeader } from "@/components/page-header"
import { Input, Select } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

function TeamsProjectsCard({ users }: { users: any[] }) {
  const [teams, setTeams] = useState<TeamDetail[]>([])
  const [projects, setProjects] = useState<ProjectDetail[]>([])
  const [error, setError] = useState("")

  const [teamName, setTeamName] = useState("")
  const [teamDept, setTeamDept] = useState("")
  const [teamLead, setTeamLead] = useState("")
  const [projName, setProjName] = useState("")
  const [projDesc, setProjDesc] = useState("")
  const [projStatus, setProjStatus] = useState("active")
  const [projLead, setProjLead] = useState("")

  const [kind, setKind] = useState<"team" | "project">("team")
  const [itemId, setItemId] = useState("")
  const [memberUser, setMemberUser] = useState("")
  const [memberRole, setMemberRole] = useState("Member")
  const [startDate, setStartDate] = useState("")

  const load = () => {
    api.teams.list()
      .then((list) => Promise.all(list.map((t) => api.teams.get(t.id).catch(() => null))))
      .then((all) => setTeams(all.filter(Boolean) as TeamDetail[]))
      .catch(console.error)
    api.projects.list()
      .then((list) => Promise.all(list.map((p) => api.projects.get(p.id).catch(() => null))))
      .then((all) => setProjects(all.filter(Boolean) as ProjectDetail[]))
      .catch(console.error)
  }
  useEffect(() => { load() }, [])

  const run = async (fn: () => Promise<unknown>, onOk?: () => void) => {
    setError("")
    try {
      await fn()
      onOk?.()
      load()
    } catch (e: any) {
      setError(e.message || "Request failed")
    }
  }

  const createTeam = () =>
    run(
      () => api.admin.createTeam({ name: teamName, department: teamDept, lead_user_id: teamLead ? Number(teamLead) : null }),
      () => { setTeamName(""); setTeamDept(""); setTeamLead("") },
    )
  const createProject = () =>
    run(
      () => api.admin.createProject({
        name: projName,
        description: projDesc || undefined,
        status: projStatus,
        lead_user_id: projLead ? Number(projLead) : null,
      }),
      () => { setProjName(""); setProjDesc(""); setProjStatus("active"); setProjLead("") },
    )
  const addMember = () =>
    run(
      () =>
        kind === "team"
          ? api.admin.addTeamMember(Number(itemId), { user_id: Number(memberUser), role: memberRole || "Member" })
          : api.admin.addProjectMember(Number(itemId), {
              user_id: Number(memberUser),
              role: memberRole || "Member",
              start_date: startDate || undefined,
            }),
      () => { setMemberUser(""); setMemberRole("Member"); setStartDate("") },
    )

  const items = kind === "team" ? teams : projects
  const userOptions = users.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)

  return (
    <div className="card">
      <h3 className="text-sm font-semibold">Teams &amp; projects</h3>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <div className="text-xs font-medium text-stone-500">Create team</div>
          <Input placeholder="Name" value={teamName} onChange={(e) => setTeamName(e.target.value)} />
          <Input placeholder="Department" value={teamDept} onChange={(e) => setTeamDept(e.target.value)} />
          <Select value={teamLead} onChange={(e) => setTeamLead(e.target.value)}>
            <option value="">No lead</option>
            {userOptions}
          </Select>
          <Button onClick={createTeam} disabled={!teamName.trim() || !teamDept.trim()}>Create team</Button>
        </div>
        <div className="space-y-2">
          <div className="text-xs font-medium text-stone-500">Create project</div>
          <Input placeholder="Name" value={projName} onChange={(e) => setProjName(e.target.value)} />
          <Input placeholder="Description" value={projDesc} onChange={(e) => setProjDesc(e.target.value)} />
          <div className="flex gap-2">
            <Select value={projStatus} onChange={(e) => setProjStatus(e.target.value)}>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
            </Select>
            <Select value={projLead} onChange={(e) => setProjLead(e.target.value)}>
              <option value="">No lead</option>
              {userOptions}
            </Select>
          </div>
          <Button onClick={createProject} disabled={!projName.trim()}>Create project</Button>
        </div>
      </div>

      <div className="mt-6 space-y-2">
        <div className="text-xs font-medium text-stone-500">Add member</div>
        <div className="flex flex-wrap gap-2">
          <Select className="w-auto" value={kind} onChange={(e) => { setKind(e.target.value as "team" | "project"); setItemId("") }}>
            <option value="team">Team</option>
            <option value="project">Project</option>
          </Select>
          <Select className="w-auto" value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">Select {kind}</option>
            {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </Select>
          <Select className="w-auto" value={memberUser} onChange={(e) => setMemberUser(e.target.value)}>
            <option value="">Select user</option>
            {userOptions}
          </Select>
          <Input className="w-40" placeholder="Role" value={memberRole} onChange={(e) => setMemberRole(e.target.value)} />
          {kind === "project" && (
            <Input className="w-40" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          )}
          <Button onClick={addMember} disabled={!itemId || !memberUser}>Add</Button>
        </div>
      </div>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <div>
          <div className="text-xs font-medium text-stone-500">Teams</div>
          <ul className="mt-2 space-y-3 text-sm">
            {teams.map((t) => (
              <li key={t.id}>
                <Link to={`/teams/${t.id}`} className="font-medium hover:underline">{t.name}</Link>
                <ul className="mt-1 divide-y divide-stone-100">
                  {t.members.map((m) => (
                    <li key={m.membership_id} className="flex items-center justify-between py-1">
                      <span>{m.user.display_name} · <span className="text-stone-500">{m.role}</span></span>
                      <Button variant="ghost" size="sm" onClick={() => run(() => api.admin.removeTeamMember(m.membership_id))}>Remove</Button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-xs font-medium text-stone-500">Projects</div>
          <ul className="mt-2 space-y-3 text-sm">
            {projects.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                <span className="ml-2 text-xs capitalize text-stone-500">{p.status}</span>
                <ul className="mt-1 divide-y divide-stone-100">
                  {p.members.map((m) => (
                    <li key={m.membership_id} className="flex items-center justify-between py-1">
                      <span>
                        {m.user.display_name} · <span className="text-stone-500">{m.role} · {formatPeriod(m.start_date, m.end_date)}</span>
                      </span>
                      <Button variant="ghost" size="sm" onClick={() => run(() => api.admin.removeProjectMember(m.membership_id))}>Remove</Button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
        <TeamsProjectsCard users={users} />
      </div>
    </div>
  )
}

export function AdminPage() {
  const [settings, setSettings] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [mappings, setMappings] = useState<any[]>([])
  const [selectedUser, setSelectedUser] = useState("")
  const [department, setDepartment] = useState("")

  const load = () => {
    api.admin.settings().then(setSettings).catch(console.error)
    api.people.list().then(setUsers).catch(console.error)
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
        <TeamsProjectsCard users={users} />
      </div>
    </div>
  )
}
