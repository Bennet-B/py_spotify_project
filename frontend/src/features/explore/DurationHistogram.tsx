import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import { selectedDurationRangeSeconds } from './selectionToRule'
import type { TrackRow } from '../../api/hooks'

/** Track-duration histogram (client-side binning over the loaded rows). Drag a box to select a duration range; double-click clears. */
export function DurationHistogram({ tracks, onRange }: { tracks: TrackRow[]; onRange: (range: [number, number] | null) => void }) {
  const data = useMemo<Data[]>(() => {
    const minutes = tracks.map((t) => t.duration_ms / 60_000)
    const end = minutes.length > 0 ? Math.ceil(Math.max(...minutes)) : 10
    return [
      {
        type: 'histogram',
        x: minutes,
        xbins: { start: 0, end, size: 0.25 },
        marker: { color: CHART.blue, opacity: 0.9 },
        hovertemplate: '%{x} min: %{y} tracks<extra></extra>',
      },
    ]
  }, [tracks])
  const layout = useMemo(
    () =>
      baseLayout({
        height: 260,
        dragmode: 'select',
        selectdirection: 'h',
        xaxis: { title: { text: 'minutes', font: { color: CHART.muted, size: 11 } }, gridcolor: CHART.grid, zeroline: false },
        bargap: 0.05,
      }),
    [],
  )
  return <PlotlyChart data={data} layout={layout} onSelected={(event) => onRange(selectedDurationRangeSeconds(event))} onDeselect={() => onRange(null)} />
}
