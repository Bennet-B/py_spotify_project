import { useEffect } from 'react'
import { isDatasetNotLoaded } from './api/client'
import { useJob, useRefreshPlaylist, useTracks } from './api/hooks'
import { Sidebar } from './components/Sidebar'
import { ProgressBar } from './components/ProgressBar'
import { TrackTable } from './features/library/TrackTable'
import { useWorkbenchStore } from './state/store'

function Main() {
  const selectedId = useWorkbenchStore((s) => s.selectedPlaylistId)
  const hasJob = useWorkbenchStore((s) => selectedId !== null && selectedId in s.jobs)
  const tracks = useTracks(selectedId)
  const refresh = useRefreshPlaylist()
  const job = useJob(selectedId)

  // A 409 on the tracks query means "not loaded yet" — kick off a refresh job exactly once per selection.
  useEffect(() => {
    if (selectedId !== null && !hasJob && tracks.isError && isDatasetNotLoaded(tracks.error) && !refresh.isPending) {
      refresh.mutate({ playlistId: selectedId, force: false })
    }
  }, [selectedId, hasJob, tracks.isError, tracks.error, refresh])

  if (selectedId === null) {
    return <p className="p-8 text-gray-400">Pick a playlist on the left to load and inspect it.</p>
  }
  if (tracks.data !== undefined) {
    return <TrackTable name={tracks.data.name} tracks={tracks.data.tracks} />
  }
  if (hasJob && job.data !== undefined) {
    return (
      <div className="max-w-md p-8">
        <p className="mb-2 text-gray-600">Loading playlist…</p>
        <ProgressBar job={job.data} />
      </div>
    )
  }
  if (tracks.isError && !isDatasetNotLoaded(tracks.error)) {
    return <p className="p-8 text-red-600">Failed to load tracks — check the API server logs.</p>
  }
  return <p className="p-8 text-gray-400">Loading…</p>
}

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <Sidebar />
      <main className="flex min-h-0 flex-1 flex-col">
        <Main />
      </main>
    </div>
  )
}
