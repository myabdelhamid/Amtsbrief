// Mirrors backend/pipeline/schemas.py and backend/app (StoredLetter, LetterSummary).

export type LineId = string // "P1-L9" = page 1, line 9

export interface Cited {
  value: string
  quote: string
  lines: LineId[]
}

export type Purpose = 'payment' | 'objection' | 'appointment' | 'other'

export interface RawDeadline {
  phrase: string
  kind: 'absolute' | 'relative' | 'unsupported'
  summary: string
  purpose: Purpose
  lines: LineId[]
}

export interface ResolvedDeadline {
  date: string // ISO, "2026-11-24"
  summary: string
  purpose: Purpose
  steps: string[]
  lines: LineId[]
}

export interface Claim {
  text: string
  lines: LineId[]
}

export interface Extraction {
  letter_type: string
  sender: Cited
  letter_date: Cited
  amount: Cited | null
  reference: Cited | null
  iban: Cited | null
  deadlines: RawDeadline[]
  explanation: Claim[]
}

export interface Issue {
  field: string // "iban", "deadlines[1]", "explanation[0]"
  problem: string
  retry: boolean
}

export interface ValidatedResult {
  extraction: Extraction
  deadlines: ResolvedDeadline[]
  unsure: Issue[]
  suspicious: LineId[]
  retried: boolean
}

export interface StoredLetter {
  id: string
  created_at: string
  analysis: {
    transcript: { lines: Record<LineId, string> }
    result: ValidatedResult
    pages: number
  }
}

export interface LetterSummary {
  id: string
  created_at: string
  letter_type: string
  sender: string
  next_deadline: string | null
  unsure: number
  warned: boolean
}
