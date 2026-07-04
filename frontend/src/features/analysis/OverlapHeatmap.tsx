import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import type { ScanResult } from '../../api/hooks'

// Single-hue sequential ramp (blues) from the validated reference palette — light means low overlap, dark means high.
const BLUES_SCALE: [number, string][] = [
  [0, '#fcfcfb'],
  [0.25, '#cde2fb'],
  [0.5, '#86b6ef'],
  [0.75, '#3987e5'],
  [1, '#104281'],
]

/** Jaccard-overlap heatmap over the scanned playlists; the trivial diagonal stays blank so the scale serves the interesting cells. */
export function OverlapHeatmap({ result }: { result: ScanResult }) {
  const names = useMemo(() => result.playlists.map((p) => p.name), [result.playlists])
  const { z, hover } = useMemo(() => {
    const index = new Map(result.playlists.map((p, i) => [p.id, i]))
    const size = result.playlists.length
    const zMatrix: (number | null)[][] = Array.from({ length: size }, () => Array.from({ length: size }, () => 0))
    const hoverMatrix: string[][] = Array.from({ length: size }, (_, row) => Array.from({ length: size }, (_, col) => (row === col ? '' : `${names[row]} ∩ ${names[col]}: 0 tracks`)))
    for (const pair of result.pairs) {
      const a = index.get(pair.a_id)
      const b = index.get(pair.b_id)
      if (a === undefined || b === undefined) continue
      zMatrix[a][b] = pair.jaccard
      zMatrix[b][a] = pair.jaccard
      const text = `${pair.a_name} ∩ ${pair.b_name}: ${pair.intersection} tracks<br>jaccard ${pair.jaccard.toFixed(2)} · ${Math.round(pair.containment_a_in_b * 100)}% of A in B · ${Math.round(pair.containment_b_in_a * 100)}% of B in A`
      hoverMatrix[a][b] = text
      hoverMatrix[b][a] = text
    }
    for (let i = 0; i < size; i++) zMatrix[i][i] = null
    return { z: zMatrix, hover: hoverMatrix }
  }, [result, names])

  const data = useMemo<Data[]>(
    () => [
      {
        type: 'heatmap',
        x: names,
        y: names,
        z,
        // Heatmaps take per-cell 2D text at runtime; @types/plotly.js only models the 1D case.
        text: hover as unknown as string[],
        hovertemplate: '%{text}<extra></extra>',
        colorscale: BLUES_SCALE,
        zmin: 0,
        zmax: 1,
        xgap: 2,
        ygap: 2,
        colorbar: { thickness: 12, tickfont: { color: CHART.muted, size: 10 }, outlinewidth: 0 },
      },
    ],
    [names, z, hover],
  )
  const layout = useMemo(
    () =>
      baseLayout({
        height: Math.max(240, 90 + names.length * 34),
        margin: { l: 140, r: 8, t: 8, b: 80 },
        xaxis: { tickangle: -35, tickfont: { color: CHART.ink, size: 10 }, gridcolor: CHART.surface },
        yaxis: { autorange: 'reversed', tickfont: { color: CHART.ink, size: 10 }, gridcolor: CHART.surface },
      }),
    [names.length],
  )
  return <PlotlyChart data={data} layout={layout} />
}
