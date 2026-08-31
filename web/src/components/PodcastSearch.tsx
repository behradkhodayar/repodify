import { Podcast, Rss, Search } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { api } from '../api/client'
import type { CandidateOut, SearchResponse } from '../api/types'
import { latestLabel } from '../lib/format'
import { cn } from '../lib/utils'
import { Input } from './ui/input'

const MIN_CHARS = 3
const DEBOUNCE_MS = 300

function isAbortError(err: unknown): boolean {
  return (
    (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  )
}

/** In-house equalizer pulse — CSS only, Lucide mic, no extra licensed assets. */
function SearchingIndicator({ labelled = false }: { labelled?: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5"
      role={labelled ? 'status' : undefined}
      aria-label={labelled ? 'Searching' : undefined}
      aria-hidden={labelled ? undefined : true}
    >
      <Podcast className="size-3.5 text-primary" aria-hidden />
      <span className="flex h-3.5 items-end gap-px" aria-hidden>
        <span className="eq-bar h-3.5 w-0.5 rounded-full bg-primary" />
        <span className="eq-bar h-3.5 w-0.5 rounded-full bg-primary [animation-delay:-0.28s]" />
        <span className="eq-bar h-3.5 w-0.5 rounded-full bg-wave [animation-delay:-0.14s]" />
        <span className="eq-bar h-3.5 w-0.5 rounded-full bg-primary [animation-delay:-0.42s]" />
      </span>
    </span>
  )
}

export function PodcastSearch({
  value,
  onChange,
  onSelect,
  debounceMs = DEBOUNCE_MS,
  minChars = MIN_CHARS,
}: {
  value: string
  onChange: (value: string) => void
  onSelect: (candidate: CandidateOut) => void
  debounceMs?: number
  minChars?: number
}) {
  const listId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [pasteHint, setPasteHint] = useState(false)
  const [highlight, setHighlight] = useState<number | null>(null)
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const candidates = result?.candidates ?? []

  useEffect(() => {
    const q = value.trim()
    if (q.length < minChars) {
      setResult(null)
      setLoading(false)
      setError(null)
      return
    }
    const ac = new AbortController()
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const next = await api.searchFeeds(q, ac.signal)
        if (cancelled) return
        setError(null)
        setResult(next)
        setOpen(true)
        setHighlight(null)
      } catch (err) {
        if (cancelled || ac.signal.aborted || isAbortError(err)) return
        setError("Couldn't search right now.")
        setResult(null)
        setOpen(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, debounceMs)
    return () => {
      cancelled = true
      ac.abort()
      window.clearTimeout(timer)
    }
  }, [value, debounceMs, minChars])

  function pick(candidate: CandidateOut) {
    onSelect(candidate)
    onChange(candidate.title)
    setOpen(false)
    setHighlight(null)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || (!candidates.length && !error && result?.candidates.length === 0)) {
      if (e.key === 'Escape') setOpen(false)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => (h == null ? 0 : Math.min(h + 1, candidates.length - 1)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => (h == null ? candidates.length - 1 : Math.max(h - 1, 0)))
    } else if (e.key === 'Enter') {
      if (highlight != null && candidates[highlight]) {
        e.preventDefault()
        pick(candidates[highlight])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
      setHighlight(null)
    }
  }

  const hasQuery = open && value.trim().length >= minChars
  const empty = hasQuery && !loading && !error && result != null && candidates.length === 0
  const showError = hasQuery && !!error && candidates.length === 0
  const showList = hasQuery && (loading || showError || empty || candidates.length > 0)

  return (
    <div className="relative space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={inputRef}
          role="combobox"
          aria-label="Podcast name or RSS URL"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-busy={loading}
          aria-activedescendant={
            highlight != null ? `${listId}-opt-${highlight}` : undefined
          }
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            setOpen(true)
          }}
          onKeyDown={onKeyDown}
          onFocus={() => {
            if (candidates.length || empty || error) setOpen(true)
          }}
          placeholder={pasteHint ? 'https://example.com/feed.xml' : 'Podcast name or RSS URL'}
          className="pl-9 pr-10"
        />
        {loading && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
            <SearchingIndicator labelled />
          </span>
        )}
      </div>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Matching podcasts"
          className="absolute z-20 max-h-80 w-full overflow-auto rounded-lg border border-border bg-popover p-1 shadow-soft"
        >
          {loading && candidates.length === 0 && (
            <li className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <SearchingIndicator />
              Searching shows…
            </li>
          )}
          {showError && (
            <li className="px-3 py-3 text-sm text-muted-foreground">
              {error}{' '}
              <button
                type="button"
                className="text-primary underline-offset-4 hover:underline"
                onClick={() => {
                  setPasteHint(true)
                  setOpen(false)
                  inputRef.current?.focus()
                }}
              >
                Paste an RSS URL instead.
              </button>
            </li>
          )}
          {empty && (
            <li className="px-3 py-3 text-sm text-muted-foreground">
              No public listing found.{' '}
              <button
                type="button"
                className="text-primary underline-offset-4 hover:underline"
                onClick={() => {
                  setPasteHint(true)
                  setOpen(false)
                  inputRef.current?.focus()
                  onChange('')
                }}
              >
                Paste an RSS URL instead.
              </button>
            </li>
          )}
          {candidates.map((c, i) => {
            const latest = latestLabel(c.newest_item)
            return (
              <li key={c.identity} role="none">
                <button
                  type="button"
                  id={`${listId}-opt-${i}`}
                  role="option"
                  aria-selected={highlight === i}
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => pick(c)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-2 py-2 text-left',
                    highlight === i ? 'bg-muted' : 'hover:bg-muted/60',
                  )}
                >
                  {c.artwork ? (
                    <img
                      src={c.artwork}
                      alt=""
                      width={40}
                      height={40}
                      className="size-10 shrink-0 rounded-md object-cover"
                    />
                  ) : (
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                      <Rss className="size-4" />
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{c.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[c.author, latest].filter(Boolean).join('  ·  ')}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      <p className="text-xs text-muted-foreground">
        Or{' '}
        <button
          type="button"
          className="text-primary underline-offset-4 hover:underline"
          onClick={() => {
            setPasteHint(true)
            inputRef.current?.focus()
          }}
        >
          paste an RSS URL instead
        </button>
        .
      </p>
    </div>
  )
}
