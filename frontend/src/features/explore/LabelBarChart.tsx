import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import { clickedBarLabel } from './selectionToRule'
import type { LabelCountRow } from '../../api/hooks'

/** Horizontal frequency bars whose clicks toggle labels in/out of a selection (genres → bucket tag rules). */
export function LabelBarChart({ rows, selected, onToggle }: { rows: LabelCountRow[]; selected: string[]; onToggle: (label: string) => void }) {
  const anySelection = selected.length > 0
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        orientation: 'h',
        x: rows.map((r) => r.count),
        y: rows.map((r) => r.label),
        marker: {
          color: rows.map((r) => (selected.includes(r.label) ? CHART.blueSelected : CHART.blue)),
          opacity: rows.map((r) => (!anySelection || selected.includes(r.label) ? 0.9 : CHART.dimOpacity)),
          cornerradius: 4,
        },
        hovertemplate: '%{y}: %{x} tracks<extra></extra>',
      },
    ],
    [rows, selected, anySelection],
  )
  const layout = useMemo(
    () =>
      baseLayout({
        height: Math.max(220, 28 + rows.length * 21),
        margin: { l: 130, r: 12, t: 4, b: 28 },
        yaxis: { autorange: 'reversed', tickfont: { color: CHART.ink, size: 11 }, gridcolor: CHART.surface },
        xaxis: { gridcolor: CHART.grid, tickfont: { color: CHART.muted }, zeroline: false },
        bargap: 0.25,
      }),
    [rows.length],
  )
  return <PlotlyChart data={data} layout={layout} onPointClick={(event) => (clickedBarLabel(event, 'h') !== null ? onToggle(clickedBarLabel(event, 'h')!) : undefined)} />
}
