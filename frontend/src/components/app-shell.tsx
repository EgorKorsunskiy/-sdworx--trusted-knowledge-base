import { Link, useLocation, useNavigate } from "react-router-dom"
import { Search, Plus, ClipboardCheck, FolderKanban, Shield, Bell, User, Lightbulb, LogOut, Menu, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useAuth } from "@/hooks/useAuth"
import { api } from "@/lib/api"

const navItems: { to: string; label: string; icon: typeof Search; count?: number }[] = [
  { to: "/", label: "Search", icon: Search },
  { to: "/information", label: "Information overview", icon: Lightbulb },
  { to: "/add", label: "Add entry", icon: Plus },
  { to: "/approvals", label: "Approvals", icon: ClipboardCheck, count: 0 },
  { to: "/contributions", label: "My contributions", icon: FolderKanban },
  { to: "/admin", label: "Admin", icon: Shield },
]

const linkClass = (active: boolean) =>
  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:bg-stone-50 hover:text-stone-900"
  }`

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const [toDecide, setToDecide] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    api.notifications.unreadCount().then((r: any) => setUnread(r.count)).catch(() => {})
    // Suggestions to decide plus incoming co-author requests (FR-MS16)
    api.information.summary().then((r) => setToDecide(r.badge)).catch(() => {})
  }, [location.pathname, location.search])

  // The mobile menu closes after navigating
  useEffect(() => setMenuOpen(false), [location.pathname])

  if (!user) return <>{children}</>

  const badge = (to: string, count?: number) => (to === "/information" ? toDecide : count) || 0

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link to="/" className="flex h-14 shrink-0 items-center px-5 text-base font-semibold tracking-tight">
        Peerpoint
      </Link>

      <nav aria-label="Main" className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {navItems.map((item) => {
          const active =
            location.pathname === item.to ||
            location.pathname.startsWith(item.to + "/") ||
            (item.to === "/" && location.pathname === "/search") // tag links open /search?tag=...
          const count = badge(item.to, item.count)
          return (
            <Link key={item.to} to={item.to} className={linkClass(active)} aria-current={active ? "page" : undefined}>
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{item.label}</span>
              {count ? (
                <span className="rounded-full bg-stone-900 px-1.5 py-0.5 text-[10px] font-semibold text-white">{count}</span>
              ) : null}
            </Link>
          )
        })}
      </nav>

      <div className="shrink-0 space-y-1 border-t border-stone-200 px-3 py-3">
        <Link to="/notifications" className={linkClass(location.pathname === "/notifications")}>
          <Bell className="h-4 w-4 shrink-0" />
          <span className="flex-1">Notifications</span>
          {unread > 0 && <span className="h-2 w-2 rounded-full bg-red-500" aria-label="Unread notifications" />}
        </Link>
        <Link to={`/people/${user.id}`} className={linkClass(location.pathname === `/people/${user.id}`)}>
          <User className="h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{user.display_name}</span>
        </Link>
        <button
          type="button"
          onClick={() => logout().then(() => navigate("/login"))}
          className={`${linkClass(false)} w-full`}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Log out
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-svh bg-stone-50">
      {/* Desktop: fixed sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-stone-200 bg-white md:block">{sidebar}</aside>

      {/* Mobile: slim top bar with a menu that opens the same sidebar */}
      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-stone-200 bg-white/90 px-4 backdrop-blur md:hidden">
        <button
          type="button"
          aria-label="Open menu"
          onClick={() => setMenuOpen(true)}
          className="rounded-md p-1.5 text-stone-600 hover:bg-stone-100"
        >
          <Menu className="h-5 w-5" />
        </button>
        <Link to="/" className="text-sm font-semibold tracking-tight">Peerpoint</Link>
        <Link to="/notifications" className="relative ml-auto rounded-md p-1.5 text-stone-500 hover:bg-stone-100">
          <Bell className="h-5 w-5" />
          {unread > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-red-500" />}
        </Link>
      </header>
      {menuOpen && (
        <div className="fixed inset-0 z-30 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-stone-900/30"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-xl">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
              className="absolute right-2 top-3 rounded-md p-1.5 text-stone-500 hover:bg-stone-100"
            >
              <X className="h-4 w-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <main className="md:pl-64">
        <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">{children}</div>
      </main>
    </div>
  )
}
