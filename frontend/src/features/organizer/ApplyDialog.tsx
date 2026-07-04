import { useState } from 'react'
import { useApply, useJobById } from '../../api/hooks'
import type { PreviewResponse } from '../../api/hooks'
import type { OrganizerSpecIn } from '../../state/store'
import { ProgressBar } from '../../components/ProgressBar'

/**
 * The explicit confirm step before the API's only mutating call. Every Apply CREATES new playlists named "[batch] bucket"
 * (Spotify has no folder API — the shared prefix + description marker is the grouping).
 */
export function ApplyDialog({ playlistId, spec, preview, onClose }: { playlistId: string; spec: OrganizerSpecIn; preview: PreviewResponse; onClose: () => void }) {
  const [batchName, setBatchName] = useState('')
  const [chosen, setChosen] = useState<Set<string>>(new Set(preview.buckets.filter((b) => b.count > 0).map((b) => b.name)))
  const [includeRest, setIncludeRest] = useState(false)
  const [restName, setRestName] = useState('Rest')
  const [isPublic, setIsPublic] = useState(false)
  const apply = useApply()
  const job = useJobById(apply.data?.job_id ?? null)

  const running = job.data !== undefined && (job.data.status === 'queued' || job.data.status === 'running')
  const done = job.data?.status === 'done'
  const failed = job.data?.status === 'error'
  const result = job.data?.result as { created: { bucket_name: string; url: string; added: number }[]; skipped_empty: string[] } | null | undefined

  function toggleBucket(name: string) {
    setChosen((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  function start() {
    apply.mutate({ playlist_id: playlistId, spec, bucket_names: [...chosen], include_rest: includeRest, rest_name: restName, public: isPublic, batch_name: batchName.trim() })
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30" onClick={done ? onClose : undefined}>
      <div className="w-[480px] rounded-xl border border-gray-200 bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-base font-semibold">Create playlists</h2>
        {!done && (
          <>
            <label className="mb-3 block text-sm">
              <span className="mb-1 block text-gray-600">Batch name (playlists become “[batch] bucket”)</span>
              <input
                autoFocus
                className="w-full rounded border border-gray-300 px-2 py-1.5 focus:border-emerald-500 focus:outline-none"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                placeholder="e.g. Split July"
                disabled={running}
              />
            </label>
            <div className="mb-3 space-y-1 text-sm">
              {preview.buckets.map((bucket) => (
                <label key={bucket.name} className={`flex items-center gap-2 ${bucket.count === 0 ? 'text-gray-400' : ''}`}>
                  <input type="checkbox" checked={chosen.has(bucket.name)} onChange={() => toggleBucket(bucket.name)} disabled={running || bucket.count === 0} />
                  {bucket.name}{' '}
                  <span className="text-xs text-gray-400">
                    ({bucket.count} tracks{bucket.count === 0 ? ' — skipped' : ''})
                  </span>
                </label>
              ))}
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={includeRest} onChange={(e) => setIncludeRest(e.target.checked)} disabled={running || preview.rest_count === 0} />
                also create{' '}
                <input
                  className="w-28 rounded border border-gray-300 px-1.5 py-0.5 text-xs"
                  value={restName}
                  onChange={(e) => setRestName(e.target.value)}
                  disabled={!includeRest || running}
                />{' '}
                from the {preview.rest_count} unmatched
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} disabled={running} />
                public playlists
              </label>
            </div>
            {preview.stats.skipped_local_count > 0 && (
              <p className="mb-2 text-xs text-gray-400">{preview.stats.skipped_local_count} local files can’t be added via the API and stay behind.</p>
            )}
          </>
        )}
        {running && job.data !== undefined && <ProgressBar job={job.data} />}
        {failed && <p className="my-2 text-sm text-red-600">Apply failed: {job.data?.error?.message ?? 'unknown error'}</p>}
        {done && result != null && (
          <div className="my-2 space-y-1 text-sm">
            <p className="font-medium text-emerald-700">Created {result.created.length} playlists:</p>
            {result.created.map((c) => (
              <a key={c.url} href={c.url} target="_blank" rel="noreferrer" className="block text-emerald-700 underline-offset-2 hover:underline">
                {c.bucket_name} — {c.added} tracks ↗
              </a>
            ))}
            {result.skipped_empty.length > 0 && <p className="text-xs text-gray-400">Skipped empty: {result.skipped_empty.join(', ')}</p>}
            <p className="pt-1 text-xs text-gray-400">Grouping into a folder stays manual in the Spotify app — the API has no folder support.</p>
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="rounded px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100" onClick={onClose} disabled={running}>
            {done ? 'Close' : 'Cancel'}
          </button>
          {!done && (
            <button
              type="button"
              className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
              onClick={start}
              disabled={running || batchName.trim().length === 0 || (chosen.size === 0 && !includeRest)}
            >
              {running ? 'Creating…' : `Create ${chosen.size + (includeRest ? 1 : 0)} playlists`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
