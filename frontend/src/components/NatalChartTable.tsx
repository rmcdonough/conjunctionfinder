import { formatIsoInOwnZone, isoOffsetLabel } from '../dates'
import type { NatalChart, NatalPointCategory } from '../types'

const CATEGORY_LABEL: Record<NatalPointCategory, string> = {
  luminary: 'Luminary',
  planet: 'Planet',
  node: 'Node',
  house: 'House cusp',
}

export function NatalChartTable({ chart }: { chart: NatalChart }) {
  return (
    <section className="card">
      <h2>Natal chart</h2>
      <p className="hint">
        Check these against what you expect before trusting the conjunction list
        — if the resolved place or timezone is wrong, everything below it is too.
      </p>

      <dl className="resolved">
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
