import type { PlotMouseEvent, PlotSelectionEvent } from 'plotly.js'

/**
 * Pure mappers from Plotly event payloads to domain selection values — the seam between chart clicks and organizer rules.
 * Kept free of React/Plotly imports at runtime (types only) so vitest covers them without a DOM.
 */

/** The category label of a clicked bar. Horizontal bars carry the label on y, vertical bars on x. */
export function clickedBarLabel(event: PlotMouseEvent, orientation: 'h' | 'v'): string | null {
  const point = event.points?.[0]
  if (!point) return null
  const raw = orientation === 'h' ? point.y : point.x
  return typeof raw === 'string' ? raw : null
}

/** True when the browser click carried Shift (multi-select semantics). */
export function isShiftClick(event: PlotMouseEvent): boolean {
  return Boolean((event.event as MouseEvent | undefined)?.shiftKey)
}

/** An integer year range from a box selection over a year axis; null when the selection is empty or unusable. */
export function selectedYearRange(event: PlotSelectionEvent | undefined): [number, number] | null {
  const range = rangeX(event)
  if (range === null) return null
  const low = Math.ceil(Math.min(...range))
  const high = Math.floor(Math.max(...range))
  return low <= high ? [low, high] : [high, low]
}

/** A duration range in whole seconds from a box selection over a minutes axis; null when empty. */
export function selectedDurationRangeSeconds(event: PlotSelectionEvent | undefined): [number, number] | null {
  const range = rangeX(event)
  if (range === null) return null
  const [a, b] = [Math.min(...range), Math.max(...range)]
  const low = Math.max(0, Math.round(a * 60))
  const high = Math.round(b * 60)
  return high > low ? [low, high] : null
}

/** Unique non-null track ids from the customdata of lasso/box-selected points. */
export function selectedTrackIds(event: PlotSelectionEvent | undefined): string[] {
  if (!event?.points) return []
  const ids = event.points.map((point) => point.customdata).filter((value): value is string => typeof value === 'string' && value.length > 0)
  return [...new Set(ids)]
}

function rangeX(event: PlotSelectionEvent | undefined): [number, number] | null {
  const x = event?.range?.x
  if (!x || x.length < 2) return null
  const [a, b] = [Number(x[0]), Number(x[1])]
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return null
  return [a, b]
}
