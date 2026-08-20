import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { CreateJobRequest } from './types'

export function useResolveFeed() {
  return useMutation({ mutationFn: (url: string) => api.resolveFeed(url) })
}

export function useCreateJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateJobRequest) => api.createJob(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useJobs(limit = 50, offset = 0) {
  return useQuery({ queryKey: ['jobs', limit, offset], queryFn: () => api.getJobs(limit, offset) })
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => api.getJob(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 2000
    },
  })
}

export function useResult(id: string, enabled: boolean) {
  return useQuery({ queryKey: ['result', id], queryFn: () => api.getResult(id), enabled })
}
