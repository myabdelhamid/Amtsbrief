// Google sign-in through Firebase Auth. The backend checks the ID token on every request.
//
// The Firebase web config comes from GET /api/config at startup, so one build works for any
// project. When the backend runs with AMTSBRIEF_DEV_USER (local development only), the config
// says dev: true and the app skips sign-in and sends no token.
import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider, getAuth, onAuthStateChanged, signInWithPopup, signOut, type Auth, type User,
} from 'firebase/auth'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface Session {
  name: string
  token: () => Promise<string | null> // fresh ID token (Firebase refreshes it hourly)
}

interface AuthState {
  session: Session | null
  loading: boolean
  error: string | null
  signIn: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

function toSession(user: User): Session {
  return { name: user.displayName ?? user.email ?? 'you', token: () => user.getIdToken() }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<Auth | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let unsubscribe = () => {}
    fetch('/api/config')
      .then((response) => response.json())
      .then((config) => {
        if (config.dev) {
          setSession({ name: 'Dev', token: async () => null })
          setLoading(false)
          return
        }
        const firebaseAuth = getAuth(initializeApp(config.firebase))
        setAuth(firebaseAuth)
        unsubscribe = onAuthStateChanged(firebaseAuth, (user) => {
          setSession(user ? toSession(user) : null)
          setLoading(false)
        })
      })
      .catch(() => {
        setError('Amtsbrief couldn’t start. Reload the page.')
        setLoading(false)
      })
    return () => unsubscribe()
  }, [])

  const value: AuthState = {
    session,
    loading,
    error,
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
