import { create } from 'zustand'
import type { components } from '../api/types.gen'

export type RuleIn = components['schemas']['BucketSpecIn']['rules'][number]
export type OrganizerSpecIn = components['schemas']['OrganizerSpecIn']

export interface ArtistSelection {
  id: string
  name: string
}

/** A bucket being edited in the UI; `id` is local-only (React keys), the API sees only name + rules. */
export interface BucketDraft {
  id: string
  name: string
  rules: RuleIn[]
}

/** Convert the current chart selections into rules (one per non-empty selection kind). */
export function selectionsToRules(selections: Selections): RuleIn[] {
  const rules: RuleIn[] = []
  if (selections.genres.length > 0) rules.push({ kind: 'tag', labels: selections.genres, field: 'genres' })
  if (selections.yearRange !== null) rules.push({ kind: 'year', min_year: selections.yearRange[0], max_year: selections.yearRange[1] })
  if (selections.durationRange !== null) rules.push({ kind: 'duration', min_seconds: selections.durationRange[0], max_seconds: selections.durationRange[1] })
  if (selections.artists.length > 0) rules.push({ kind: 'artist', artist_ids: selections.artists.map((a) => a.id) })
  if (selections.trackIds.length > 0) rules.push({ kind: 'track', track_ids: selections.trackIds })
  return rules
}

/** Chart-driven selection fragments â€” the raw material organizer rules are built from (M2). */
export interface Selections {
  genres: string[]
  yearRange: [number, number] | null
  /** Whole seconds, from the duration histogram's minute axis. */
  durationRange: [number, number] | null
  artists: ArtistSelection[]
  /** From the release-vs-added lasso. */
  trackIds: string[]
}

const EMPTY_SELECTIONS: Selections = { genres: [], yearRange: null, durationRange: null, artists: [], trackIds: [] }

/**
 * Cross-component workbench state: selected playlist, running refresh jobs, the active view, and chart selections.
 * Switching playlists resets the selections â€” they are meaningless against another library.
 */
interface WorkbenchState {
  selectedPlaylistId: string | null
  activeView: 'explore' | 'organize' | 'analyze' | 'tracks'
  /** playlistId -> id of the currently running refresh job. */
  jobs: Record<string, string>
  selections: Selections
  /** Organizer draft state. Buckets survive playlist switches (rules may apply to any source); selections do not. */
  buckets: BucketDraft[]
  activeBucketId: string | null
  allowDuplicates: boolean
  /** Artist id -> display name, remembered from chart clicks so artist rules render readable chips. */
  artistNames: Record<string, string>
  select: (playlistId: string) => void
  setView: (view: 'explore' | 'organize' | 'analyze' | 'tracks') => void
  setJob: (playlistId: string, jobId: string) => void
  clearJob: (playlistId: string) => void
  toggleGenre: (label: string) => void
  setYearRange: (range: [number, number] | null) => void
  setDurationRange: (range: [number, number] | null) => void
  toggleArtist: (artist: ArtistSelection) => void
  setTrackIds: (ids: string[]) => void
  clearSelections: () => void
  addBucket: () => void
  removeBucket: (bucketId: string) => void
  renameBucket: (bucketId: string, name: string) => void
  setActiveBucket: (bucketId: string) => void
  removeRule: (bucketId: string, ruleIndex: number) => void
  /** The selectionsâ†’rules moment: append the current selections to the active bucket as rules, then clear them. */
  addSelectionsToActiveBucket: () => void
  setAllowDuplicates: (allow: boolean) => void
  /** Replace the bucket drafts with a spec (used by suggest-split's "Load into organizer"). */
  setBucketsFromSpec: (spec: OrganizerSpecIn) => void
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  selectedPlaylistId: null,
  activeView: 'explore',
  jobs: {},
  selections: EMPTY_SELECTIONS,
  buckets: [],
  activeBucketId: null,
  allowDuplicates: true,
  artistNames: {},
  select: (playlistId) => set({ selectedPlaylistId: playlistId, selections: EMPTY_SELECTIONS }),
  setView: (view) => set({ activeView: view }),
  setJob: (playlistId, jobId) => set((s) => ({ jobs: { ...s.jobs, [playlistId]: jobId } })),
  clearJob: (playlistId) =>
    set((s) => {
      const { [playlistId]: _removed, ...rest } = s.jobs
      return { jobs: rest }
    }),
  toggleGenre: (label) =>
    set((s) => ({
      selections: {
        ...s.selections,
        genres: s.selections.genres.includes(label) ? s.selections.genres.filter((g) => g !== label) : [...s.selections.genres, label],
      },
    })),
  setYearRange: (range) => set((s) => ({ selections: { ...s.selections, yearRange: range } })),
  setDurationRange: (range) => set((s) => ({ selections: { ...s.selections, durationRange: range } })),
  toggleArtist: (artist) =>
    set((s) => ({
      artistNames: { ...s.artistNames, [artist.id]: artist.name },
      selections: {
        ...s.selections,
        artists: s.selections.artists.some((a) => a.id === artist.id) ? s.selections.artists.filter((a) => a.id !== artist.id) : [...s.selections.artists, artist],
      },
    })),
  setTrackIds: (ids) => set((s) => ({ selections: { ...s.selections, trackIds: ids } })),
  clearSelections: () => set({ selections: EMPTY_SELECTIONS }),
  addBucket: () =>
    set((s) => {
      const bucket: BucketDraft = { id: crypto.randomUUID(), name: `Bucket ${s.buckets.length + 1}`, rules: [] }
      return { buckets: [...s.buckets, bucket], activeBucketId: bucket.id }
    }),
  removeBucket: (bucketId) =>
    set((s) => ({
      buckets: s.buckets.filter((b) => b.id !== bucketId),
      activeBucketId: s.activeBucketId === bucketId ? null : s.activeBucketId,
    })),
  renameBucket: (bucketId, name) => set((s) => ({ buckets: s.buckets.map((b) => (b.id === bucketId ? { ...b, name } : b)) })),
  setActiveBucket: (bucketId) => set({ activeBucketId: bucketId }),
  removeRule: (bucketId, ruleIndex) => set((s) => ({ buckets: s.buckets.map((b) => (b.id === bucketId ? { ...b, rules: b.rules.filter((_, i) => i !== ruleIndex) } : b)) })),
  addSelectionsToActiveBucket: () => {
    const { activeBucketId, selections, buckets } = get()
    const rules = selectionsToRules(selections)
    if (activeBucketId === null || rules.length === 0) return
    set({
      buckets: buckets.map((b) => (b.id === activeBucketId ? { ...b, rules: [...b.rules, ...rules] } : b)),
      selections: EMPTY_SELECTIONS,
    })
  },
  setAllowDuplicates: (allow) => set({ allowDuplicates: allow }),
  setBucketsFromSpec: (spec) => {
    const buckets = spec.buckets.map((bucket) => ({ id: crypto.randomUUID(), name: bucket.name, rules: bucket.rules }))
    set({ buckets, allowDuplicates: spec.allow_duplicates ?? true, activeBucketId: buckets[0]?.id ?? null, activeView: 'organize' })
  },
}))
