/**
 * Build a shareable/bookmarkable URL that reproduces a submitted search.
 *
 * Mirrors `readUrlSeed` in `components/BirthForm.tsx` exactly — every param
 * name here is one that function knows how to read back. Keep the two in
 * sync if either changes.
 */

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
