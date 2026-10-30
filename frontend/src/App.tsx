import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import LetterPage from './pages/LetterPage'
import Letters from './pages/Letters'
import SignIn from './pages/SignIn'

function Shell() {
  const { session, loading, signOut } = useAuth()
  if (loading) return <main className="page"><p className="muted">Loading…</p></main>
  if (!session) return <SignIn />
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">Amtsbrief</Link>
        <span className="muted small">{session.name}</span>
        <button className="link" onClick={signOut}>Sign out</button>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Letters />} />
          <Route path="/letters/:id" element={<LetterPage />} />
          <Route path="*" element={<p>Page not found. <Link to="/">Back to your letters</Link></p>} />
        </Routes>
      </main>
      <footer className="footer small muted">
        Amtsbrief explains letters; it is not legal advice. Always check dates and amounts against the
        original letter. Letters are read by Google Gemini; the photo itself is not stored.
      </footer>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  )
}
