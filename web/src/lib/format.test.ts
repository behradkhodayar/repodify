import { describe, expect, it } from 'vitest'
import { elapsedLabel, latestLabel, parsePercent, PIPELINE_STAGES, stockVoiceLabel } from './format'

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

describe('elapsedLabel', () => {
  const from = '2026-01-01T00:00:00.000Z'

  it('formats seconds and minutes', () => {
    expect(elapsedLabel(from, '2026-01-01T00:00:12.000Z')).toBe('12s')
    expect(elapsedLabel(from, '2026-01-01T00:01:00.000Z')).toBe('1m')
    expect(elapsedLabel(from, '2026-01-01T00:01:03.000Z')).toBe('1m 03s')
  })

  it('returns empty for missing or inverted timestamps', () => {
    expect(elapsedLabel(null, from)).toBe('')
    expect(elapsedLabel(from, '2025-01-01T00:00:00.000Z')).toBe('')
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
