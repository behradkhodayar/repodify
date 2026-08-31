import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

function Hello() {
  return <h1>Repodify</h1>
}

describe('smoke', () => {
  it('renders', () => {
    render(<Hello />)
    expect(screen.getByText('Repodify')).toBeInTheDocument()
  })
})
