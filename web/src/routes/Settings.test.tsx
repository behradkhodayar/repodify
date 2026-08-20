import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Settings } from './Settings'

describe('Settings', () => {
  it('saves the token to localStorage', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })
})
