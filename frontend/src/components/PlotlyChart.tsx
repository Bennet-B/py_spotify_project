import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-cartesian-dist-min'
import type { Config, Data, Layout, PlotMouseEvent, PlotSelectionEvent } from 'plotly.js'
import { BASE_CONFIG } from '../lib/chartTheme'

export interface PlotlyChartProps {
  data: Data[]
  layout: Partial<Layout>
  config?: Partial<Config>
  /** Per-mark click (bars, dots). The raw event carries point data plus the browser MouseEvent (shift-click detection). */
  onPointClick?: (event: PlotMouseEvent) => void
  /** Box/lasso selection; undefined means the selection was cleared. */
  onSelected?: (event: PlotSelectionEvent | undefined) => void
  /** Double-click clears a Plotly selection. */
  onDeselect?: () => void
  className?: string
}

/**
 * Owned thin wrapper over plotly.js (react-plotly.js is unmaintained): newPlot on mount, react() on updates, purge on unmount.
 * Event handlers are kept in refs so listeners bind once and always see the latest callbacks.
 */
export function PlotlyChart({ data, layout, config, onPointClick, onSelected, onDeselect, className }: PlotlyChartProps) {
  const container = useRef<HTMLDivElement>(null)
  const handlers = useRef({ onPointClick, onSelected, onDeselect })
  handlers.current = { onPointClick, onSelected, onDeselect }

  useEffect(() => {
    const el = container.current
    if (!el) return
    let disposed = false
    void Plotly.newPlot(el, data, layout, { ...BASE_CONFIG, ...config }).then((plotEl) => {
      if (disposed) return
      plotEl.on('plotly_click', (event: PlotMouseEvent) => handlers.current.onPointClick?.(event))
      plotEl.on('plotly_selected', (event: PlotSelectionEvent) => handlers.current.onSelected?.(event))
      plotEl.on('plotly_deselect', () => handlers.current.onDeselect?.())
    })
    return () => {
      disposed = true
      Plotly.purge(el)
    }
    // Mount/unmount only — updates flow through Plotly.react below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const el = container.current
    if (!el) return
    void Plotly.react(el, data, layout, { ...BASE_CONFIG, ...config })
  }, [data, layout, config])

  return <div ref={container} className={className} />
}
