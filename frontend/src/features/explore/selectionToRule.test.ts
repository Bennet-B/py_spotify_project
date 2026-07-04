import { describe, expect, it } from 'vitest'
import type { PlotMouseEvent, PlotSelectionEvent } from 'plotly.js'
import { clickedBarLabel, isShiftClick, selectedDurationRangeSeconds, selectedTrackIds, selectedYearRange } from './selectionToRule'

function mouseEvent(point: Record<string, unknown>, shiftKey = false): PlotMouseEvent {
  return { points: [point], event: { shiftKey } } as unknown as PlotMouseEvent
}

function selection(partial: Record<string, unknown> | undefined): PlotSelectionEvent | undefined {
  return partial as unknown as PlotSelectionEvent | undefined
}

describe('clickedBarLabel', () => {
  it('reads y for horizontal bars and x for vertical bars', () => {
    expect(clickedBarLabel(mouseEvent({ x: 42, y: 'rock' }), 'h')).toBe('rock')
    expect(clickedBarLabel(mouseEvent({ x: 'rock', y: 42 }), 'v')).toBe('rock')
  })

  it('returns null for numeric axes and empty events', () => {
    expect(clickedBarLabel(mouseEvent({ x: 1999, y: 3 }), 'v')).toBeNull()
    expect(clickedBarLabel({ points: [] } as unknown as PlotMouseEvent, 'h')).toBeNull()
  })
})

describe('isShiftClick', () => {
  it('detects the shift modifier', () => {
    expect(isShiftClick(mouseEvent({}, true))).toBe(true)
    expect(isShiftClick(mouseEvent({}, false))).toBe(false)
  })
})

describe('selectedYearRange', () => {
  it('snaps a float box range to the integer years inside it', () => {
    expect(selectedYearRange(selection({ range: { x: [1998.4, 2003.7] } }))).toEqual([1999, 2003])
  })

  it('handles inverted drags and rejects empty selections', () => {
    expect(selectedYearRange(selection({ range: { x: [2003.7, 1998.4] } }))).toEqual([1999, 2003])
    expect(selectedYearRange(undefined)).toBeNull()
    expect(selectedYearRange(selection({}))).toBeNull()
  })
})

describe('selectedDurationRangeSeconds', () => {
  it('converts a minutes box range to whole seconds, clamped at zero', () => {
    expect(selectedDurationRangeSeconds(selection({ range: { x: [-0.5, 3.5] } }))).toEqual([0, 210])
  })

  it('rejects zero-width ranges', () => {
    expect(selectedDurationRangeSeconds(selection({ range: { x: [2, 2] } }))).toBeNull()
  })
})

describe('selectedTrackIds', () => {
  it('collects unique non-null customdata ids', () => {
    const event = selection({ points: [{ customdata: 't1' }, { customdata: 't2' }, { customdata: 't1' }, { customdata: null }, {}] })
    expect(selectedTrackIds(event)).toEqual(['t1', 't2'])
  })

  it('returns empty for cleared selections', () => {
    expect(selectedTrackIds(undefined)).toEqual([])
  })
})
