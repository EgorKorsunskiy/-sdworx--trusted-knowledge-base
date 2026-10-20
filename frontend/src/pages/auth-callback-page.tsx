import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { takeAuthorization } from "@/lib/pkce"
import { useAuth } from "@/hooks/useAuth"

/** The identity provider sends the browser back here with ?code=...&state=... */
export function AuthCallbackPage() {
  const { completeSignIn } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState("")
  const started = useRef(false) // React StrictMode runs effects twice; the code is single use

  useEffect(() => {
    if (started.current) return
    started.current = true

    const params = new URLSearchParams(window.location.search)
    const saved = takeAuthorization()
    const code = params.get("code")
    if (params.get("error")) {
      setError(params.get("error_description") || "The identity provider refused the sign-in.")
    } else if (!code || !saved || saved.state !== params.get("state")) {
      setError("This sign-in attempt is not valid or has expired. Please try again.")
    } else {
      completeSignIn(code, saved.verifier, saved.redirectUri)
        .then(() => navigate("/", { replace: true }))
        .catch((err: unknown) => setError(err instanceof Error ? err.message : "Sign-in failed"))
    }
  }, [])

  if (!error) return <div className="p-10 text-center text-stone-500">Signing you in…</div>
  return (
    <div className="flex min-h-svh items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-md card text-center">
        <h1 className="text-lg font-semibold">Could not sign you in</h1>
        <p className="mt-2 text-sm text-stone-500">{error}</p>
        <Link to="/login" className="mt-4 inline-block text-sm underline">
          Back to sign-in
        </Link>
      </div>
    </div>
  )
}
