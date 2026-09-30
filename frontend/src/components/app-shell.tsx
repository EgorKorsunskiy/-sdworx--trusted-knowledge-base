import { Link, useLocation, useNavigate } from "react-router-dom"
import { Search, Plus, ClipboardCheck, FolderKanban, Shield, Bell, User } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"

const navItems = [
  { to: "/", label: "Search", icon: Search },
  { to: "/add", label: "Add entry", icon: Plus },
  { to: "/approvals", label: "Approvals", icon: ClipboardCheck, count: 0 },
  { to: "/contributions", label: "My contributions", icon: FolderKanban },
  { to: "/admin", label: "Admin", icon: Shield },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  if (!user) return <>{children}</>

  return (
    <div className="min-h-svh bg-stone-50">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4 sm:px-6">
          <Link to="/" className="text-sm font-semibold tracking-tight">
            Peerpoint
          </Link>
          <nav className="hidden sm:flex items-center gap-1 text-sm font-medium">
            {navItems.map((item) => {
              const active = location.pathname === item.to || location.pathname.startsWith(item.to + "/")
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors ${
                    active
                      ? "bg-stone-100 text-stone-900"
                      : "text-stone-500 hover:text-stone-900"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                  {item.count ? (
                    <span className="ml-1 rounded-full bg-stone-900 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      {item.count}
                    </span>
                  ) : null}
                </Link>
              )
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <button className="relative rounded-md p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-900">
              <Bell className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2">
              <User className="h-5 w-5 text-stone-400" />
              <span className="hidden sm:inline text-stone-600">{user.display_name}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={() => logout().then(() => navigate("/login"))}>
              Log out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  )
}
