import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { ApiError, api } from './client'

describe('api client', () => {
  it('omits Authorization when no token is set', async () => {
    let auth: string | null = 'unset'
    server.use(
      http.get('/jobs', ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ jobs: [], total: 0 })
      }),
    )
    await api.getJobs()
    expect(auth).toBeNull()
  })

  it('sends Bearer token when set', async () => {
    localStorage.setItem('api_token', 'secret')
    let auth: string | null = null
    server.use(
      http.get('/jobs', ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ jobs: [], total: 0 })
      }),
    )
    await api.getJobs()
    expect(auth).toBe('Bearer secret')
  })

  it('throws ApiError with status on non-2xx', async () => {
    server.use(http.get('/jobs/x', () => new HttpResponse('nope', { status: 404 })))
    await expect(api.getJob('x')).rejects.toMatchObject({ status: 404 })
    await expect(api.getJob('x')).rejects.toBeInstanceOf(ApiError)
  })

  it('gets and updates llm settings', async () => {
    server.use(
      http.get('/settings/llm', () =>
        HttpResponse.json({
          backend: 'anthropic',
          openrouter_model: 'openai/gpt-4o-mini',
          ollama_model: 'qwen2.5-coder:7b',
          anthropic_map_model: 'claude-haiku-4-5-20251001',
          anthropic_reduce_model: 'claude-opus-4-8',
          available_backends: ['anthropic', 'ollama', 'openrouter'],
          openrouter_configured: true,
        }),
      ),
      http.put('/settings/llm', async ({ request }) => {
        const body = (await request.json()) as { backend?: string }
        return HttpResponse.json({
          backend: body.backend ?? 'anthropic',
          openrouter_model: 'openai/gpt-4o-mini',
          ollama_model: 'qwen2.5-coder:7b',
          anthropic_map_model: 'claude-haiku-4-5-20251001',
          anthropic_reduce_model: 'claude-opus-4-8',
          available_backends: ['anthropic', 'ollama', 'openrouter'],
          openrouter_configured: true,
        })
      }),
    )
    expect((await api.getLlmSettings()).backend).toBe('anthropic')
    expect((await api.updateLlmSettings({ backend: 'openrouter' })).backend).toBe('openrouter')
  })

  it('gets and updates app settings', async () => {
    server.use(
      http.get('/settings', () =>
        HttpResponse.json({
          whisper_model: 'small',
          whisper_models: ['small'],
          ollama_model: 'qwen2.5-coder:7b',
          ollama_base_url: 'http://localhost:11434',
          diarization_model: 'pyannote/speaker-diarization-community-1',
          hf_token_configured: false,
          openrouter_stt_model: 'openai/whisper-large-v3',
          openrouter_llm_model: 'openai/gpt-4o-mini',
          openrouter_tts_model: 'fish-audio/s2.1-pro',
          openrouter_configured: true,
          anthropic_map_model: 'haiku',
          anthropic_reduce_model: 'opus',
          anthropic_configured: false,
          pyannoteai_model: 'community-1',
          pyannoteai_configured: false,
        }),
      ),
      http.put('/settings', async ({ request }) => {
        const body = (await request.json()) as { whisper_model?: string }
        return HttpResponse.json({
          whisper_model: body.whisper_model ?? 'small',
          whisper_models: ['small'],
          ollama_model: 'qwen2.5-coder:7b',
          ollama_base_url: 'http://localhost:11434',
          diarization_model: 'pyannote/speaker-diarization-community-1',
          hf_token_configured: false,
          openrouter_stt_model: 'openai/whisper-large-v3',
          openrouter_llm_model: 'openai/gpt-4o-mini',
          openrouter_tts_model: 'fish-audio/s2.1-pro',
          openrouter_configured: true,
          anthropic_map_model: 'haiku',
          anthropic_reduce_model: 'opus',
          anthropic_configured: false,
          pyannoteai_model: 'community-1',
          pyannoteai_configured: false,
        })
      }),
    )
    expect((await api.getAppSettings()).whisper_model).toBe('small')
    expect((await api.updateAppSettings({ whisper_model: 'base' })).whisper_model).toBe('base')
  })
})
