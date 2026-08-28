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

// Harness where selection is real state, so the checkbox toggles it.
function StatefulHarness() {
  const [selected, setSelected] = useState<Set<string>>(new Set(['e1']))
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  return (
    <EpisodePicker
      episodes={[EP]}
      selected={selected}
      onToggle={(guid) =>
        setSelected((prev) => {
          const next = new Set(prev)
          if (next.has(guid)) next.delete(guid)
          else next.add(guid)
          return next
        })
      }
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

  it('collapses the note when its episode is deselected, keeping the typed text', async () => {
    const user = userEvent.setup()
    render(<StatefulHarness />)

    // Open the note and type into it.
    await user.click(screen.getByRole('button', { name: /add note/i }))
    await user.type(screen.getByLabelText(/note for ep one/i), 'hello')

    // Deselect the episode — its note controls disappear entirely.
    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    expect(screen.queryByRole('button', { name: /note/i })).not.toBeInTheDocument()

    // Re-select it — the note is collapsed again (not reopened)...
    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    expect(screen.queryByLabelText(/note for ep one/i)).not.toBeInTheDocument()
    // ...but the toggle shows "note" (not "add note"), so the text was kept.
    const toggle = screen.getByRole('button', { name: 'note' })
    await user.click(toggle)
    expect(screen.getByLabelText(/note for ep one/i)).toHaveValue('hello')
  })
})
