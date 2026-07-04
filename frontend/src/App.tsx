import { useEffect } from 'react'
import { isDatasetNotLoaded } from './api/client'
import { useJob, useRefreshPlaylist, useTracks } from './api/hooks'
import { Sidebar } from './components/Sidebar'
import { ProgressBar } from './components/ProgressBar'
import { TrackTable } from './features/library/TrackTable'
import { ExploreView } from './features/explore/ExploreView'
import { OrganizerView } from './features/organizer/OrganizerView'
import { useWorkbenchStore } from './state/store'

function ViewTabs() {
  const activeView = useWorkbenchStore((s) => s.activeView)
  const setView = useWorkbenchStore((s) => s.setView)
  const tabs = [
    { id: 'explore', label: 'Explore' },
    { id: 'organize', label: 'Organize' },
    { id: 'tracks', label: 'Tracks' },
  ] as const
  return (
    <nav className="flex gap-1 border-b border-gray-200 bg-white px-4 pt-2">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => setView(tab.id)}
          className={`rounded-t px-4 py-2 text-sm font-medium ${activeView === tab.id ? 'border-x border-t border-gray-200 bg-gray-50 text-gray-900' : 'text-gray-500 hover:text-gray-800'}`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  )
}

function Main() {
  const selectedId = useWorkbenchStore((s) => s.selectedPlaylistId)
  const activeView = useWorkbenchStore((s) => s.activeView)
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
    return <p className="p-8 text-gray-400">Pick a playlist on the left to load and explore it.</p>
  }
  if (tracks.data !== undefined) {
    return (
      <>
        <ViewTabs />
        {activeView === 'explore' && <ExploreView playlistId={selectedId} tracks={tracks.data.tracks} />}
        {activeView === 'organize' && <OrganizerView playlistId={selectedId} tracks={tracks.data.tracks} />}
        {activeView === 'tracks' && <TrackTable name={tracks.data.name} tracks={tracks.data.tracks} />}
      </>
    )
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
