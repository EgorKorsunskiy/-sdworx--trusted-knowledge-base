import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { api, type User } from "@/lib/api"

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (userId: number) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then((res) => setUser(res.authenticated ? res.user : null))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async (userId: number) => {
    const res = await api.login(userId)
    setUser(res.user)
  }

  const logout = async () => {
    await api.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
