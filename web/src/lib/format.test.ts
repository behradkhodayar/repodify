import { describe, expect, it } from 'vitest'
import {
  elapsedLabel,
  latestLabel,
  parseInstant,
  parsePercent,
  PIPELINE_STAGES,
  pipelineElapsed,
  relativeTime,
  stockVoiceLabel,
} from './format'

describe('latestLabel', () => {
  const now = Date.parse('2026-01-10T00:00:00Z')

  it('formats day-scale freshness', () => {
    expect(latestLabel(Date.parse('2026-01-07T00:00:00Z') / 1000, now)).toBe('latest: 3 days ago')
  })

  it('returns null when unknown', () => {
    expect(latestLabel(null)).toBeNull()
    expect(latestLabel(0)).toBeNull()
  })
})

describe('relativeTime', () => {
  const now = Date.parse('2026-01-01T00:05:00Z')

  it('treats naive created_at as UTC so the local offset is not added', () => {
    expect(relativeTime('2026-01-01T00:00:00', now)).toBe('5m ago')
    expect(relativeTime('2026-01-01T00:00:00Z', now)).toBe('5m ago')
  })
})

describe('parsePercent', () => {
  it('reads the first 0–100 percent token', () => {
    expect(parsePercent('ep 1/3 · 40% · 1.2 MB')).toBe(40)
    expect(parsePercent('0%')).toBe(0)
    expect(parsePercent('100% done')).toBe(100)
  })

  it('returns null when missing or out of range', () => {
    expect(parsePercent(null)).toBeNull()
    expect(parsePercent('1/3')).toBeNull()
    expect(parsePercent('240%')).toBeNull()
  })
})

describe('parseInstant', () => {
  it('treats naive ISO timestamps as UTC, matching an explicit Z', () => {
    expect(parseInstant('2026-01-01T00:00:12')).toBe(Date.parse('2026-01-01T00:00:12Z'))
    expect(parseInstant('2026-01-01T00:00:12.000')).toBe(Date.parse('2026-01-01T00:00:12.000Z'))
  })

  it('keeps explicit offsets', () => {
    expect(parseInstant('2026-01-01T03:30:00+03:30')).toBe(Date.parse('2026-01-01T00:00:00Z'))
    expect(parseInstant('2026-01-01T00:00:00Z')).toBe(Date.parse('2026-01-01T00:00:00Z'))
  })
})

describe('elapsedLabel', () => {
  const from = '2026-01-01T00:00:00.000Z'
  const now = Date.parse('2026-01-01T00:00:12.000Z')

  it('formats seconds and minutes', () => {
    expect(elapsedLabel(from, '2026-01-01T00:00:12.000Z')).toBe('12s')
    expect(elapsedLabel(from, '2026-01-01T00:01:00.000Z')).toBe('1m')
    expect(elapsedLabel(from, '2026-01-01T00:01:03.000Z')).toBe('1m 03s')
  })

  it('returns empty for missing or inverted timestamps', () => {
    expect(elapsedLabel(null, from)).toBe('')
    expect(elapsedLabel(from, '2025-01-01T00:00:00.000Z')).toBe('')
  })

  it('does not add the local timezone offset to naive UTC timestamps', () => {
    expect(elapsedLabel('2026-01-01T00:00:00', null, now)).toBe('12s')
  })
})

describe('pipelineElapsed', () => {
  const resolveStart = '2026-01-01T00:00:00'
  const now = Date.parse('2026-01-01T00:00:25Z')

  it('is wall-clock from this job resolve start to assemble end, not a stage sum', () => {
    expect(
      pipelineElapsed(
        [
          {
            stage: 'resolve',
            started_at: resolveStart,
            finished_at: '2026-01-01T00:00:10',
          },
          {
            stage: 'download',
            started_at: '2026-01-01T00:00:10',
            finished_at: '2026-01-01T00:00:20',
          },
          {
            stage: 'assemble',
            started_at: '2026-01-01T00:00:20',
            finished_at: '2026-01-01T00:00:22',
          },
        ],
        now,
      ),
    ).toBe('22s')
  })

  it('ticks from resolve start until now while assemble is still running', () => {
    expect(
      pipelineElapsed(
        [
          {
            stage: 'resolve',
            started_at: resolveStart,
            finished_at: '2026-01-01T00:00:04',
          },
          { stage: 'assemble', started_at: '2026-01-01T00:00:20', finished_at: null },
        ],
        now,
      ),
    ).toBe('25s')
  })

  it('returns empty when this job has not started resolve', () => {
    expect(pipelineElapsed([{ stage: 'download', started_at: resolveStart, finished_at: null }])).toBe(
      '',
    )
  })
})

describe('stockVoiceLabel', () => {
  it('tags gender so unisex names stay unambiguous', () => {
    expect(stockVoiceLabel('Heart', 'female')).toBe('Heart (female)')
    expect(stockVoiceLabel('Adam', 'male')).toBe('Adam (male)')
    expect(stockVoiceLabel('Heart', null)).toBe('Heart')
  })
})

describe('PIPELINE_STAGES', () => {
  it('lists the nine tracked stages in order, without unused list', () => {
    expect(PIPELINE_STAGES).toEqual([
      'resolve',
      'download',
      'transcribe',
      'diarize',
      'summarize',
      'arc',
      'script',
      'tts',
      'assemble',
    ])
  })
})
