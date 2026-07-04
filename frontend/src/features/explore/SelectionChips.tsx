import { useWorkbenchStore } from '../../state/store'
import { formatDuration } from '../../lib/format'

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-200">
      {label}
      <button type="button" className="rounded-full px-0.5 text-emerald-600 hover:bg-emerald-100" onClick={onRemove} title="Remove">
        ×
      </button>
    </span>
  )
}

/** The rule-fragment bar: every chart selection appears here as a removable chip — in M2 these feed the organizer's bucket rules. */
export function SelectionChips() {
  const selections = useWorkbenchStore((s) => s.selections)
  const toggleGenre = useWorkbenchStore((s) => s.toggleGenre)
  const setYearRange = useWorkbenchStore((s) => s.setYearRange)
  const setDurationRange = useWorkbenchStore((s) => s.setDurationRange)
  const toggleArtist = useWorkbenchStore((s) => s.toggleArtist)
  const setTrackIds = useWorkbenchStore((s) => s.setTrackIds)
  const clearSelections = useWorkbenchStore((s) => s.clearSelections)

  const empty = selections.genres.length === 0 && selections.yearRange === null && selections.durationRange === null && selections.artists.length === 0 && selections.trackIds.length === 0

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5">
      <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-gray-400">Selection</span>
      {empty && <span className="text-xs text-gray-400">Click genre/artist bars, box-select years or durations, lasso the scatter — selections collect here as rule fragments.</span>}
      {selections.genres.map((genre) => (
        <Chip key={`g-${genre}`} label={`genre: ${genre}`} onRemove={() => toggleGenre(genre)} />
      ))}
      {selections.yearRange !== null && (
        <Chip
          label={selections.yearRange[0] === selections.yearRange[1] ? `year: ${selections.yearRange[0]}` : `years: ${selections.yearRange[0]}–${selections.yearRange[1]}`}
          onRemove={() => setYearRange(null)}
        />
      )}
      {selections.durationRange !== null && (
        <Chip label={`length: ${formatDuration(selections.durationRange[0] * 1000)}–${formatDuration(selections.durationRange[1] * 1000)}`} onRemove={() => setDurationRange(null)} />
      )}
      {selections.artists.map((artist) => (
        <Chip key={`a-${artist.id}`} label={`artist: ${artist.name}`} onRemove={() => toggleArtist(artist)} />
      ))}
      {selections.trackIds.length > 0 && <Chip label={`${selections.trackIds.length} tracks from scatter`} onRemove={() => setTrackIds([])} />}
      {!empty && (
        <span className="ml-auto flex items-center gap-3">
          <AddToBucketButton />
          <button type="button" className="text-xs text-gray-400 underline-offset-2 hover:text-gray-600 hover:underline" onClick={clearSelections}>
            Clear all
          </button>
        </span>
      )}
    </div>
  )
}

/** Turns the current selections into rules on the active bucket (creating a first bucket if none exists) and jumps to the organizer. */
function AddToBucketButton() {
  const buckets = useWorkbenchStore((s) => s.buckets)
  const activeBucketId = useWorkbenchStore((s) => s.activeBucketId)
  const addBucket = useWorkbenchStore((s) => s.addBucket)
  const addSelectionsToActiveBucket = useWorkbenchStore((s) => s.addSelectionsToActiveBucket)
  const setView = useWorkbenchStore((s) => s.setView)
  const activeName = buckets.find((b) => b.id === activeBucketId)?.name

  function handleClick() {
    if (activeBucketId === null) addBucket()
    addSelectionsToActiveBucket()
    setView('organize')
  }

  return (
    <button type="button" className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-700" onClick={handleClick}>
      Add to {activeName !== undefined ? `“${activeName}”` : 'new bucket'} →
    </button>
  )
}
