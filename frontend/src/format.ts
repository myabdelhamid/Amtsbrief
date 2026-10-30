// Labels and formatting shared by the pages.
import type { Purpose } from './types'

export const LETTER_TYPE: Record<string, string> = {
  tax: 'Tax office',
  registration: 'Registration office',
  health_insurance: 'Health insurance',
  landlord: 'Landlord',
  fine: 'Fine',
  other: 'Other',
}

export const PURPOSE: Record<Purpose, string> = {
  payment: 'Payment due',
  objection: 'Last day to object',
  appointment: 'Appointment',
  other: 'Deadline',
}

/** "2026-11-24" -> "Tue, 24 Nov 2026". Parsed as a local date, never shifted by time zone. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

/** Whole days from today until an ISO date; negative when it has passed. */
export function daysUntil(iso: string): number {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((new Date(year, month - 1, day).getTime() - start.getTime()) / 86_400_000)
}

export function inDays(iso: string): string {
  const days = daysUntil(iso)
  if (days < 0) return 'passed'
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  return `in ${days} days`
}
