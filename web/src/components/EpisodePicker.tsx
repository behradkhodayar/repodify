import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { EpisodeOut } from '../api/types'
import { cn } from '../lib/utils'
import { Badge } from './ui/badge'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { Select } from './ui/select'
import { Textarea } from './ui/textarea'

function formatDuration(seconds: number | null): string | null {
  if (!seconds) return null
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString()
}

function parseSort(value: string): 'newest' | 'oldest' {
  return value === 'oldest' ? 'oldest' : 'newest'
}

export function EpisodePicker({
  episodes,
  selected,
  onToggle,
  prompts,
  onPromptChange,
}: {
  episodes: EpisodeOut[]
  selected: Set<string>
  onToggle: (guid: string) => void
  prompts: Record<string, string>
  onPromptChange: (guid: string, value: string) => void
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest')
  const [query, setQuery] = useState('')

  const trimmed = query.trim()
  const filtered =
    trimmed === ''
      ? episodes
      : episodes.filter((item) => item.title.toLowerCase().includes(trimmed.toLowerCase()))
  const visible = [...filtered].sort((a, b) =>
    sort === 'newest' ? b.order_index - a.order_index : a.order_index - b.order_index,
  )
  const countLabel =
    trimmed === ''
      ? `Showing ${episodes.length} episodes`
      : `Showing ${visible.length} of ${episodes.length} episodes`

  function toggleOpen(guid: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(guid)) next.delete(guid)
      else next.add(guid)
      return next
    })
  }

  function handleToggle(guid: string) {
    // Deselecting an episode hides its note controls; forget its expanded state
    // too, so re-selecting it starts collapsed rather than reopening the note.
    if (selected.has(guid)) {
      setOpen((prev) => {
        if (!prev.has(guid)) return prev
        const next = new Set(prev)
        next.delete(guid)
        return next
      })
    }
    onToggle(guid)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          aria-label="Filter episodes"
          placeholder="Find an episode…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="sm:flex-1"
        />
        <Select
          aria-label="Sort episodes"
          value={sort}
          onChange={(e) => setSort(parseSort(e.target.value))}
          className="sm:w-44"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground">{countLabel}</p>
      {visible.length === 0 ? (
        <p className="px-1 py-6 text-sm text-muted-foreground">
          No episodes match “{trimmed}”.
        </p>
      ) : (
        <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
          {visible.map((ep) => {
            const isSelected = selected.has(ep.guid)
            const isOpen = open.has(ep.guid)
            const hasNote = Boolean(prompts[ep.guid]?.trim())
            const meta = [formatDate(ep.published_at), formatDuration(ep.duration_s)].filter(Boolean)
            return (
              <li key={ep.guid}>
                <label
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition-colors',
                    isSelected
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border hover:bg-muted/50',
                  )}
                >
                  <Checkbox
                    aria-label={ep.title}
                    checked={isSelected}
                    onChange={() => handleToggle(ep.guid)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{ep.title}</span>
                    {meta.length > 0 && (
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {meta.join(' · ')}
                      </span>
                    )}
                  </span>
                  {ep.is_short_or_trailer && <Badge variant="secondary">trailer</Badge>}
                </label>

                {isSelected && (
                  <div className="mt-1 pl-8">
                    <button
                      type="button"
                      onClick={() => toggleOpen(ep.guid)}
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      {isOpen ? (
                        <ChevronDown className="size-3" />
                      ) : (
                        <ChevronRight className="size-3" />
                      )}
                      {hasNote ? 'note' : 'add note'}
                    </button>
                    {isOpen && (
                      <Textarea
                        aria-label={`Note for ${ep.title}`}
                        value={prompts[ep.guid] ?? ''}
                        onChange={(e) => onPromptChange(ep.guid, e.target.value)}
                        placeholder="e.g. keep only the interview; cut 4:20 to 6:09"
                        rows={2}
                        maxLength={4000} // mirrors MAX_PROMPT_CHARS server-side cap
                        className="mt-1"
                      />
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
