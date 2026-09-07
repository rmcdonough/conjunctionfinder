import type { ConjunctionsRequest, ConjunctionsResponse } from './types'

/**
 * Backend base URL. Set VITE_API_BASE_URL in .env (or the deploy environment)
 * to point at something other than a local uvicorn.
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** A 422 validation error entry from FastAPI/Pydantic. */
interface ValidationDetail {
  loc?: (string | number)[]
  msg?: string
}

/**
 * Turn a FastAPI error body into one readable sentence.
 *
 * The backend answers with either `{"detail": "message"}` (our own 400s) or
 * `{"detail": [{loc, msg}, ...]}` (Pydantic 422s). Pydantic prefixes custom
 * validator messages with "Value error, ", which is noise to a user.
 */
function formatError(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = (detail as ValidationDetail[])
      .map((entry) => {
        const msg = (entry.msg ?? '').replace(/^Value error,\s*/, '')
        // Skip the "body" prefix Pydantic puts on every request-body location.
        const field = (entry.loc ?? []).filter((p) => p !== 'body').join('.')
        return field && !msg.toLowerCase().includes(field.toLowerCase())
          ? `${field}: ${msg}`
          : msg
      })
      .filter(Boolean)
    if (messages.length) return messages.join(' — ')
  }

  return `Request failed with status ${status}.`
}

export async function fetchConjunctions(
  request: ConjunctionsRequest,
): Promise<ConjunctionsResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/conjunctions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  } catch {
    throw new Error(
      `Could not reach the backend at ${API_BASE_URL}. Is it running? ` +
        '(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000)',
    )
  }

  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // Non-JSON error body (e.g. a proxy's HTML page) — fall through.
    }
    throw new Error(formatError(response.status, body))
  }

  return (await response.json()) as ConjunctionsResponse
}
