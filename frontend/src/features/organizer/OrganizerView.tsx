import { useMemo, useState } from 'react'
import { useBatches, usePreview } from '../../api/hooks'
import type { PreviewResponse, TrackRow } from '../../api/hooks'
import { useWorkbenchStore } from '../../state/store'
import type { BucketDraft, OrganizerSpecIn } from '../../state/store'
import { formatDuration } from '../../lib/format'
import { ruleLabel } from './ruleLabel'
import { ApplyDialog } from './ApplyDialog'
import { SuggestSplitDialog } from './SuggestSplitDialog'

function BucketCard({ bucket }: { bucket: BucketDraft }) {
  const activeBucketId = useWorkbenchStore((s) => s.activeBucketId)
  const setActiveBucket = useWorkbenchStore((s) => s.setActiveBucket)
  const renameBucket = useWorkbenchStore((s) => s.renameBucket)
  const removeBucket = useWorkbenchStore((s) => s.removeBucket)
  const removeRule = useWorkbenchStore((s) => s.removeRule)
  const artistNames = useWorkbenchStore((s) => s.artistNames)
  const active = activeBucketId === bucket.id

  return (
    <div
      className={`cursor-pointer rounded-lg border bg-white p-3 ${active ? 'border-emerald-400 ring-1 ring-emerald-300' : 'border-gray-200 hover:border-gray-300'}`}
      onClick={() => setActiveBucket(bucket.id)}
    >
      <div className="flex items-center gap-2">
        <input
          className="w-full rounded border border-transparent px-1 py-0.5 text-sm font-semibold hover:border-gray-200 focus:border-emerald-400 focus:outline-none"
          value={bucket.name}
          onChange={(e) => renameBucket(bucket.id, e.target.value)}
          onClick={(e) => e.stopPropagation()}
        />
        <button
          type="button"
          className="rounded px-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600"
          title="Remove bucket"
          onClick={(e) => {
            e.stopPropagation()
            removeBucket(bucket.id)
          }}
        >
          ×
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {bucket.rules.length === 0 && <span className="text-xs text-gray-400">{active ? 'Select in Explore charts, then “Add to bucket”.' : 'No rules yet.'}</span>}
        {bucket.rules.map((rule, index) => (
          <span key={index} className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-800 ring-1 ring-blue-200">
            {ruleLabel(rule, artistNames)}
            <button
              type="button"
              className="rounded-full px-0.5 text-blue-500 hover:bg-blue-100"
              title="Remove rule"
              onClick={(e) => {
                e.stopPropagation()
                removeRule(bucket.id, index)
              }}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      {active && <div className="mt-1 text-[11px] text-emerald-600">active — selections land here</div>}
    </div>
  )
}

function PreviewPanel({ preview, trackNames, onApply }: { preview: PreviewResponse | undefined; trackNames: Map<string, string>; onApply: () => void }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  if (preview === undefined) {
    return <p className="p-6 text-sm text-gray-400">Add a bucket with at least one rule to see the live dry-run.</p>
  }
  const sample = (ids: string[]) => ids.slice(0, 8).map((id) => trackNames.get(id) ?? id)
  const canApply = preview.buckets.some((b) => b.count > 0)
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm">
        <span>
          coverage <strong>{preview.stats.coverage_pct.toFixed(1)}%</strong>
        </span>
        <span>
          in several buckets <strong>{preview.stats.duplicate_count}</strong>
        </span>
        <span>
          unmatched <strong>{preview.rest_count}</strong>
        </span>
        {preview.stats.skipped_local_count > 0 && <span className="text-gray-500">{preview.stats.skipped_local_count} local files skipped</span>}
        {preview.stats.overlaps.slice(0, 3).map((o) => (
          <span key={`${o.bucket_a}-${o.bucket_b}`} className="text-xs text-gray-400">
            {o.bucket_a} ∩ {o.bucket_b}: {o.count}
          </span>
        ))}
        <button
          type="button"
          disabled={!canApply}
          className="ml-auto rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
          onClick={onApply}
        >
          Apply…
        </button>
      </div>
      <div className="space-y-2">
        {[
          ...preview.buckets.map((b) => ({ name: b.name, count: b.count, duration: b.duration_ms_total, ids: b.track_ids, rest: false })),
          { name: 'Rest (unmatched)', count: preview.rest_count, duration: 0, ids: preview.rest_track_ids, rest: true },
        ].map((row) => (
          <div key={row.name} className={`rounded-lg border bg-white p-3 ${row.rest ? 'border-dashed border-gray-300' : 'border-gray-200'}`}>
            <div className="flex items-baseline gap-3">
              <span className="font-semibold">{row.name}</span>
              <span className="text-sm text-gray-500">{row.count} tracks</span>
              {!row.rest && row.duration > 0 && <span className="text-xs text-gray-400">{formatDuration(row.duration)} total</span>}
              {row.ids.length > 0 && (
                <button type="button" className="ml-auto text-xs text-gray-400 hover:text-gray-600" onClick={() => setExpanded(expanded === row.name ? null : row.name)}>
                  {expanded === row.name ? 'hide tracks' : 'show tracks'}
                </button>
              )}
            </div>
            <p className="mt-1 truncate text-xs text-gray-500">
              {sample(row.ids).join(' · ')}
              {row.ids.length > 8 && ` · +${row.ids.length - 8} more`}
            </p>
            {expanded === row.name && (
              <ul className="mt-2 max-h-64 columns-2 gap-6 overflow-y-auto text-xs text-gray-600">
                {row.ids.map((id) => (
                  <li key={id} className="truncate py-0.5">
                    {trackNames.get(id) ?? id}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function BatchHistory() {
  const batches = useBatches()
  if (batches.data === undefined || batches.data.batches.length === 0) return null
  return (
    <details className="rounded-lg border border-gray-200 bg-white p-3">
      <summary className="cursor-pointer text-sm font-semibold text-gray-700">Created batches ({batches.data.batches.length})</summary>
      <ul className="mt-2 space-y-2">
        {batches.data.batches.map((batch) => (
          <li key={`${batch.batch_name}-${batch.created_at}`} className="text-sm">
            <span className="font-medium">{batch.batch_name}</span> <span className="text-xs text-gray-400">{new Date(batch.created_at).toLocaleString()}</span>
            <span className="ml-2 space-x-2">
              {batch.created.map((c) => (
                <a key={c.playlist_id} href={c.url} target="_blank" rel="noreferrer" className="text-xs text-emerald-700 underline-offset-2 hover:underline">
                  {c.bucket_name} ({c.added})
                </a>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

/** The organizer: bucket drafts on the left, live dry-run preview on the right, Apply behind an explicit dialog. */
export function OrganizerView({ playlistId, tracks }: { playlistId: string; tracks: TrackRow[] }) {
  const buckets = useWorkbenchStore((s) => s.buckets)
  const allowDuplicates = useWorkbenchStore((s) => s.allowDuplicates)
  const setAllowDuplicates = useWorkbenchStore((s) => s.setAllowDuplicates)
  const addBucket = useWorkbenchStore((s) => s.addBucket)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [suggestOpen, setSuggestOpen] = useState(false)

  const spec = useMemo<OrganizerSpecIn>(() => ({ buckets: buckets.map((b) => ({ name: b.name, rules: b.rules })), allow_duplicates: allowDuplicates }), [buckets, allowDuplicates])
  const preview = usePreview(buckets.length > 0 ? playlistId : null, spec)
  const trackNames = useMemo(() => new Map(tracks.filter((t) => t.track_id !== null).map((t) => [t.track_id!, `${t.name} — ${t.primary_artist_name}`])), [tracks])

  return (
    <div className="flex min-h-0 flex-1 gap-4 overflow-y-auto p-4">
      <aside className="w-96 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Buckets</h2>
          <label className="flex items-center gap-1.5 text-xs text-gray-500">
            <input type="checkbox" checked={allowDuplicates} onChange={(e) => setAllowDuplicates(e.target.checked)} />
            allow duplicates
          </label>
        </div>
        {buckets.map((bucket) => (
          <BucketCard key={bucket.id} bucket={bucket} />
        ))}
        <button
          type="button"
          className="w-full rounded-lg border border-dashed border-gray-300 py-2 text-sm text-gray-500 hover:border-emerald-400 hover:text-emerald-700"
          onClick={addBucket}
        >
          + Add bucket
        </button>
        <button
          type="button"
          className="w-full rounded-lg border border-dashed border-blue-300 py-2 text-sm text-blue-600 hover:border-blue-400 hover:bg-blue-50"
          onClick={() => setSuggestOpen(true)}
        >
          ✨ Suggest a split…
        </button>
        <p className="text-xs leading-relaxed text-gray-400">
          Build rules in <strong>Explore</strong>: click genre/artist bars, box-select year or length ranges, lasso the scatter — then “Add to bucket”. Rules AND together inside a bucket.
          {!allowDuplicates && ' Without duplicates, bucket order is priority order.'}
        </p>
      </aside>
      <div className="min-w-0 flex-1 space-y-3">
        <PreviewPanel preview={preview.data} trackNames={trackNames} onApply={() => setDialogOpen(true)} />
        <BatchHistory />
      </div>
      {dialogOpen && preview.data !== undefined && <ApplyDialog playlistId={playlistId} spec={spec} preview={preview.data} onClose={() => setDialogOpen(false)} />}
      {suggestOpen && <SuggestSplitDialog playlistId={playlistId} onClose={() => setSuggestOpen(false)} />}
    </div>
  )
}
