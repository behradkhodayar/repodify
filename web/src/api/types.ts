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
  cached?: boolean
}

export interface CandidateOut {
  title: string
  author: string
  feed_url: string
  artwork: string | null
  itunes_id: number | null
  pi_feed_id: number | null
  newest_item: number | null
  episode_count: number | null
  language: string | null
  sources: string[]
  identity: string
  cached: boolean
  dead: boolean
}

export interface SearchResponse {
  query: string
  kind: string
  candidates: CandidateOut[]
  degraded: boolean
  cached: boolean
  warning: string | null
}

export interface VoiceAssignment {
  speaker_id: string
  mode: 'clone' | 'stock'
  stock_voice?: string | null
  display_name?: string | null
}

export interface CreateJobRequest {
  feed_url: string
  episode_ids: string[]
  host_count?: number
  clone?: boolean
  target_minutes?: number
  voice_assignments?: VoiceAssignment[]
  preserve_speakers?: boolean
  review_voices?: boolean
  custom_prompt?: string | null
  episode_prompts?: Record<string, string>
}

export interface StockVoiceOut {
  id: string
  name: string
  gender: 'female' | 'male' | null
  sample_url: string
}

export interface VoicesResponse {
  stock_voices: string[]
  voices: StockVoiceOut[]
}

export interface VoiceSettingsResponse {
  preferred_stock_voices: string[]
}

export interface VoiceSettingsUpdate {
  preferred_stock_voices: string[]
}

export interface SpeakerOut {
  speaker_id: string
  speaking_seconds: number
  display_name?: string | null
  gender?: 'female' | 'male' | null
}

export interface SpeakersResponse {
  status: string
  speakers: SpeakerOut[]
}

export interface SubmitVoicesRequest {
  voice_assignments: VoiceAssignment[]
}

export interface StageOut {
  stage: string
  state: string
  detail: string | null
  started_at: string | null
  finished_at: string | null
}

export interface GateInfo {
  openrouter_configured?: boolean
  anthropic_configured?: boolean
  pyannoteai_configured?: boolean
  hf_token_configured?: boolean
  whisper_model?: string
  ollama_model?: string
  openrouter_llm_model?: string
  openrouter_tts_model?: string
  openrouter_stt_model?: string
  pyannoteai_model?: string
  speakers?: SpeakerOut[]
}

export interface ContinueJobRequest {
  gate: 'transcribe' | 'diarize' | 'voices' | 'summarize' | 'tts'
  payload: Record<string, unknown>
}

export interface JobStatusResponse {
  id: string
  status: 'queued' | 'running' | 'awaiting_review' | 'awaiting_config' | 'completed' | 'failed'
  current_stage: string | null
  stages: StageOut[]
  report: { skipped?: string[]; warnings?: string[]; show_notes?: unknown; gate?: string }
  gate?: string | null
  gate_info?: GateInfo
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

export interface LlmSettingsResponse {
  backend: string
  openrouter_model: string
  ollama_model: string
  anthropic_map_model: string
  anthropic_reduce_model: string
  available_backends: string[]
  openrouter_configured: boolean
}

export interface LlmSettingsUpdate {
  backend?: string
  openrouter_model?: string
  ollama_model?: string
}

export interface AppSettingsResponse {
  whisper_model: string
  whisper_models: string[]
  ollama_model: string
  ollama_base_url: string
  diarization_model: string
  hf_token_configured: boolean
  openrouter_stt_model: string
  openrouter_llm_model: string
  openrouter_tts_model: string
  openrouter_configured: boolean
  anthropic_map_model: string
  anthropic_reduce_model: string
  anthropic_configured: boolean
  pyannoteai_model: string
  pyannoteai_configured: boolean
}

export interface AppSettingsUpdate {
  whisper_model?: string
  ollama_model?: string
  ollama_base_url?: string
  diarization_model?: string
  hf_token?: string
  openrouter_stt_model?: string
  openrouter_llm_model?: string
  openrouter_tts_model?: string
  openrouter_api_key?: string
  map_model?: string
  reduce_model?: string
  anthropic_api_key?: string
  pyannoteai_model?: string
  pyannoteai_api_key?: string
}
