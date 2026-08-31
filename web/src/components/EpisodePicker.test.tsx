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

function ep(
  partial: Partial<EpisodeOut> & Pick<EpisodeOut, 'guid' | 'title' | 'order_index'>,
): EpisodeOut {
  return {
    published_at: null,
    duration_s: 60,
    is_short_or_trailer: false,
    ...partial,
  }
}

function ListHarness({
  episodes,
  initialSelected = new Set<string>(),
}: {
  episodes: EpisodeOut[]
  initialSelected?: Set<string>
}) {
  const [selected, setSelected] = useState(new Set(initialSelected))
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  return (
    <EpisodePicker
      episodes={episodes}
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

function checkboxNames(): string[] {
  return screen.getAllByRole('checkbox').map((el) => el.getAttribute('aria-label') ?? '')
}

const OLD = ep({ guid: 'old', title: 'Alpha Episode', order_index: 0 })
const NEW = ep({ guid: 'new', title: 'Beta Latest', order_index: 1 })

describe('EpisodePicker filter and sort', () => {
  it('lists newest first by default', () => {
    render(<ListHarness episodes={[OLD, NEW]} />)
    expect(checkboxNames()).toEqual(['Beta Latest', 'Alpha Episode'])
    expect(screen.getByLabelText(/sort episodes/i)).toHaveValue('newest')
    expect(screen.getByText('Showing 2 episodes')).toBeInTheDocument()
  })

  it('lists oldest first when that sort is chosen', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.selectOptions(screen.getByLabelText(/sort episodes/i), 'oldest')
    expect(checkboxNames()).toEqual(['Alpha Episode', 'Beta Latest'])
  })

  it('filters titles case-insensitively', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), 'alpha')
    expect(checkboxNames()).toEqual(['Alpha Episode'])
    expect(screen.getByText('Showing 1 of 2 episodes')).toBeInTheDocument()
  })

  it('treats a whitespace-only query as no filter', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), '   ')
    expect(checkboxNames()).toEqual(['Beta Latest', 'Alpha Episode'])
    expect(screen.getByText('Showing 2 episodes')).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), 'zzzz')
    expect(screen.getByText('No episodes match “zzzz”.')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByText('Showing 0 of 2 episodes')).toBeInTheDocument()
  })

  it('keeps a selection after the query hides then reveals the episode', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.click(screen.getByRole('checkbox', { name: 'Alpha Episode' }))
    expect(screen.getByRole('checkbox', { name: 'Alpha Episode' })).toBeChecked()

    await user.type(screen.getByLabelText(/filter episodes/i), 'beta')
    expect(screen.queryByRole('checkbox', { name: 'Alpha Episode' })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Beta Latest' })).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/filter episodes/i))
    expect(screen.getByRole('checkbox', { name: 'Alpha Episode' })).toBeChecked()
  })
})
