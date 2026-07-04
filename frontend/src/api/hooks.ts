import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { components } from './types.gen'
import { useWorkbenchStore } from '../state/store'

export type PlaylistItem = components['schemas']['PlaylistItem']
export type JobOut = components['schemas']['JobOut']
export type TrackRow = components['schemas']['TrackRow']

const JOB_POLL_INTERVAL_MS = 750

/** The sidebar's playlist list (Liked Songs first). */
export function usePlaylists() {
  return useQuery({
    queryKey: ['playlists'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/playlists')
      if (error) throw error
      return data
    },
  })
}

/** Flattened track rows of a loaded playlist; surfaces the 409 envelope as the query error until a refresh job has run. */
export function useTracks(playlistId: string | null) {
  return useQuery({
    queryKey: ['tracks', playlistId],
    enabled: playlistId !== null,
    retry: false, // the 409 before first load is expected, not transient
    queryFn: async () => {
      const { data, error } = await api.GET('/api/playlists/{playlist_id}/tracks', { params: { path: { playlist_id: playlistId! } } })
      if (error) throw error
      return data
    },
  })
}

/** Start a refresh job for a playlist and remember its id in the store (server-side dedupe makes double-clicks harmless). */
export function useRefreshPlaylist() {
  const setJob = useWorkbenchStore((s) => s.setJob)
  return useMutation({
    mutationFn: async ({ playlistId, force }: { playlistId: string; force: boolean }) => {
      const { data, error } = await api.POST('/api/playlists/{playlist_id}/refresh', {
        params: { path: { playlist_id: playlistId } },
        body: { force },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data, { playlistId }) => setJob(playlistId, data.job_id),
  })
}

/** Poll a job while it is queued/running; on completion, clear it from the store and refetch the affected queries. */
export function useJob(playlistId: string | null) {
  const jobId = useWorkbenchStore((s) => (playlistId !== null ? (s.jobs[playlistId] ?? null) : null))
  const clearJob = useWorkbenchStore((s) => s.clearJob)
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['job', jobId],
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'error' ? false : JOB_POLL_INTERVAL_MS
    },
    queryFn: async () => {
      const { data, error } = await api.GET('/api/jobs/{job_id}', { params: { path: { job_id: jobId! } } })
      if (error) throw error
      if ((data.status === 'done' || data.status === 'error') && playlistId !== null) {
        clearJob(playlistId)
        void queryClient.invalidateQueries({ queryKey: ['playlists'] })
        void queryClient.invalidateQueries({ queryKey: ['tracks', playlistId] })
      }
      return data
    },
  })
}
