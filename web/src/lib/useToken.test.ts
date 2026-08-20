import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useToken } from './useToken'

describe('useToken', () => {
  it('reads and writes localStorage', () => {
    const { result } = renderHook(() => useToken())
    expect(result.current.token).toBe('')
    act(() => result.current.setToken('secret'))
    expect(localStorage.getItem('api_token')).toBe('secret')
    expect(result.current.token).toBe('secret')
  })
})
