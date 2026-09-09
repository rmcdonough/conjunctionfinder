/**
 * Build a downloadable .ics (RFC 5545) calendar file for a single
 * conjunction event, entirely client-side — no backend round trip, nothing
 * stored anywhere.
 *
 * The event's `utc` field is a real UTC instant, so the .ics uses UTC
 * timestamps (trailing `Z`) throughout. Every calendar client converts
 * those to the viewer's own local time automatically, which matches how
 * the "Local time" column in the results table already behaves.
 */

import type { ConjunctionEvent } from './types'

const BODY_NAME: Record<ConjunctionEvent['transiting_body'], string> = {
  moon: 'Moon',
  sun: 'Sun',
}

/** Conjunctions are instants; give the calendar entry a short visible span. */
const EVENT_DURATION_MINUTES = 30

/** Escape text per RFC 5545 3.3.11 (backslash, semicolon, comma, newline). */
function icsEscapeText(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n')
}

/** UTC `Date` -> ICS `YYYYMMDDTHHMMSSZ` basic format. */
function toIcsUtcStamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z'
}

/** Lowercase, hyphenated, filesystem/URL-safe fragment for filenames and UIDs. */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Suggested download filename for an event's .ics file. */
export function icsFileName(event: ConjunctionEvent): string {
  const bodyName = BODY_NAME[event.transiting_body]
  const dateStamp = event.utc.slice(0, 10) // YYYY-MM-DD
  return `${slugify(bodyName)}-conjunct-${slugify(event.natal_key)}-${dateStamp}.ics`
}

/**
 * Build a `data:` URI holding the .ics content for one conjunction event.
 * Suitable directly as an `<a href>` with a `download` attribute — no Blob
 * lifecycle to manage, and the file is tiny.
 */
export function buildConjunctionIcsDataUri(event: ConjunctionEvent): string {
  const bodyName = BODY_NAME[event.transiting_body]
  const start = new Date(event.utc)
  const end = new Date(start.getTime() + EVENT_DURATION_MINUTES * 60_000)

  const dtStart = toIcsUtcStamp(start)
  const dtEnd = toIcsUtcStamp(end)
  const dtStamp = toIcsUtcStamp(new Date())

  const summary = `${bodyName} conjunct ${event.natal_key}`
  const description = `Transiting ${bodyName} conjuncts natal ${event.natal_key} (${event.natal_label}).`
  const uid = `${slugify(bodyName)}-${slugify(event.natal_key)}-${dtStart}@astrology-conjunction-finder`

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Astrology Conjunction Finder//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${dtStamp}`,
    `DTSTART:${dtStart}`,
    `DTEND:${dtEnd}`,
    `SUMMARY:${icsEscapeText(summary)}`,
    `DESCRIPTION:${icsEscapeText(description)}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ]

  // CRLF line endings per RFC 5545.
  const ics = lines.join('\r\n') + '\r\n'
  return `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}`
}
