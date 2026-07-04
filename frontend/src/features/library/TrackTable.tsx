import type { TrackRow } from '../../api/hooks'
import { formatDate, formatDuration } from '../../lib/format'

const MAX_RENDERED_ROWS = 1000

/** Plain sortable-later track table; M0 renders the flattened rows as-is, capped for DOM sanity. */
export function TrackTable({ name, tracks }: { name: string; tracks: TrackRow[] }) {
  const rows = tracks.slice(0, MAX_RENDERED_ROWS)
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-baseline gap-3 px-4 py-3">
        <h1 className="text-lg font-semibold">{name}</h1>
        <span className="text-sm text-gray-500">
          {tracks.length.toLocaleString()} tracks
          {tracks.length > MAX_RENDERED_ROWS && ` (showing first ${MAX_RENDERED_ROWS.toLocaleString()})`}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-4 pb-4">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="border-b border-gray-200 px-2 py-2">#</th>
              <th className="border-b border-gray-200 px-2 py-2">Title</th>
              <th className="border-b border-gray-200 px-2 py-2">Artists</th>
              <th className="border-b border-gray-200 px-2 py-2">Album</th>
              <th className="border-b border-gray-200 px-2 py-2">Year</th>
              <th className="border-b border-gray-200 px-2 py-2">Length</th>
              <th className="border-b border-gray-200 px-2 py-2">Added</th>
              <th className="border-b border-gray-200 px-2 py-2">Genres</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((track, index) => (
              <tr key={track.track_id ?? `local-${index}`} className="hover:bg-gray-50">
                <td className="border-b border-gray-100 px-2 py-1.5 text-gray-400">{index + 1}</td>
                <td className="max-w-64 truncate border-b border-gray-100 px-2 py-1.5 font-medium">{track.name}</td>
                <td className="max-w-56 truncate border-b border-gray-100 px-2 py-1.5">{track.artist_names.join(', ')}</td>
                <td className="max-w-56 truncate border-b border-gray-100 px-2 py-1.5 text-gray-500">{track.album_name}</td>
                <td className="border-b border-gray-100 px-2 py-1.5">{track.release_year ?? '—'}</td>
                <td className="border-b border-gray-100 px-2 py-1.5 tabular-nums">{formatDuration(track.duration_ms)}</td>
                <td className="border-b border-gray-100 px-2 py-1.5 text-gray-500">{formatDate(track.added_at)}</td>
                <td className="max-w-64 truncate border-b border-gray-100 px-2 py-1.5 text-gray-500">{track.genres.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
