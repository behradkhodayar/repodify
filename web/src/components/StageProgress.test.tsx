import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { StageOut } from '../api/types'
import { StageProgress } from './StageProgress'

function stage(partial: Partial<StageOut> & Pick<StageOut, 'stage' | 'state'>): StageOut {
  return {
    detail: null,
    started_at: null,
    finished_at: null,
    ...partial,
  }
}

describe('StageProgress', () => {
  it('renders the full pipeline even when only one stage has started', () => {
    render(
      <StageProgress
        stages={[
          stage({
            stage: 'download',
            state: 'running',
            detail: 'Episode 1 · 1/3 · 40%',
            started_at: new Date().toISOString(),
          }),
        ]}
      />,
    )
    for (const name of [
      'resolve',
      'download',
      'transcribe',
      'diarize',
      'summarize',
      'arc',
      'script',
      'tts',
      'assemble',
    ]) {
      expect(screen.getByText(name)).toBeInTheDocument()
    }
    expect(screen.getByText(/1\/3 · 40%/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows a done stage detail without a spinner progress bar', () => {
    render(
      <StageProgress
        stages={[stage({ stage: 'resolve', state: 'done', detail: '2 episodes selected' })]}
      />,
    )
    expect(screen.getByText('2 episodes selected')).toBeInTheDocument()
  })
})
