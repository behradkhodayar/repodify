import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { EpisodePicker } from './EpisodePicker'
import type { EpisodeOut } from '../api/types'

const EP: EpisodeOut = {
  guid: 'e1', title: 'Ep One', published_at: null,
  duration_s: 60, order_index: 0, is_short_or_trailer: false,
}

function Harness() {
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  return (
    <EpisodePicker
      episodes={[EP]}
      selected={new Set(['e1'])}
      onToggle={() => {}}
      prompts={prompts}
      onPromptChange={(guid, value) => setPrompts((p) => ({ ...p, [guid]: value }))}
    />
  )
}

describe('EpisodePicker per-episode notes', () => {
  it('reveals a note textarea for a selected episode and records typed text', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    // Textarea hidden until the note is opened.
    expect(screen.queryByLabelText(/note for ep one/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /add note/i }))
    const box = screen.getByLabelText(/note for ep one/i)
    await user.type(box, 'keep the interview')
    expect(box).toHaveValue('keep the interview')
  })
})
