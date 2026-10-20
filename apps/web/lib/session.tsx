'use client'
import { ClerkProvider, useAuth, useUser } from '@clerk/clerk-react'
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react'
import { setTokenGetter } from './api'

// Shared NEXORA account login (Clerk). gateway.onenexora.com is a subdomain of the account's primary domain,
// so the account session is shared; we only need the public publishable key, no secret key in this app.
const PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''
const SIGN_IN_URL = process.env.NEXT_PUBLIC_SIGN_IN_URL ?? 'https://account.onenexora.com/sign-in'
const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === '1'

type Session = { email: string; signOut: () => void }
const Ctx = createContext<Session>({ email: '', signOut: () => {} })
export const useSession = () => useContext(Ctx)

function Waiting({ text }: Readonly<{ text: string }>) {
  return <output className="flex min-h-screen items-center justify-center text-text-muted">{text}</output>
}

function ClerkInner({ children }: Readonly<{ children: ReactNode }>) {
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

  const email = user?.primaryEmailAddress?.emailAddress ?? ''
  const value = useMemo(() => ({ email, signOut: () => { setTokenGetter(null); signOut({ redirectUrl: '/' }) } }), [email, signOut])
  if (!ready) return <Waiting text={isLoaded && !isSignedIn ? 'Taking you to sign in…' : 'Loading…'} />
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

const DEV_SESSION: Session = { email: 'demo@dev.local', signOut: () => {} }

export function AuthGate({ children }: Readonly<{ children: ReactNode }>) {
  if (DEV_AUTH) return <Ctx.Provider value={DEV_SESSION}>{children}</Ctx.Provider>
  if (!PUBLISHABLE_KEY) return <Waiting text="Sign-in is not configured for this environment." />
  return <ClerkProvider publishableKey={PUBLISHABLE_KEY} signInUrl={SIGN_IN_URL} afterSignOutUrl="/"><ClerkInner>{children}</ClerkInner></ClerkProvider>
}
