import { useMemo } from 'react'
import type { Data, Shape } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import { selectedTrackIds } from './selectionToRule'
import type { ReleaseVsAddedRow } from '../../api/hooks'

/** Release-year vs added-year scatter. Lasso/box-select dots to capture their tracks as a selection; double-click clears. */
export function ReleaseVsAddedScatter({ rows, onTracks }: { rows: ReleaseVsAddedRow[]; onTracks: (ids: string[]) => void }) {
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'scattergl',
        mode: 'markers',
        x: rows.map((r) => r.release_year),
        y: rows.map((r) => r.added_year),
        customdata: rows.map((r) => r.track_id),
        text: rows.map((r) => `${r.track} — ${r.artist}`),
        marker: { color: CHART.blue, size: 7, opacity: 0.35 },
        selected: { marker: { color: CHART.blueSelected, opacity: 0.9 } },
        unselected: { marker: { opacity: 0.12 } },
        hovertemplate: '%{text}<br>released %{x}, added %{y}<extra></extra>',
      },
    ],
    [rows],
  )
  const diagonal = useMemo<Partial<Shape> | null>(() => {
    if (rows.length === 0) return null
    const lo = Math.min(...rows.map((r) => r.release_year))
    const hi = Math.max(...rows.map((r) => r.added_year))
    return { type: 'line', x0: lo, y0: lo, x1: hi, y1: hi, line: { color: CHART.axis, width: 1, dash: 'dash' } }
  }, [rows])
  const layout = useMemo(
    () =>
      baseLayout({
        height: 420,
        dragmode: 'lasso',
        shapes: diagonal !== null ? [diagonal] : [],
        xaxis: { title: { text: 'release year', font: { color: CHART.muted, size: 11 } }, gridcolor: CHART.grid, zeroline: false },
        yaxis: { title: { text: 'added year', font: { color: CHART.muted, size: 11 } }, gridcolor: CHART.grid, zeroline: false },
      }),
    [diagonal],
  )
  return <PlotlyChart data={data} layout={layout} onSelected={(event) => onTracks(selectedTrackIds(event))} onDeselect={() => onTracks([])} />
}
