import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, User } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { PageHeader } from "@/components/page-header"

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    if (user) {
      navigate("/", { replace: true })
      return
    }
    api.listUsers()
      .then(setUsers)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load users"))
      .finally(() => setLoading(false))
  }, [user, navigate])

  const handleLogin = async (userId: number) => {
    await login(userId)
    navigate("/", { replace: true })
  }

  if (loading) return <div className="p-10 text-center text-stone-500">Loading…</div>

  return (
    <div className="flex min-h-svh items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-md card">
        <PageHeader title="Peerpoint" subtitle="Choose a demo user to continue" />
        {error && (
          <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
            {error}
          </div>
        )}
        <div className="mt-6 space-y-2">
          {users.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => handleLogin(u.id)}
              className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-4 py-3 text-left transition-colors hover:bg-stone-50"
            >
              <div>
                <div className="text-sm font-medium text-stone-900">{u.display_name}</div>
                <div className="text-xs text-stone-500">
                  {u.title} · {u.roles.map((r) => r.role).join(", ")}
                </div>
              </div>
              <span className="inline-flex h-8 items-center rounded-lg bg-stone-900 px-3 text-sm font-medium text-white">
                Log in
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
