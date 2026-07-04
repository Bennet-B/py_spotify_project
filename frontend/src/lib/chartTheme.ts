import type { Layout, Config } from 'plotly.js'

/**
 * Chart color roles (light surface), validated with the dataviz palette checker:
 * series blue + selection accent pass lightness band, chroma floor, CVD separation (ΔE 13.2), and 3:1 contrast.
 */
export const CHART = {
  /** Series slot 1 — every single-series chart uses this. */
  blue: '#2a78d6',
  /** Selection accent — the 550 step of the same blue ramp, used for selected marks. */
  blueSelected: '#1c5cab',
  /** Dimmed variant for unselected marks while a selection is active. */
  dimOpacity: 0.35,
  surface: '#fcfcfb',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  muted: '#898781',
  ink: '#0b0b0b',
} as const

/** Shared base layout: neutral chrome, recessive grid, system font, tight margins. Spread chart-specific overrides on top. */
export function baseLayout(overrides: Partial<Layout> = {}): Partial<Layout> {
  return {
    paper_bgcolor: CHART.surface,
    plot_bgcolor: CHART.surface,
    font: { family: 'system-ui, "Segoe UI", sans-serif', size: 12, color: CHART.ink },
    margin: { l: 56, r: 12, t: 8, b: 36 },
    xaxis: { gridcolor: CHART.grid, linecolor: CHART.axis, tickcolor: CHART.axis, tickfont: { color: CHART.muted }, zeroline: false },
    yaxis: { gridcolor: CHART.grid, linecolor: CHART.axis, tickcolor: CHART.axis, tickfont: { color: CHART.muted }, zeroline: false },
    showlegend: false,
    hovermode: 'closest',
    ...overrides,
  }
}

/** Shared Plotly config: responsive, no logo, modebar only on hover. */
export const BASE_CONFIG: Partial<Config> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['zoomIn2d', 'zoomOut2d', 'autoScale2d', 'toImage'],
}
