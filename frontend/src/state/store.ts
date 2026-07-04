import { create } from 'zustand'

/**
 * Cross-component workbench state. M0 holds the selected playlist and running refresh jobs;
 * M1 adds chart selections, M2 the organizer's buckets and rules.
 */
interface WorkbenchState {
  selectedPlaylistId: string | null
  /** playlistId -> id of the currently running refresh job. */
  jobs: Record<string, string>
  select: (playlistId: string) => void
  setJob: (playlistId: string, jobId: string) => void
  clearJob: (playlistId: string) => void
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  selectedPlaylistId: null,
  jobs: {},
  select: (playlistId) => set({ selectedPlaylistId: playlistId }),
  setJob: (playlistId, jobId) => set((s) => ({ jobs: { ...s.jobs, [playlistId]: jobId } })),
  clearJob: (playlistId) =>
    set((s) => {
      const { [playlistId]: _removed, ...rest } = s.jobs
      return { jobs: rest }
    }),
}))
