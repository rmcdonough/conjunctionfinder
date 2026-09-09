/** Month/date helpers shared by the form and the results tables. */

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export interface MonthYear {
  year: number
  month: number // 1-12
}

/** Months since year 0 — makes span arithmetic across a year boundary trivial. */
export function monthIndex({ year, month }: MonthYear): number {
  return year * 12 + (month - 1)
}

/** Inclusive span in months, so Jan→Jan is 1 and Jan→Dec is 12. */
export function monthSpan(start: MonthYear, end: MonthYear): number {
  return monthIndex(end) - monthIndex(start) + 1
}

export function addMonths({ year, month }: MonthYear, delta: number): MonthYear {
  const index = year * 12 + (month - 1) + delta
  return { year: Math.floor(index / 12), month: (index % 12) + 1 }
}

export function currentMonthYear(): MonthYear {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}

/**
 * Format an ISO 8601 timestamp that already carries the offset we want to show.
 *
 * The backend sends each event twice — once in UTC and once in the birth
 * location's timezone — so we must NOT re-interpret either in the browser's
 * local timezone. We therefore read the string's own fields instead of letting
 * `Date` shift them.
 */
export function formatIsoInOwnZone(
  iso: string,
  { weekday = true }: { weekday?: boolean } = {},
): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso)
  if (!match) return iso
  const [, year, month, day, hour, minute, second] = match
  const monthName = MONTH_NAMES[Number(month) - 1].slice(0, 3)
  const stamp = `${day} ${monthName} ${year}, ${hour}:${minute}:${second ?? '00'}`
  if (!weekday) return stamp
  // Build the date as UTC so no local-timezone shift can move the weekday.
  const dayName = new Date(
    Date.UTC(Number(year), Number(month) - 1, Number(day)),
  ).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  return `${dayName} ${stamp}`
}

/** "June 2026" heading for the month an ISO timestamp falls in. */
export function isoMonthLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(iso)
  if (!match) return iso
  return `${MONTH_NAMES[Number(match[2]) - 1]} ${match[1]}`
}

/**
 * UTC offset as carried by the ISO string, e.g. "UTC-04:00".
 *
 * `short` drops the "UTC" prefix, for table rows where the column header
 * already names the timezone — the offset itself still matters there because it
 * changes across a DST transition inside the search window.
 */
export function isoOffsetLabel(iso: string, { short = false } = {}): string {
  if (iso.endsWith('Z') || iso.endsWith('+00:00')) return short ? '+00:00' : 'UTC'
  const match = /([+-]\d{2}:\d{2})$/.exec(iso)
  if (!match) return ''
  return short ? match[1] : `UTC${match[1]}`
}

/**
 * Format a real UTC instant in the BROWSER's own local timezone.
 *
 * Unlike `formatIsoInOwnZone` (which trusts the offset already embedded in
 * the string and must NOT be reinterpreted — used when we want the birth
 * location's wall-clock time regardless of who's viewing), this one
 * deliberately lets `Date`'s local getters (`getHours`, `getDate`, ...)
 * apply whatever timezone the visitor's device is set to. `event.utc` is
 * always a genuine UTC instant (suffixed `Z` or `+00:00`), so reinterpreting
 * it this way is safe and correct.
 */
export function formatBrowserLocal(
  utcIso: string,
  { weekday = true }: { weekday?: boolean } = {},
): string {
  const date = new Date(utcIso)
  if (Number.isNaN(date.getTime())) return utcIso
  const day = String(date.getDate()).padStart(2, '0')
  const monthName = MONTH_NAMES[date.getMonth()].slice(0, 3)
  const year = date.getFullYear()
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  const stamp = `${day} ${monthName} ${year}, ${hour}:${minute}:${second}`
  if (!weekday) return stamp
  const dayName = date.toLocaleDateString('en-US', { weekday: 'short' })
  return `${dayName} ${stamp}`
}

/** UTC offset of the BROWSER's own timezone for a given instant, e.g. "-04:00". */
export function browserOffsetLabel(utcIso: string, { short = false } = {}): string {
  const date = new Date(utcIso)
  if (Number.isNaN(date.getTime())) return ''
  const totalMinutes = -date.getTimezoneOffset()
  const sign = totalMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(totalMinutes)
  const hh = String(Math.floor(abs / 60)).padStart(2, '0')
  const mm = String(abs % 60).padStart(2, '0')
  const offset = `${sign}${hh}:${mm}`
  return short ? offset : `UTC${offset}`
}

/** "June 2026" heading for the month a UTC instant falls in, in the BROWSER's own timezone. */
export function browserMonthLabel(utcIso: string): string {
  const date = new Date(utcIso)
  if (Number.isNaN(date.getTime())) return utcIso
  return `${MONTH_NAMES[date.getMonth()]} ${date.getFullYear()}`
}
