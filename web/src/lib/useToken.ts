import { useState } from 'react'

export function useToken() {
  const [token, setTokenState] = useState(() => localStorage.getItem('api_token') ?? '')
  function setToken(value: string) {
    if (value) localStorage.setItem('api_token', value)
    else localStorage.removeItem('api_token')
    setTokenState(value)
  }
  return { token, setToken }
}
