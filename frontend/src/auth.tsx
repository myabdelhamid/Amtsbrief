// Google sign-in through Firebase Auth. The backend checks the ID token on every request.
//
// Local development without Firebase: set VITE_DEV_AUTH=true and start the backend with
// AMTSBRIEF_DEV_USER=dev. The app then skips sign-in and sends no token.
import { initializeApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, onAuthStateChanged, signInWithPopup, signOut, type User } from 'firebase/auth'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const DEV = import.meta.env.VITE_DEV_AUTH === 'true'

const auth = DEV
  ? null
  : getAuth(initializeApp({
      apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
      authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
      appId: import.meta.env.VITE_FIREBASE_APP_ID,
    }))

interface Session {
  name: string
  token: () => Promise<string | null> // fresh ID token (Firebase refreshes it hourly)
}

interface AuthState {
  session: Session | null
  loading: boolean
  signIn: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

function toSession(user: User): Session {
  return { name: user.displayName ?? user.email ?? 'you', token: () => user.getIdToken() }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(DEV ? { name: 'Dev', token: async () => null } : null)
  const [loading, setLoading] = useState(!DEV)

  useEffect(() => {
    if (!auth) return
    return onAuthStateChanged(auth, (user) => {
      setSession(user ? toSession(user) : null)
      setLoading(false)
    })
  }, [])

  const value: AuthState = {
    session,
    loading,
    signIn: async () => {
      if (auth) await signInWithPopup(auth, new GoogleAuthProvider())
    },
    signOut: async () => {
      if (auth) await signOut(auth)
    },
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (!state) throw new Error('useAuth outside AuthProvider')
  return state
}
