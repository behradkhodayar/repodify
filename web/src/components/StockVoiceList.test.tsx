import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { StockVoiceOut } from '../api/types'
import { StockVoiceList } from './StockVoiceList'

const VOICES: StockVoiceOut[] = [
  { id: 'af_heart', name: 'Heart', gender: 'female', sample_url: '/voices/af_heart/sample' },
  { id: 'am_adam', name: 'Adam', gender: 'male', sample_url: '/voices/am_adam/sample' },
]

function Harness() {
  const [preferred, setPreferred] = useState<string[]>(['af_heart'])
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <StockVoiceList voices={VOICES} preferredIds={preferred} onPreferredChange={setPreferred} />
    </QueryClientProvider>
  )
}

describe('StockVoiceList', () => {
  it('tags each voice with gender and a playable sample', () => {
    render(<Harness />)
    expect(screen.getByText('Heart')).toBeInTheDocument()
    expect(screen.getByText('female')).toBeInTheDocument()
    expect(screen.getByText('Adam')).toBeInTheDocument()
    expect(screen.getByText('male')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /play sample of heart/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /play sample of adam/i })).toBeInTheDocument()
  })

  it('toggles preferred voices', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const heart = screen.getByRole('checkbox', { name: /prefer heart \(female\)/i })
    const adam = screen.getByRole('checkbox', { name: /prefer adam \(male\)/i })
    expect(heart).toBeChecked()
    expect(adam).not.toBeChecked()
    await user.click(adam)
    expect(adam).toBeChecked()
    await user.click(heart)
    expect(heart).not.toBeChecked()
  })
})
