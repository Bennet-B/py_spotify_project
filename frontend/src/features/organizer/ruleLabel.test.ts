import { describe, expect, it } from 'vitest'
import { ruleLabel } from './ruleLabel'

describe('ruleLabel', () => {
  it('renders tag rules with their field', () => {
    expect(ruleLabel({ kind: 'tag', labels: ['rock', 'metal'], field: 'genres' }, {})).toBe('genre: rock, metal')
    expect(ruleLabel({ kind: 'tag', labels: ['seen live'], field: 'tags' }, {})).toBe('tags: seen live')
  })

  it('renders year rules with open and closed bounds', () => {
    expect(ruleLabel({ kind: 'year', min_year: 1990, max_year: 1999 }, {})).toBe('years: 1990–1999')
    expect(ruleLabel({ kind: 'year', min_year: 2020, max_year: 2020 }, {})).toBe('year: 2020')
    expect(ruleLabel({ kind: 'year', min_year: null, max_year: 1999 }, {})).toBe('years: ≤ 1999')
  })

  it('renders duration rules as m:ss', () => {
    expect(ruleLabel({ kind: 'duration', min_seconds: 60, max_seconds: 270 }, {})).toBe('length: 1:00–4:30')
  })

  it('resolves artist names with id fallback', () => {
    expect(ruleLabel({ kind: 'artist', artist_ids: ['a1', 'a2'] }, { a1: 'The Beatles' })).toBe('artists: The Beatles, a2')
  })

  it('summarizes track rules by count', () => {
    expect(ruleLabel({ kind: 'track', track_ids: ['t1', 't2'] }, {})).toBe('2 picked tracks')
  })
})
