import { useMemo } from 'react'
import type { Data } from 'plotly.js'
import { PlotlyChart } from '../../components/PlotlyChart'
import { CHART, baseLayout } from '../../lib/chartTheme'
import { useAdditions, useDiscovery, useSeasonal } from '../../api/hooks'

/** Monthly additions bars — how the library grew. */
export function AdditionsChart({ playlistId }: { playlistId: string }) {
  const additions = useAdditions(playlistId)
  const rows = useMemo(() => additions.data?.rows ?? [], [additions.data])
  const data = useMemo<Data[]>(
    () => [{ type: 'bar', x: rows.map((r) => r.period), y: rows.map((r) => r.added), marker: { color: CHART.blue, opacity: 0.9 }, hovertemplate: '%{x|%b %Y}: %{y} added<extra></extra>' }],
    [rows],
  )
  const layout = useMemo(() => baseLayout({ height: 240, bargap: 0.15 }), [])
  return <PlotlyChart data={data} layout={layout} />
}

/** Cumulative listening hours area — the same growth, in hours of music. */
export function CumulativeHoursChart({ playlistId }: { playlistId: string }) {
  const additions = useAdditions(playlistId)
  const rows = useMemo(() => additions.data?.rows ?? [], [additions.data])
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'scatter',
        mode: 'lines',
        x: rows.map((r) => r.period),
        y: rows.map((r) => r.cumulative_hours),
        fill: 'tozeroy',
        line: { color: CHART.blue, width: 2 },
        fillcolor: 'rgba(42, 120, 214, 0.15)',
        hovertemplate: '%{x|%b %Y}: %{y:.0f} h total<extra></extra>',
      },
    ],
    [rows],
  )
  const layout = useMemo(() => baseLayout({ height: 240 }), [])
  return <PlotlyChart data={data} layout={layout} />
}

/** New-artist discoveries per month — spikes are discovery waves. */
export function DiscoveryChart({ playlistId }: { playlistId: string }) {
  const discovery = useDiscovery(playlistId)
  const rows = useMemo(() => discovery.data?.rows ?? [], [discovery.data])
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'scatter',
        mode: 'lines',
        x: rows.map((r) => r.period),
        y: rows.map((r) => r.new_artists),
        fill: 'tozeroy',
        line: { color: CHART.blue, width: 2 },
        fillcolor: 'rgba(42, 120, 214, 0.15)',
        hovertemplate: '%{x|%b %Y}: %{y} new artists<extra></extra>',
      },
    ],
    [rows],
  )
  const layout = useMemo(() => baseLayout({ height: 240 }), [])
  return <PlotlyChart data={data} layout={layout} />
}

/** Additions by calendar month across all years — do you hoard music in winter or summer? */
export function SeasonalChart({ playlistId }: { playlistId: string }) {
  const seasonal = useSeasonal(playlistId)
  const rows = useMemo(() => seasonal.data?.rows ?? [], [seasonal.data])
  const data = useMemo<Data[]>(
    () => [
      {
        type: 'bar',
        x: rows.map((r) => r.month_name),
        y: rows.map((r) => r.added),
        marker: { color: CHART.blue, opacity: 0.9, cornerradius: 4 },
        hovertemplate: '%{x}: %{y} added<extra></extra>',
      },
    ],
    [rows],
  )
  const layout = useMemo(() => baseLayout({ height: 240, bargap: 0.25, xaxis: { tickfont: { color: CHART.muted }, gridcolor: CHART.surface } }), [])
  return <PlotlyChart data={data} layout={layout} />
}
