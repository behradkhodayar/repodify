import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AudioPlayer } from './AudioPlayer'

describe('AudioPlayer', () => {
  it('seeks to a chapter start on click', async () => {
    render(
      <AudioPlayer
        jobId="j1"
        chapters={[
          { title: 'Intro', start_s: 0 },
          { title: 'Part 2', start_s: 42 },
        ]}
      />,
    )
    const audio = document.querySelector('audio') as HTMLAudioElement
    let seeked = -1
    Object.defineProperty(audio, 'currentTime', {
      configurable: true,
      get: () => seeked,
      set: (v: number) => {
        seeked = v
      },
    })
    await userEvent.click(screen.getByRole('button', { name: /part 2/i }))
    expect(seeked).toBe(42)
  })

  it('points at the mp3 endpoint', () => {
    render(<AudioPlayer jobId="j1" chapters={[]} />)
    const audio = document.querySelector('audio') as HTMLAudioElement
    expect(audio.getAttribute('src')).toBe('/jobs/j1/audio?format=mp3')
  })
})
