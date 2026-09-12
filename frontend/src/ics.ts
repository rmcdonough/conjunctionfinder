import { API_BASE_URL } from './api'
import type { ConjunctionEvent } from './types'

/**
 * URL for a single conjunction event's .ics file, served by the backend
 * (`GET /api/conjunction-event.ics`) rather than built client-side as a
 * `data:` URI.
 *
 * The client-side `data:` URI approach downloaded fine on desktop browsers,
 * but iOS Safari does not honour the anchor `download` attribute on `data:`
 * URIs — tapping the link there did nothing. A real HTTP link to a
 * `text/calendar` resource works everywhere, including iOS Safari's native
 * "tap a .ics link -> Add to Calendar" flow (supported since iOS 5). The
 * server names the actual downloaded file via its Content-Disposition
 * header (see `single_event_ics_filename` in backend/app/ics.py).
 */
export function conjunctionEventIcsUrl(event: ConjunctionEvent): string {
  const params = new URLSearchParams({
    transiting_body: event.transiting_body,
    natal_key: event.natal_key,
    natal_label: event.natal_label,
    utc: event.utc,
  })
  return `${API_BASE_URL}/api/conjunction-event.ics?${params.toString()}`
}
