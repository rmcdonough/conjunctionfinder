import { browserMonthLabel, browserOffsetLabel, formatBrowserLocal, isoMonthLabel } from '../dates'
import { buildConjunctionIcsDataUri, icsFileName } from '../ics'
import type { ConjunctionEvent, ConjunctionsResponse } from '../types'

const BODY_GLYPH: Record<ConjunctionEvent['transiting_body'], string> = {
  moon: '☾',
  sun: '☉',
}

const BODY_NAME: Record<ConjunctionEvent['transiting_body'], string> = {
  moon: 'Moon',
  sun: 'Sun',
}

/**
 * Group events under a month heading, keyed by their month in the BROWSER's
 * own local timezone (matching the sole timestamp column shown per row). A
 * conjunction near a month boundary can therefore land under a different
 * month than it would in UTC or the birth location's timezone — that is
 * genuinely when it happened for whoever is looking at the screen.
 */
function groupByLocalMonth(
  events: ConjunctionEvent[],
): { month: string; events: ConjunctionEvent[] }[] {
  const groups: { month: string; events: ConjunctionEvent[] }[] = []
  for (const event of events) {
    const month = browserMonthLabel(event.utc)
    const last = groups[groups.length - 1]
    if (last && last.month === month) last.events.push(event)
    else groups.push({ month, events: [event] })
  }
  return groups
}

function formatRange(startIso: string, endIso: string): string {
  return `${isoMonthLabel(`${startIso}T00:00:00`)} – ${isoMonthLabel(`${endIso}T00:00:00`)}`
}

export function EventsTable({ result }: { result: ConjunctionsResponse }) {
  const { events, bodies } = result
  const bodyNames = bodies.map((b) => BODY_NAME[b]).join(' and ')
  const groups = groupByLocalMonth(events)

  if (events.length === 0) {
    return (
      <section className="card">
        <h2>Conjunctions</h2>
        <p className="empty">
          No {bodyNames} conjunctions found between{' '}
          {formatRange(result.range_start, result.range_end)}.
        </p>
        <p className="hint">
          The Sun only meets each natal point once a year, so a short window can
          genuinely come up empty. Widen the range, or add the Moon — it crosses
          every natal point about once a month.
        </p>
      </section>
    )
  }

  return (
    <section className="card">
      <h2>
        Conjunctions{' '}
        <span className="count">
          {events.length} event{events.length === 1 ? '' : 's'}
        </span>
      </h2>
      <p className="hint">
        Transiting {bodyNames} over natal points,{' '}
        {formatRange(result.range_start, result.range_end)}. Times are shown
        in your browser&rsquo;s own local timezone.
      </p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Local time</th>
              <th scope="col">Transiting</th>
              <th scope="col">Natal point</th>
              <th scope="col">Natal position</th>
              <th scope="col">Calendar invite</th>
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.month}>
              <tr className="month-heading">
                <th scope="colgroup" colSpan={5}>
                  {group.month}
                  <span className="count">
                    {group.events.length} event
                    {group.events.length === 1 ? '' : 's'}
                  </span>
                </th>
              </tr>
              {group.events.map((event) => (
                <tr key={`${event.transiting_body}-${event.natal_key}-${event.utc}`}>
                  <td className="mono">
                    {formatBrowserLocal(event.utc)}{' '}
                    <span className="muted">
                      {browserOffsetLabel(event.utc, { short: true })}
                    </span>
                  </td>
                  <td>
                    <span className="glyph" aria-hidden="true">
                      {BODY_GLYPH[event.transiting_body]}
                    </span>{' '}
                    {BODY_NAME[event.transiting_body]}
                  </td>
                  <th scope="row">{event.natal_key}</th>
                  <td className="mono">{event.natal_label}</td>
                  <td>
                    <a
                      href={buildConjunctionIcsDataUri(event)}
                      download={icsFileName(event)}
                    >
                      Link
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </section>
  )
}
