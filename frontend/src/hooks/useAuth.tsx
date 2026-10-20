import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { api, refreshSession, SIGNED_OUT_EVENT, type Session, type User } from "@/lib/api"

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (userId: number) => Promise<void>
  completeSignIn: (code: string, verifier: string, redirectUri: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Page load: the access token is only in memory, so ask the refresh cookie for a fresh one.
    refreshSession()
      .then((session: Session | null) => setUser(session?.authenticated ? session.user : null))
      .finally(() => setLoading(false))

    // Renewal failed during a request: back to the sign-in screen.
    const onSignedOut = () => setUser(null)
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut)
  }, [])

  const login = async (userId: number) => {
    const res = await api.login(userId)
    setUser(res.user)
  }

  const completeSignIn = async (code: string, verifier: string, redirectUri: string) => {
    const res = await api.exchangeCode({ code, code_verifier: verifier, redirect_uri: redirectUri })
    setUser(res.user)
  }

  const logout = async () => {
    await api.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, completeSignIn, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
