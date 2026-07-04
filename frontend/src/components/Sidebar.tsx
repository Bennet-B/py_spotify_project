import { useJob, usePlaylists, useRefreshPlaylist } from '../api/hooks'
import type { PlaylistItem } from '../api/hooks'
import { useWorkbenchStore } from '../state/store'
import { ProgressBar } from './ProgressBar'

function PlaylistEntry({ item }: { item: PlaylistItem }) {
  const selectedId = useWorkbenchStore((s) => s.selectedPlaylistId)
  const select = useWorkbenchStore((s) => s.select)
  const hasJob = useWorkbenchStore((s) => item.id in s.jobs)
  const refresh = useRefreshPlaylist()
  const job = useJob(item.id)

  const running = hasJob && job.data !== undefined && (job.data.status === 'queued' || job.data.status === 'running')
  const failed = job.data?.status === 'error'

  return (
    <li className={`cursor-pointer rounded px-3 py-2 hover:bg-gray-100 ${selectedId === item.id ? 'bg-emerald-50 ring-1 ring-emerald-300' : ''}`} onClick={() => select(item.id)}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{item.name}</span>
        <span className="shrink-0 text-xs text-gray-400">{item.track_count ?? '—'}</span>
      </div>
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <span className="truncate">{item.owner_name}</span>
        {item.loaded && <span className="text-emerald-600">● loaded</span>}
        {!item.loaded && item.cached_at !== null && <span>cached</span>}
        <button
          type="button"
          title="Force refresh from Spotify"
          className="ml-auto rounded px-1 hover:bg-gray-200"
          onClick={(e) => {
            e.stopPropagation()
            refresh.mutate({ playlistId: item.id, force: true })
          }}
        >
          ⟳
        </button>
      </div>
      {running && job.data !== undefined && <ProgressBar job={job.data} />}
      {failed && <div className="mt-1 text-xs text-red-600">Refresh failed: {job.data?.error?.message ?? 'unknown error'}</div>}
    </li>
  )
}

/** Playlist picker: Liked Songs first, then all playlists, each with load state and inline refresh progress. */
export function Sidebar() {
  const playlists = usePlaylists()
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-3 py-3 text-sm font-semibold tracking-wide text-gray-700">LIBRARY</div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {playlists.isLoading && <p className="px-3 py-2 text-sm text-gray-400">Loading playlists…</p>}
        {playlists.isError && <p className="px-3 py-2 text-sm text-red-600">Could not load playlists — is the API server running?</p>}
        <ul className="space-y-0.5">
          {playlists.data?.items.map((item) => (
            <PlaylistEntry key={item.id} item={item} />
          ))}
        </ul>
      </div>
    </aside>
  )
}
