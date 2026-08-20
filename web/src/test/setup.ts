import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './msw'

// jsdom's localStorage is unavailable on an opaque origin, and Node's experimental
// global localStorage is undefined without --localstorage-file. Provide a
// deterministic in-memory Storage so the app's real localStorage usage is testable.
class MemoryStorage {
  private store = new Map<string, string>()
  get length() {
    return this.store.size
  }
  clear() {
    this.store.clear()
  }
  getItem(key: string) {
    return this.store.get(key) ?? null
  }
  key(index: number) {
    return [...this.store.keys()][index] ?? null
  }
  removeItem(key: string) {
    this.store.delete(key)
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value))
  }
}

try {
  Object.defineProperty(globalThis, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  })
} catch {
  ;(globalThis as unknown as { localStorage: MemoryStorage }).localStorage = new MemoryStorage()
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())
