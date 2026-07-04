import type { JobOut } from '../api/hooks'

const PHASE_LABELS: Record<string, string> = {
  tracks: 'Fetching tracks',
  artists: 'Fetching artists',
  lastfm_tags: 'Enriching tags',
}

/** Inline progress bar for a running refresh job; indeterminate while the total is unknown. */
export function ProgressBar({ job }: { job: JobOut }) {
  const { phase, done, total } = job.progress
  const label = PHASE_LABELS[phase] ?? (job.status === 'queued' ? 'Queued' : 'Working')
  const pct = total !== null && total > 0 ? Math.round((done / total) * 100) : null
  return (
    <div className="mt-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>{label}</span>
        <span>{total !== null ? `${done}/${total}` : done > 0 ? done : ''}</span>
      </div>
      <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded bg-gray-200">
        {pct !== null ? (
          <div className="h-full rounded bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
        ) : (
          <div className="h-full w-1/3 animate-pulse rounded bg-emerald-400" />
        )}
      </div>
    </div>
  )
}
