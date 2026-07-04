import { useState } from 'react'
import { useSuggestSplit } from '../../api/hooks'
import { useWorkbenchStore } from '../../state/store'

/** Ask the backend for an even bucket layout; on accept, the proposal replaces the current bucket drafts (nothing is applied). */
export function SuggestSplitDialog({ playlistId, onClose }: { playlistId: string; onClose: () => void }) {
  const [targetBuckets, setTargetBuckets] = useState(5)
  const [tolerancePct, setTolerancePct] = useState(15)
  const suggest = useSuggestSplit()
  const setBucketsFromSpec = useWorkbenchStore((s) => s.setBucketsFromSpec)

  const result = suggest.data

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[80vh] w-[520px] overflow-y-auto rounded-xl border border-gray-200 bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-base font-semibold">Suggest a split</h2>
        <div className="mb-3 flex items-end gap-4 text-sm">
          <label>
            <span className="mb-1 block text-gray-600">Target buckets</span>
            <input
              type="number"
              min={1}
              max={50}
              className="w-20 rounded border border-gray-300 px-2 py-1"
              value={targetBuckets}
              onChange={(e) => setTargetBuckets(Number(e.target.value))}
            />
          </label>
          <label className="flex-1">
            <span className="mb-1 block text-gray-600">Duplication tolerance: {tolerancePct}%</span>
            <input type="range" min={0} max={50} step={5} className="w-full" value={tolerancePct} onChange={(e) => setTolerancePct(Number(e.target.value))} />
          </label>
          <button
            type="button"
            className="rounded bg-emerald-600 px-4 py-1.5 font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
            disabled={suggest.isPending || targetBuckets < 1}
            onClick={() => suggest.mutate({ playlist_id: playlistId, target_buckets: targetBuckets, duplication_tolerance: tolerancePct / 100 })}
          >
            {suggest.isPending ? 'Thinking…' : 'Suggest'}
          </button>
        </div>
        {suggest.isError && <p className="mb-2 text-sm text-red-600">Suggestion failed — is the playlist loaded and genre-tagged?</p>}
        {result !== undefined && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span>
                coverage <strong>{result.coverage_pct.toFixed(1)}%</strong>
              </span>
              <span>
                duplication <strong>{(result.duplication_rate * 100).toFixed(1)}%</strong>
              </span>
              <span>
                buckets <strong>{Object.keys(result.bucket_sizes).length}</strong>
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(result.bucket_sizes).map(([name, size]) => (
                <span key={name} className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-800 ring-1 ring-blue-200">
                  {name} · {size}
                </span>
              ))}
            </div>
            <ul className="list-inside list-disc space-y-0.5 text-xs text-gray-500">
              {result.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="rounded px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100" onClick={onClose}>
            Cancel
          </button>
          {result !== undefined && result.spec.buckets.length > 0 && (
            <button
              type="button"
              className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
              onClick={() => {
                setBucketsFromSpec(result.spec)
                onClose()
              }}
            >
              Load into organizer (replaces current buckets)
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
