import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider, useAuth } from "@/hooks/useAuth"
import { AppShell } from "@/components/app-shell"
import { LoginPage } from "@/pages/login-page"
import { SearchPage } from "@/pages/search-page"
import { AddEntryPage } from "@/pages/add-entry-page"
import { EntryPage } from "@/pages/entry-page"
import { PlaceholderPage } from "@/pages/placeholder-page"

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-10 text-center text-stone-500">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <AppShell>
              <Routes>
                <Route path="/" element={<SearchPage />} />
                <Route path="/add" element={<AddEntryPage />} />
                <Route path="/entries/:publicId" element={<EntryPage />} />
                <Route path="/approvals" element={<PlaceholderPage title="Approvals" />} />
                <Route path="/contributions" element={<PlaceholderPage title="My contributions" />} />
                <Route path="/admin" element={<PlaceholderPage title="Admin" />} />
              </Routes>
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
