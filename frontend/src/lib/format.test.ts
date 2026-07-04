import { describe, expect, it } from 'vitest'
import { formatDate, formatDuration } from './format'

describe('formatDuration', () => {
  it('formats whole minutes with padded seconds', () => {
    expect(formatDuration(200_000)).toBe('3:20')
  })

  it('pads single-digit seconds', () => {
    expect(formatDuration(61_000)).toBe('1:01')
  })

  it('rounds sub-second remainders', () => {
    expect(formatDuration(59_600)).toBe('1:00')
  })
})

describe('formatDate', () => {
  it('renders a dash for missing timestamps', () => {
    expect(formatDate(null)).toBe('—')
  })
})
