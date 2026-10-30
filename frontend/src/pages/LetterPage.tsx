// One letter: the warning, the facts with their sources, deadlines, explanation,
// what couldn't be verified, and the transcript the line IDs point into.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, deleteLetter, downloadDeadline, getLetter } from '../api'
import { useAuth } from '../auth'
import { LETTER_TYPE, PURPOSE, formatDate, inDays } from '../format'
import type { Cited, LineId, StoredLetter } from '../types'

const FIELDS: [keyof Pick<StoredLetter['analysis']['result']['extraction'],
  'sender' | 'letter_date' | 'amount' | 'reference' | 'iban'>, string][] = [
  ['sender', 'From'],
  ['letter_date', 'Letter date'],
  ['amount', 'Amount'],
  ['reference', 'Reference'],
  ['iban', 'Pay into (IBAN)'],
]

function Sources({ lines, onShow }: { lines: LineId[]; onShow: (lines: LineId[]) => void }) {
  return (
    <button className="source" onClick={() => onShow(lines)} title="Show in the letter">
      {lines.join(', ')}
    </button>
  )
}

export default function LetterPage() {
  const { id } = useParams()
  const { session } = useAuth()
  const token = session!.token
  const navigate = useNavigate()
  const [letter, setLetter] = useState<StoredLetter | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<LineId[]>([])
  const transcriptRef = useRef<HTMLElement>(null)

  useEffect(() => {
    getLetter(token, id!).then(setLetter).catch((e) =>
      setError(e instanceof ApiError && e.status === 404 ? 'This letter doesn’t exist or was deleted.' : 'Couldn’t load the letter.'))
  }, [token, id])

  if (error) return <p className="error">{error} <Link to="/">Back to your letters</Link></p>
  if (!letter) return <p className="muted">Loading…</p>

  const { transcript, result } = letter.analysis
  const { extraction } = result
  const unsure = new Map(result.unsure.map((issue) => [issue.field, issue]))
  const suspicious = new Set(result.suspicious)

  function show(lines: LineId[]) {
    setHighlight(lines)
    document.getElementById(`line-${lines[0]}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function remove() {
    if (!confirm('Delete this letter? This can’t be undone.')) return
    await deleteLetter(token, letter!.id)
    navigate('/')
  }

  const upcoming = [...result.deadlines.entries()].sort(([, a], [, b]) => a.date.localeCompare(b.date))
  const unverifiedDeadlines = extraction.deadlines.flatMap((deadline, i) => {
    const issue = unsure.get(`deadlines[${i}]`)
    return issue ? [{ deadline, issue }] : []
  })

  return (
    <>
      <p><Link to="/">← Your letters</Link></p>
      <h1>{extraction.sender.value}</h1>
      <p className="muted">{LETTER_TYPE[extraction.letter_type] ?? extraction.letter_type} · {letter.analysis.pages} page(s)</p>

      {result.suspicious.length > 0 && (
        <div className="alert danger" role="alert">
          <strong>This letter contains text aimed at automated readers.</strong> Lines{' '}
          <Sources lines={result.suspicious} onShow={show} /> try to give instructions to an AI. Real
          authorities don’t write this. Amtsbrief ignored that text, but treat the letter with suspicion and check
          any bank details or phone numbers with the sender through a channel you already know.
        </div>
      )}

      <section className="card">
        <h2>What it says</h2>
        <ul className="claims">
          {extraction.explanation.map((claim, i) => (
            <li key={i} className={unsure.has(`explanation[${i}]`) ? 'unsure' : ''}>
              {claim.text} <Sources lines={claim.lines} onShow={show} />
              {unsure.has(`explanation[${i}]`) && <span className="badge warn">Couldn’t verify</span>}
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Deadlines</h2>
        {upcoming.length === 0 && <p className="muted">No deadline could be calculated from this letter.</p>}
        <ul className="deadlines">
          {upcoming.map(([index, deadline]) => (
            <li key={index}>
              <div className="row between">
                <div>
                  <div className="small muted">{PURPOSE[deadline.purpose]}</div>
                  <strong>{formatDate(deadline.date)}</strong> <span className="muted">({inDays(deadline.date)})</span>
                </div>
                <button onClick={() => downloadDeadline(token, letter.id, index)}>Add to calendar</button>
              </div>
              <p>{deadline.summary} <Sources lines={deadline.lines} onShow={show} /></p>
              <details>
                <summary className="small">How this date was calculated</summary>
                <ol className="small">{deadline.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
              </details>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Details</h2>
        <dl className="facts">
          {FIELDS.map(([name, label]) => {
            const cited: Cited | null = extraction[name]
            if (!cited) return null
            return (
              <div key={name} className={unsure.has(name) ? 'unsure' : ''}>
                <dt>{label}</dt>
                <dd>
                  {cited.value} <Sources lines={cited.lines} onShow={show} />
                  {unsure.has(name) && <span className="badge warn">Couldn’t verify</span>}
                </dd>
              </div>
            )
          })}
        </dl>
      </section>

      {(unverifiedDeadlines.length > 0 || result.unsure.length > 0) && (
        <section className="card warn-card">
          <h2>Couldn’t verify</h2>
          <p className="small">
            These couldn’t be checked against the letter, so they aren’t shown as fact and get no reminder. Read
            the cited lines yourself.
          </p>
          <ul>
            {unverifiedDeadlines.map(({ deadline, issue }, i) => (
              <li key={`d${i}`}>
                Deadline: “{deadline.phrase}” <Sources lines={deadline.lines} onShow={show} />
                <div className="small muted">{issue.problem}</div>
              </li>
            ))}
            {result.unsure.filter((issue) => !issue.field.startsWith('deadlines[')).map((issue) => (
              <li key={issue.field}>
                {issue.field}: <span className="small muted">{issue.problem}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card" ref={transcriptRef}>
        <h2>The letter, line by line</h2>
        <ol className="transcript">
          {Object.entries(transcript.lines).map(([lineId, text]) => (
            <li
              key={lineId}
              id={`line-${lineId}`}
              className={[highlight.includes(lineId) ? 'hl' : '', suspicious.has(lineId) ? 'suspicious' : ''].join(' ')}
            >
              <span className="line-id">{lineId}</span> {text}
            </li>
          ))}
        </ol>
      </section>

      <p><button className="danger-button" onClick={remove}>Delete this letter</button></p>
    </>
  )
}
