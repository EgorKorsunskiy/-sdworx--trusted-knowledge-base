import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { API_BASE, api, type AuthConfig, type User } from "@/lib/api"
import { startAuthorization } from "@/lib/pkce"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/page-header"

export function LoginPage() {
  const { user, login, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [error, setError] = useState("")
  const [redirecting, setRedirecting] = useState(false)

  useEffect(() => {
    if (user) {
      navigate("/", { replace: true })
      return
    }
    api.authConfig()
      .then((cfg) => {
        setConfig(cfg)
        if (cfg.demo_mode) {
          api.listUsers().then(setUsers).catch(() => {})
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load sign-in options"))
  }, [user, navigate])

  const signIn = async () => {
    if (!config) return
    setRedirecting(true)
    try {
      const base = config.idp.authorize_url.startsWith("/") ? API_BASE + config.idp.authorize_url : config.idp.authorize_url
      const url = await startAuthorization({
        authorizeUrl: base,
        clientId: config.idp.client_id,
        scope: config.idp.scope,
      })
      window.location.assign(url)
    } catch (err: unknown) {
      setRedirecting(false)
      setError(err instanceof Error ? err.message : "Could not start sign-in")
    }
  }

  const handleDemoLogin = async (userId: number) => {
    await login(userId)
    navigate("/", { replace: true })
  }

  if (authLoading) return <div className="p-10 text-center text-stone-500">Loading…</div>

  return (
    <div className="flex min-h-svh items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-md card">
        <PageHeader title="Peerpoint" subtitle="Sign in with your SD Worx account" />
        {error && (
          <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 ring-1 ring-inset ring-red-600/20">
            {error}
          </div>
        )}
        <Button className="mt-2 w-full" onClick={signIn} disabled={!config || redirecting}>
          {redirecting ? "Redirecting…" : "Sign in with SD Worx"}
        </Button>

        {config?.demo_mode && (
          <div className="mt-8">
            <p className="text-xs font-medium uppercase tracking-wide text-stone-400">Demo mode</p>
            <p className="mt-1 text-sm text-stone-500">Skip the identity provider and pick a demo user.</p>
            <div className="mt-3 space-y-2">
              {users.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => handleDemoLogin(u.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-4 py-3 text-left transition-colors hover:bg-stone-50"
                >
                  <div>
                    <div className="text-sm font-medium text-stone-900">{u.display_name}</div>
                    <div className="text-xs text-stone-500">
                      {u.title} · {u.roles.map((r) => r.role).join(", ")}
                    </div>
                  </div>
                  <span className="inline-flex h-8 items-center rounded-lg bg-stone-100 px-3 text-sm font-medium text-stone-700">
                    Use
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
