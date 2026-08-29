import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { CreateJobRequest, LlmSettingsUpdate, SubmitVoicesRequest } from './types'

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

export function useVoices() {
  return useQuery({ queryKey: ['voices'], queryFn: () => api.getVoices() })
}

export function useSpeakers(id: string, enabled: boolean) {
  return useQuery({ queryKey: ['speakers', id], queryFn: () => api.getSpeakers(id), enabled })
}

export function useSubmitVoices(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SubmitVoicesRequest) => api.submitVoices(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job', id] }),
  })
}

export function useLlmSettings() {
  return useQuery({ queryKey: ['llm-settings'], queryFn: () => api.getLlmSettings() })
}

export function useUpdateLlmSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LlmSettingsUpdate) => api.updateLlmSettings(body),
    onSuccess: (data) => qc.setQueryData(['llm-settings'], data),
  })
}
