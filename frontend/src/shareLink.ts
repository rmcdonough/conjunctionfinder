/**
 * Build shareable URLs: one that reproduces a submitted search in this app
 * (query params BirthForm.tsx's readUrlSeed knows how to read back), and one
 * that is a public .ics calendar feed URL for the backend's subscription
 * endpoint (GET /api/conjunctions.ics — a different shape, and a different
 * origin, from the app's own URL).
 */

import { API_BASE_URL } from './api'
import type { ConjunctionsRequest } from './types'

export function buildShareableUrl(request: ConjunctionsRequest): string {
  const params = new URLSearchParams()

  if (request.name) params.set('name', request.name)
  params.set('birth_date', request.birth_date)
  params.set('birth_time', request.birth_time)

  // Both are sent independently of each other: birth_place is kept even when
  // manual coordinates were used, since it's still shown as a display label
  // in that case (see BirthForm's request-building and readUrlSeed).
  if (request.birth_place) params.set('birth_place', request.birth_place)
  if (request.latitude != null && request.longitude != null) {
    params.set('latitude', String(request.latitude))
    params.set('longitude', String(request.longitude))
  }

  params.set('end_year', String(request.end_year))
  params.set('bodies', request.bodies.join(','))

  const { origin, pathname } = window.location
  return `${origin}${pathname}?${params.toString()}`
}

/**
 * Build the public, subscribable .ics feed URL for this birth data — no
 * search-window params, since the backend endpoint has its own fixed rolling
 * window (1 month back, 6 months ahead) that keeps moving forward every time
 * a calendar client re-fetches the URL. `bodies` is repeated once per value
 * (`?bodies=moon&bodies=sun`) to match FastAPI's query-list convention,
 * unlike the comma-joined form `buildShareableUrl` uses for this app's own
 * `?bodies=moon,sun` parsing.
 */
export function buildIcsFeedUrl(request: ConjunctionsRequest): string {
  const params = new URLSearchParams()

  if (request.name) params.set('name', request.name)
  params.set('birth_date', request.birth_date)
  params.set('birth_time', request.birth_time)
  if (request.birth_place) params.set('birth_place', request.birth_place)
  if (request.latitude != null && request.longitude != null) {
    params.set('latitude', String(request.latitude))
    params.set('longitude', String(request.longitude))
  }
  for (const body of request.bodies) params.append('bodies', body)

  return `${API_BASE_URL}/api/conjunctions.ics?${params.toString()}`
}
