import { useArtists, useLabels, useReleaseVsAdded, useYears } from '../../api/hooks'
import type { TrackRow } from '../../api/hooks'
import { useWorkbenchStore } from '../../state/store'
import { ChartCard } from './ChartCard'
import { LabelBarChart } from './LabelBarChart'
import { ArtistChart } from './ArtistChart'
import { YearChart } from './YearChart'
import { DurationHistogram } from './DurationHistogram'
import { ReleaseVsAddedScatter } from './ReleaseVsAddedScatter'
import { AdditionsChart, CumulativeHoursChart, DiscoveryChart, SeasonalChart } from './TimelineCharts'
import { SelectionChips } from './SelectionChips'

/** The explore workbench: rule-helper charts (top) and timeline insights (bottom), all feeding the selection chip bar. */
export function ExploreView({ playlistId, tracks }: { playlistId: string; tracks: TrackRow[] }) {
  const selections = useWorkbenchStore((s) => s.selections)
  const toggleGenre = useWorkbenchStore((s) => s.toggleGenre)
  const toggleArtist = useWorkbenchStore((s) => s.toggleArtist)
  const setYearRange = useWorkbenchStore((s) => s.setYearRange)
  const setDurationRange = useWorkbenchStore((s) => s.setDurationRange)
  const setTrackIds = useWorkbenchStore((s) => s.setTrackIds)

  const labels = useLabels(playlistId)
  const artists = useArtists(playlistId, selections.genres)
  const years = useYears(playlistId)
  const releaseVsAdded = useReleaseVsAdded(playlistId)

  const scopeHint = selections.genres.length > 0 ? `within ${selections.genres.join(', ')}` : 'all genres'

  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      <SelectionChips />
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <ChartCard title="Genres" hint="click bars to select">
          {labels.data !== undefined && <LabelBarChart rows={labels.data.rows} selected={selections.genres} onToggle={toggleGenre} />}
        </ChartCard>
        <ChartCard title="Artists" hint={`click to select · ${scopeHint}`}>
          {artists.data !== undefined && <ArtistChart rows={artists.data.rows} selected={selections.artists} onToggle={toggleArtist} />}
        </ChartCard>
        <ChartCard title="Release years" hint="drag to select a range · double-click to clear">
          {years.data !== undefined && <YearChart rows={years.data.rows} range={selections.yearRange} onRange={setYearRange} />}
        </ChartCard>
        <ChartCard title="Track length" hint="drag to select a range · double-click to clear">
          <DurationHistogram tracks={tracks} onRange={setDurationRange} />
        </ChartCard>
        <ChartCard title="Released vs added" hint="lasso dots to capture tracks · double-click to clear" className="xl:col-span-2">
          {releaseVsAdded.data !== undefined && <ReleaseVsAddedScatter rows={releaseVsAdded.data.rows} onTracks={setTrackIds} />}
        </ChartCard>
        <ChartCard title="Additions per month">
          <AdditionsChart playlistId={playlistId} />
        </ChartCard>
        <ChartCard title="Cumulative listening hours">
          <CumulativeHoursChart playlistId={playlistId} />
        </ChartCard>
        <ChartCard title="Artist discovery waves">
          <DiscoveryChart playlistId={playlistId} />
        </ChartCard>
        <ChartCard title="Seasonal profile">
          <SeasonalChart playlistId={playlistId} />
        </ChartCard>
      </div>
    </div>
  )
}
