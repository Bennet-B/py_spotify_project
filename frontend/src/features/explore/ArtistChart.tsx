import { useMemo } from 'react'
import type { Data, PlotMouseEvent } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import type { ArtistCountRow } from '../../api/hooks'
import type { ArtistSelection } from '../../state/store'

/** Horizontal artist bars, re-scoped by the current genre selection; clicks toggle artists into the selection. */
export function ArtistChart({ rows, selected, onToggle }: { rows: ArtistCountRow[]; selected: ArtistSelection[]; onToggle: (artist: ArtistSelection) => void }) {
  const selectedIds = useMemo(() => new Set(selected.map((a) => a.id)), [selected])
  const anySelection = selectedIds.size > 0
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((r) => r.track_count),
        y: rows.map((r) => r.artist_name),
        customdata: rows.map((r) => r.artist_id),
        marker: {
          color: rows.map((r) => (selectedIds.has(r.artist_id) ? CHART.blueSelected : CHART.blue)),
          opacity: rows.map((r) => (!anySelection || selectedIds.has(r.artist_id) ? 0.9 : CHART.dimOpacity)),
          cornerradius: 4,
        },
        hovertemplate: '%{y}: %{x} tracks<extra></extra>',
      },
    ],
    [rows, selectedIds, anySelection],
  )
  const layout = useMemo(
    () =>
      baseLayout({
        height: Math.max(220, 28 + rows.length * 21),
        margin: { l: 150, r: 12, t: 4, b: 28 },
        yaxis: { autorange: 'reversed', tickfont: { color: CHART.ink, size: 11 }, gridcolor: CHART.surface },
        xaxis: { gridcolor: CHART.grid, tickfont: { color: CHART.muted }, zeroline: false },
        bargap: 0.25,
      }),
    [rows.length],
  )

  function handleClick(event: PlotMouseEvent) {
    const point = event.points?.[0]
    const id = typeof point?.customdata === 'string' ? point.customdata : null
    const name = typeof point?.y === 'string' ? point.y : null
    if (id !== null && name !== null) onToggle({ id, name })
  }

  return <PlotlyChart data={data} layout={layout} onPointClick={handleClick} />
}
