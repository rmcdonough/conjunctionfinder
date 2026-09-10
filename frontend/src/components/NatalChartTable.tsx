import { useState } from 'react'
import { formatIsoInOwnZone, isoOffsetLabel } from '../dates'
import type { NatalChart, NatalPointCategory } from '../types'

const CATEGORY_LABEL: Record<NatalPointCategory, string> = {
  luminary: 'Luminary',
  planet: 'Planet',
  node: 'Node',
  house: 'House cusp',
}

/** A read-only URL field with a one-click copy button. */
function ShareLinkField({
  label,
  url,
  hint,
  ariaLabel,
}: {
  label: string
  url: string
  hint: string
  ariaLabel: string
}) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API can be unavailable (e.g. insecure context); the field
      // is still selectable text, so manual copy always works as a fallback.
    }
  }

  return (
    <div className="share-link">
      <span className="share-link-label">{label}</span>
      <div className="share-link-row">
        <input
          type="text"
          readOnly
          value={url}
          onFocus={(e) => e.currentTarget.select()}
          aria-label={ariaLabel}
        />
        <button type="button" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <p className="hint">{hint}</p>
    </div>
  )
}

export function NatalChartTable({
  chart,
  shareUrl,
  icsFeedUrl,
}: {
  chart: NatalChart
  shareUrl: string
  icsFeedUrl: string
}) {
  return (
    <section className="card">
      <h2>Natal chart</h2>
      <p className="hint">
        Check these against what you expect before trusting the conjunction list
        — if the resolved place or timezone is wrong, everything below it is too.
      </p>

      <dl className="resolved">
        {(shareUrl || icsFeedUrl) && (
          <div className="resolved-share">
            {shareUrl && (
              <ShareLinkField
                label="Shareable link"
                url={shareUrl}
                ariaLabel="Shareable link for this search"
                hint="Pre-fills the form with this birth data and search window — save it or send it to reproduce this exact search."
              />
            )}
            {icsFeedUrl && (
              <ShareLinkField
                label="Calendar subscription (.ics)"
                url={icsFeedUrl}
                ariaLabel="Public calendar subscription URL for these conjunctions"
                hint="Paste into Google Calendar, Outlook, or Apple Calendar's “subscribe by URL” field. Publicly accessible to anyone with this link — always covers 1 month back to 6 months ahead of today, updating automatically each time your calendar app refreshes it."
              />
            )}
          </div>
        )}
        <div>
          <dt>Resolved place</dt>
          <dd>{chart.resolved_place}</dd>
        </div>
        <div>
          <dt>Coordinates</dt>
          <dd>
            {chart.latitude.toFixed(4)}°, {chart.longitude.toFixed(4)}°
          </dd>
        </div>
        <div>
          <dt>Timezone</dt>
          <dd>{chart.timezone}</dd>
        </div>
        <div>
          <dt>Birth moment (local)</dt>
          <dd>
            {formatIsoInOwnZone(chart.birth_datetime_local)}{' '}
            <span className="muted">
              {isoOffsetLabel(chart.birth_datetime_local)}
            </span>
          </dd>
        </div>
        <div>
          <dt>Birth moment (UTC)</dt>
          <dd>{formatIsoInOwnZone(chart.birth_datetime_utc)}</dd>
        </div>
      </dl>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Point</th>
              <th scope="col">Type</th>
              <th scope="col">Sign &amp; degree</th>
              <th scope="col">Longitude</th>
              <th scope="col">Retrograde</th>
            </tr>
          </thead>
          <tbody>
            {chart.points.map((point) => (
              <tr key={point.key} className={`row-${point.category}`}>
                <th scope="row">{point.key}</th>
                <td className="muted">{CATEGORY_LABEL[point.category]}</td>
                <td className="mono">{point.label}</td>
                <td className="mono numeric">{point.longitude.toFixed(4)}°</td>
                <td>
                  {point.retrograde ? (
                    <span className="retro" title="Retrograde">
                      ℞
                    </span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Houses are Placidus. &ldquo;Dragon&rsquo;s Head&rdquo; is the mean lunar
        node and &ldquo;Dragon&rsquo;s Tail&rdquo; the point opposite it; neither
        is flagged retrograde even though the node always moves backwards.
      </p>
    </section>
  )
}
