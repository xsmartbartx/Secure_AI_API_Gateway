'use client'
import { ClerkProvider, useAuth, useUser } from '@clerk/clerk-react'
import { createContext, ReactNode, useContext, useEffect, useState } from 'react'
import { setTokenGetter } from './api'

// Shared NEXORA account login (Clerk). gateway.onenexora.com is a subdomain of the account's primary domain,
// so the account session is shared; we only need the public publishable key, no secret key in this app.
const PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''
const SIGN_IN_URL = process.env.NEXT_PUBLIC_SIGN_IN_URL ?? 'https://account.onenexora.com/sign-in'
const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === '1'

type Session = { email: string; signOut: () => void }
const Ctx = createContext<Session>({ email: '', signOut: () => {} })
export const useSession = () => useContext(Ctx)

function Waiting({ text }: { text: string }) {
  return <div className="flex min-h-screen items-center justify-center text-text-muted" role="status">{text}</div>
}

function ClerkInner({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth()
  const { user } = useUser()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!isLoaded) return
    if (!isSignedIn) {
      window.location.replace(`${SIGN_IN_URL}?redirect_url=${encodeURIComponent(window.location.href)}`)
      return
    }
    setTokenGetter(() => getToken()) // short-lived session JWT, refreshed by Clerk on every call
    setReady(true)
  }, [isLoaded, isSignedIn, getToken])

  if (!ready) return <Waiting text={isLoaded && !isSignedIn ? 'Taking you to sign in…' : 'Loading…'} />
  return <Ctx.Provider value={{ email: user?.primaryEmailAddress?.emailAddress ?? '', signOut: () => { setTokenGetter(null); signOut({ redirectUrl: '/' }) } }}>{children}</Ctx.Provider>
}

export function AuthGate({ children }: { children: ReactNode }) {
  if (DEV_AUTH) return <Ctx.Provider value={{ email: 'demo@dev.local', signOut: () => {} }}>{children}</Ctx.Provider>
  if (!PUBLISHABLE_KEY) return <Waiting text="Sign-in is not configured for this environment." />
  return <ClerkProvider publishableKey={PUBLISHABLE_KEY} signInUrl={SIGN_IN_URL} afterSignOutUrl="/"><ClerkInner>{children}</ClerkInner></ClerkProvider>
}
