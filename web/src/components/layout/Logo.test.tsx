import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo } from './Logo'

describe('Logo', () => {
  it('colors re and ify gold and pod as the foreground (black/white)', () => {
    render(<Logo animate={false} />)
    expect(screen.getByText('re')).toHaveClass('text-wave')
    expect(screen.getByText('pod')).toHaveClass('text-foreground')
    expect(screen.getByText('ify')).toHaveClass('text-wave')
  })

  it('uses the brand favicon as the mark next to the wordmark', () => {
    const { container } = render(<Logo animate={false} />)
    const mark = container.querySelector('img')
    expect(mark).not.toBeNull()
    expect(mark).toHaveAttribute('src', `${import.meta.env.BASE_URL}favicon.svg`)
  })
})
