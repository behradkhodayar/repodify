import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo } from './Logo'

describe('Logo', () => {
  it('colors re and ify green and pod as the foreground (black/white)', () => {
    render(<Logo animate={false} />)
    expect(screen.getByText('re')).toHaveClass('text-wave')
    expect(screen.getByText('pod')).toHaveClass('text-foreground')
    expect(screen.getByText('ify')).toHaveClass('text-wave')
  })
})
