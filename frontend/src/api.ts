// Calls to the FastAPI backend. Every call sends the signed-in user's ID token.
import type { LetterSummary, StoredLetter } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Token = () => Promise<string | null>

async function request(token: Token, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const idToken = await token()
  if (idToken) headers.set('Authorization', `Bearer ${idToken}`)
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    // FastAPI errors look like {"detail": "..."}; fall back to the status text.
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, typeof body?.detail === 'string' ? body.detail : response.statusText)
  }
  return response
}

export async function uploadLetter(token: Token, file: File): Promise<StoredLetter> {
  const form = new FormData()
  form.append('file', file)
  return (await request(token, '/api/letters', { method: 'POST', body: form })).json()
}

export async function listLetters(token: Token): Promise<LetterSummary[]> {
  return (await request(token, '/api/letters')).json()
}

export async function getLetter(token: Token, id: string): Promise<StoredLetter> {
  return (await request(token, `/api/letters/${id}`)).json()
}

export async function deleteLetter(token: Token, id: string): Promise<void> {
  await request(token, `/api/letters/${id}`, { method: 'DELETE' })
}

export async function feedUrl(token: Token): Promise<string> {
  return (await (await request(token, '/api/calendar')).json()).url
}

/** Download one deadline as an .ics file. A plain link can't carry the sign-in token. */
export async function downloadDeadline(token: Token, letterId: string, index: number): Promise<void> {
  const blob = await (await request(token, `/api/letters/${letterId}/deadlines/${index}.ics`)).blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'deadline.ics'
  link.click()
  URL.revokeObjectURL(url)
}
