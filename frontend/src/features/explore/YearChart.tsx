import { useMemo } from 'react'
import type { Data, PlotMouseEvent } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import { selectedYearRange } from './selectionToRule'
import type { YearCountRow } from '../../api/hooks'

/** Release-year bars (pre-binned server-side). Drag a box to select a year range; click a bar for a single year; double-click clears. */
export function YearChart({ rows, range, onRange }: { rows: YearCountRow[]; range: [number, number] | null; onRange: (range: [number, number] | null) => void }) {
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        x: rows.map((r) => r.year),
        y: rows.map((r) => r.count),
        marker: {
          color: rows.map((r) => (range !== null && r.year >= range[0] && r.year <= range[1] ? CHART.blueSelected : CHART.blue)),
          opacity: rows.map((r) => (range === null || (r.year >= range[0] && r.year <= range[1]) ? 0.9 : CHART.dimOpacity)),
          cornerradius: 2,
        },
        hovertemplate: '%{x}: %{y} tracks<extra></extra>',
      },
    ],
    [rows, range],
  )
  const layout = useMemo(() => baseLayout({ height: 260, dragmode: 'select', selectdirection: 'h' }), [])

  function handleClick(event: PlotMouseEvent) {
    const year = event.points?.[0]?.x
    if (typeof year === 'number') onRange([year, year])
  }

  return <PlotlyChart data={data} layout={layout} onPointClick={handleClick} onSelected={(event) => onRange(selectedYearRange(event))} onDeselect={() => onRange(null)} />
}
