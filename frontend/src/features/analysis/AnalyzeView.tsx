import { useMemo, useState } from 'react'
import { useJobById, usePlaylists, useScan, useScanResult, useSweep } from '../../api/hooks'
import type { ScanResult } from '../../api/hooks'
import { ProgressBar } from '../../components/ProgressBar'
import { ChartCard } from '../explore/ChartCard'
import { OverlapHeatmap } from './OverlapHeatmap'

/** Pick which playlists count as sources (should be fully organized) vs subsets (count as "organized"). */
function ScopeSelector({ sourceIds, subsetIds, onToggle }: { sourceIds: Set<string>; subsetIds: Set<string>; onToggle: (id: string, role: 'source' | 'subset') => void }) {
  const playlists = usePlaylists()
  return (
    <div className="max-h-80 overflow-y-auto overflow-x-hidden rounded-lg border border-gray-200 bg-white">
      <table className="w-full table-fixed text-sm">
        <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wide text-gray-400">
          <tr>
            <th className="px-3 py-2">Playlist</th>
            <th className="w-20 px-2 py-2" title="Should be fully organized (e.g. Liked Songs)">
              Source
            </th>
            <th className="w-20 px-2 py-2" title="Counts as organized (your sub-playlists)">
              Subset
            </th>
          </tr>
        </thead>
        <tbody>
          {playlists.data?.items.map((item) => (
            <tr key={item.id} className="hover:bg-gray-50">
              <td className="truncate px-3 py-1">
                {item.name} <span className="text-xs text-gray-400">{item.track_count ?? ''}</span>
              </td>
              <td className="px-2 py-1">
                <input type="checkbox" checked={sourceIds.has(item.id)} onChange={() => onToggle(item.id, 'source')} />
              </td>
              <td className="px-2 py-1">
                <input type="checkbox" checked={subsetIds.has(item.id)} onChange={() => onToggle(item.id, 'subset')} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SubsetCallouts({ result }: { result: ScanResult }) {
  const contained = result.pairs.flatMap((pair) => {
    const lines: string[] = []
    if (pair.containment_a_in_b >= 0.9 && pair.intersection > 0) lines.push(`${Math.round(pair.containment_a_in_b * 100)}% of “${pair.a_name}” is inside “${pair.b_name}”`)
    if (pair.containment_b_in_a >= 0.9 && pair.intersection > 0) lines.push(`${Math.round(pair.containment_b_in_a * 100)}% of “${pair.b_name}” is inside “${pair.a_name}”`)
    return lines
  })
  if (contained.length === 0) return null
  return (
    <ul className="space-y-0.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm text-gray-700">
      {contained.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  )
}

function UnorganizedReport({ result }: { result: ScanResult }) {
  const [sweepName, setSweepName] = useState('Unsorted')
  const sweep = useSweep()
  const sweepJob = useJobById(sweep.data?.job_id ?? null)
  const running = sweepJob.data !== undefined && (sweepJob.data.status === 'queued' || sweepJob.data.status === 'running')
  const sweepResult = sweepJob.data?.status === 'done' ? (sweepJob.data.result as { url: string; added: number } | null) : null

  return (
    <ChartCard title={`Unorganized tracks (${result.unorganized.count})`} hint="in a source, in no subset">
      {result.unorganized.count === 0 ? (
        <p className="px-1 py-2 text-sm text-emerald-700">Every source track lives in at least one subset — everything has its place. 🎉</p>
      ) : (
        <div className="space-y-2 px-1">
          <p className="max-h-40 overflow-y-auto text-xs leading-relaxed text-gray-500">
            {result.unorganized.sample_names.join(' · ')}
            {result.unorganized.count > result.unorganized.sample_names.length && ` · +${result.unorganized.count - result.unorganized.sample_names.length} more`}
          </p>
          {sweepResult === null ? (
            <div className="flex items-center gap-2">
              <input className="w-48 rounded border border-gray-300 px-2 py-1 text-sm" value={sweepName} onChange={(e) => setSweepName(e.target.value)} disabled={running} />
              <button
                type="button"
                className="rounded bg-emerald-600 px-3 py-1 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
                disabled={running || sweepName.trim().length === 0}
                onClick={() => sweep.mutate({ name: sweepName.trim(), track_ids: result.unorganized.track_ids })}
              >
                {running ? 'Sweeping…' : `Sweep all ${result.unorganized.count} into a playlist`}
              </button>
            </div>
          ) : (
            <a href={sweepResult.url} target="_blank" rel="noreferrer" className="text-sm text-emerald-700 underline-offset-2 hover:underline">
              Created “{sweepName}” with {sweepResult.added} tracks ↗
            </a>
          )}
          {running && sweepJob.data !== undefined && <ProgressBar job={sweepJob.data} />}
        </div>
      )}
    </ChartCard>
  )
}

/** Set-analysis workbench: pick the scope, run the scan, read overlaps / duplication / the unorganized report. */
export function AnalyzeView() {
  const [sourceIds, setSourceIds] = useState<Set<string>>(new Set(['__liked__']))
  const [subsetIds, setSubsetIds] = useState<Set<string>>(new Set())
  const scan = useScan()
  const job = useJobById(scan.data?.job_id ?? null)
  const jobDone = job.data?.status === 'done'
  const result = useScanResult(scan.data?.job_id ?? null, jobDone)
  const running = job.data !== undefined && (job.data.status === 'queued' || job.data.status === 'running')

  const duplicated = useMemo(() => result.data?.duplication ?? [], [result.data])

  function toggle(id: string, role: 'source' | 'subset') {
    const [mine, other, setMine, setOther] =
      role === 'source' ? ([sourceIds, subsetIds, setSourceIds, setSubsetIds] as const) : ([subsetIds, sourceIds, setSubsetIds, setSourceIds] as const)
    const next = new Set(mine)
    if (next.has(id)) next.delete(id)
    else {
      next.add(id)
      if (other.has(id)) {
        const cleaned = new Set(other)
        cleaned.delete(id)
        setOther(cleaned)
      }
    }
    setMine(next)
  }

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="space-y-2">
          <ScopeSelector sourceIds={sourceIds} subsetIds={subsetIds} onToggle={toggle} />
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
              disabled={sourceIds.size === 0 || running}
              onClick={() => scan.mutate({ source_ids: [...sourceIds], subset_ids: [...subsetIds] })}
            >
              {running ? 'Scanning…' : 'Run scan'}
            </button>
            <span className="text-xs text-gray-400">
              {sourceIds.size} sources · {subsetIds.size} subsets — cold playlists are fetched first, warm ones load in seconds
            </span>
          </div>
          {running && job.data !== undefined && <ProgressBar job={job.data} />}
          {job.data?.status === 'error' && <p className="text-sm text-red-600">Scan failed: {job.data.error?.message}</p>}
        </div>
        {result.data !== undefined && (
          <ChartCard title="Overlap (Jaccard)" hint="hover for shared-track counts">
            <OverlapHeatmap result={result.data} />
          </ChartCard>
        )}
      </div>
      {result.data !== undefined && (
        <>
          <SubsetCallouts result={result.data} />
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <ChartCard title={`Tracks in several subsets (${result.data.duplication_total})`} hint="curation duplication">
              {duplicated.length === 0 ? (
                <p className="px-1 py-2 text-sm text-gray-400">No track lives in more than one selected subset.</p>
              ) : (
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-sm">
                    <tbody>
                      {duplicated.map((row) => (
                        <tr key={row.track_id} className="hover:bg-gray-50">
                          <td className="truncate px-2 py-1">{row.name}</td>
                          <td className="px-2 py-1 text-center text-xs font-semibold text-gray-600">{row.n_playlists}×</td>
                          <td className="truncate px-2 py-1 text-xs text-gray-400">{row.playlist_names.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ChartCard>
            <UnorganizedReport result={result.data} />
          </div>
        </>
      )}
    </div>
  )
}
