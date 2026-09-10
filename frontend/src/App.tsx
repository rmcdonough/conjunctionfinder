import { useState } from 'react'
import './App.css'
import { API_BASE_URL, fetchConjunctions } from './api'
import { BirthForm } from './components/BirthForm'
import { EventsTable } from './components/EventsTable'
import { NatalChartTable } from './components/NatalChartTable'
import { buildShareableUrl } from './shareLink'
import type { ConjunctionsRequest, ConjunctionsResponse } from './types'

export default function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ConjunctionsResponse | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [shareUrl, setShareUrl] = useState('')

  async function handleSubmit(request: ConjunctionsRequest, name: string) {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchConjunctions(request)
      setResult(response)
      setDisplayName(name)
      // Built from the request that was actually sent, not the response, so
      // it reproduces this exact search even if the backend re-derives some
      // display fields (e.g. resolved_place) differently on a later run.
      setShareUrl(buildShareableUrl(request))
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="masthead">
        <h1>
          <span className="glyph" aria-hidden="true">
            ☾
          </span>{' '}
          Conjunction Finder
        </h1>
        <p>
          Enter a birth date, time and place. This computes the natal chart, then
          finds every moment in your chosen window when the transiting Moon or Sun
          crosses one of its points — planets, luminaries, the lunar nodes, Chiron
          or a house cusp.
        </p>
      </header>

      <main>
        <BirthForm loading={loading} onSubmit={handleSubmit} />

        {error && (
          <div className="card error-card" role="alert">
            <h2>Couldn&rsquo;t run that search</h2>
            <p>{error}</p>
          </div>
        )}

        {loading && (
          <div className="card loading" aria-live="polite">
            Computing the chart and scanning the window…
          </div>
        )}

        {result && !loading && (
          <>
            {displayName && (
              <h2 className="for-name">Results for {displayName}</h2>
            )}
            <NatalChartTable chart={result.natal_chart} shareUrl={shareUrl} />
            <EventsTable result={result} />
          </>
        )}
      </main>

      <footer>
        <p>
          Positions from the Swiss Ephemeris via pyswisseph. Houses are Placidus.
          Nothing you enter is stored — the backend at <code>{API_BASE_URL}</code>{' '}
          has no database.
        </p>
      </footer>
    </div>
  )
}
