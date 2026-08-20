export interface EpisodeOut {
  guid: string
  title: string
  published_at: string | null
  duration_s: number | null
  order_index: number
  is_short_or_trailer: boolean
}

export interface ResolveResponse {
  feed_title: string
  rss_url: string
  episodes: EpisodeOut[]
}

export interface CreateJobRequest {
  feed_url: string
  episode_ids: string[]
  host_count?: number
  clone?: boolean
  target_minutes?: number
}

export interface StageOut {
  stage: string
  state: string
  detail: string | null
  started_at: string | null
  finished_at: string | null
}

export interface JobStatusResponse {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  current_stage: string | null
  stages: StageOut[]
  report: { skipped?: string[]; warnings?: string[]; show_notes?: unknown }
}

export interface ChapterOut {
  title: string
  start_s: number
}

export interface ResultResponse {
  audio_mp3_url: string
  audio_wav_url: string
  summary: string
  chapters: ChapterOut[]
}

export interface JobSummaryOut {
  id: string
  status: string
  current_stage: string | null
  target_minutes: number
  created_at: string
}

export interface JobListResponse {
  jobs: JobSummaryOut[]
  total: number
}
