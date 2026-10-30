import { useState } from 'react'
import { useAuth } from '../auth'

export default function SignIn() {
  const { signIn } = useAuth()
  const [error, setError] = useState<string | null>(null)

  return (
    <main className="page narrow">
      <h1>Amtsbrief</h1>
      <p className="lead">
        Photograph a letter from the Finanzamt, Bürgeramt, Krankenkasse, your landlord or a fine.
        Amtsbrief explains it in plain English, finds the amounts and deadlines, and shows the line in
        the letter that each one comes from.
      </p>
      <ul className="points">
        <li>Deadlines are calculated in code, step by step, never guessed by the AI.</li>
        <li>Anything that can’t be checked against the letter is marked “Couldn’t verify”.</li>
        <li>Add every deadline to your own calendar.</li>
      </ul>
      <button
        className="primary"
        onClick={() => signIn().catch(() => setError('Sign-in was cancelled or failed. Try again.'))}
      >
        Sign in with Google
      </button>
      {error && <p className="error">{error}</p>}
      <p className="small muted">
        Your letters are read by Google Gemini and stored in your account so you can come back to them.
        The photo or PDF itself is not stored, and you can delete any letter. Amtsbrief is not legal advice.
      </p>
    </main>
  )
}
