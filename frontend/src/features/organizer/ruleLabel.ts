import type { RuleIn } from '../../state/store'
import { formatDuration } from '../../lib/format'

/** Human-readable chip text for a rule; artist ids resolve through the remembered name map. */
export function ruleLabel(rule: RuleIn, artistNames: Record<string, string>): string {
  switch (rule.kind) {
    case 'tag':
      return `${rule.field === 'tags' ? 'tags' : 'genre'}: ${rule.labels.join(', ')}`
    case 'year': {
      const min = rule.min_year ?? null
      const max = rule.max_year ?? null
      if (min !== null && max !== null) return min === max ? `year: ${min}` : `years: ${min}–${max}`
      return min !== null ? `years: ≥ ${min}` : `years: ≤ ${max}`
    }
    case 'duration': {
      const min = rule.min_seconds ?? null
      const max = rule.max_seconds ?? null
      if (min !== null && max !== null) return `length: ${formatDuration(min * 1000)}–${formatDuration(max * 1000)}`
      return min !== null ? `length: ≥ ${formatDuration(min * 1000)}` : `length: ≤ ${formatDuration((max ?? 0) * 1000)}`
    }
    case 'artist':
      return `artists: ${rule.artist_ids.map((id) => artistNames[id] ?? id).join(', ')}`
    case 'track':
      return `${rule.track_ids.length} picked tracks`
  }
}
