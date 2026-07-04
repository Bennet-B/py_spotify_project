import { create } from 'zustand'

export interface ArtistSelection {
  id: string
  name: string
}

/** Chart-driven selection fragments — the raw material organizer rules are built from (M2). */
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
 * Switching playlists resets the selections — they are meaningless against another library.
 */
interface WorkbenchState {
  selectedPlaylistId: string | null
  activeView: 'explore' | 'tracks'
  /** playlistId -> id of the currently running refresh job. */
  jobs: Record<string, string>
  selections: Selections
  select: (playlistId: string) => void
  setView: (view: 'explore' | 'tracks') => void
  setJob: (playlistId: string, jobId: string) => void
  clearJob: (playlistId: string) => void
  toggleGenre: (label: string) => void
  setYearRange: (range: [number, number] | null) => void
  setDurationRange: (range: [number, number] | null) => void
  toggleArtist: (artist: ArtistSelection) => void
  setTrackIds: (ids: string[]) => void
  clearSelections: () => void
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  selectedPlaylistId: null,
  activeView: 'explore',
  jobs: {},
  selections: EMPTY_SELECTIONS,
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
      selections: {
        ...s.selections,
        artists: s.selections.artists.some((a) => a.id === artist.id) ? s.selections.artists.filter((a) => a.id !== artist.id) : [...s.selections.artists, artist],
      },
    })),
  setTrackIds: (ids) => set((s) => ({ selections: { ...s.selections, trackIds: ids } })),
  clearSelections: () => set({ selections: EMPTY_SELECTIONS }),
}))
