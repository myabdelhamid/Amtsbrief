import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, feedUrl, listLetters, uploadLetter } from '../api'
import { useAuth } from '../auth'
import { LETTER_TYPE, formatDate, inDays } from '../format'
import type { LetterSummary } from '../types'

export default function Letters() {
  const { session } = useAuth()
  const token = session!.token
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [letters, setLetters] = useState<LetterSummary[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feed, setFeed] = useState<string | null>(null)

  useEffect(() => {
    listLetters(token).then(setLetters).catch(() => setError('Couldn’t load your letters. Reload the page.'))
  }, [token])

  async function upload(file: File) {
    setBusy(true)
    setError(null)
    try {
      const letter = await uploadLetter(token, file)
      navigate(`/letters/${letter.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Upload failed. Check your connection and try again.')
      setBusy(false)
    }
  }

  return (
    <>
      <section className="card upload">
        <h1>Add a letter</h1>
        <p className="muted">A photo of each page, or the PDF. Reading a letter takes about 20–40 seconds.</p>
        <input
          ref={input}
          type="file"
          accept="application/pdf,image/*"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = '' // so choosing the same file again still triggers onChange
            if (file) upload(file)
          }}
        />
        <button className="primary" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? 'Reading your letter…' : 'Choose photo or PDF'}
        </button>
        {busy && <p className="small muted">Transcribing, extracting and checking every line. Keep this page open.</p>}
        {error && <p className="error">{error}</p>}
      </section>

      <section>
        <div className="row between">
          <h2>Your letters</h2>
          <button className="link" onClick={() => feedUrl(token).then(setFeed)}>Calendar feed</button>
        </div>
        {feed && (
          <div className="card small">
            <p>
              Subscribe to this address in Google Calendar, Apple Calendar or Outlook (“Add calendar from URL”) to
              see every deadline. Keep it private: anyone with the link can see your deadlines.
            </p>
            <code className="feed">{feed}</code>
            <div className="row">
              <button onClick={() => navigator.clipboard.writeText(feed)}>Copy</button>
              <a className="button" href={feed.replace(/^https?:/, 'webcal:')}>Open in calendar app</a>
            </div>
          </div>
        )}
        {letters === null && !error && <p className="muted">Loading…</p>}
        {letters?.length === 0 && <p className="muted">No letters yet.</p>}
        <ul className="letters">
          {letters?.map((letter) => (
            <li key={letter.id}>
              <Link to={`/letters/${letter.id}`} className="card letter-row">
                <div>
                  <strong>{letter.sender}</strong>
                  <div className="small muted">
                    {LETTER_TYPE[letter.letter_type] ?? letter.letter_type} · added {formatDate(letter.created_at)}
                  </div>
                </div>
                <div className="right small">
                  {letter.next_deadline
                    ? <span>Next: {formatDate(letter.next_deadline)} ({inDays(letter.next_deadline)})</span>
                    : <span className="muted">No upcoming deadline</span>}
                  {letter.warned && <span className="badge danger">Suspicious text</span>}
                  {letter.unsure > 0 && <span className="badge warn">{letter.unsure} to check</span>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
