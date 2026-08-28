import { useState } from 'react'
import type { EpisodeOut } from '../api/types'
import { cn } from '../lib/utils'
import { Badge } from './ui/badge'
import { Checkbox } from './ui/checkbox'

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

  function toggleOpen(guid: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(guid)) next.delete(guid)
      else next.add(guid)
      return next
    })
  }

  return (
    <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
      {episodes.map((ep) => {
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
                onChange={() => onToggle(ep.guid)}
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
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {isOpen ? '▾' : '▸'} {hasNote ? 'note' : 'add note'}
                </button>
                {isOpen && (
                  <textarea
                    aria-label={`Note for ${ep.title}`}
                    value={prompts[ep.guid] ?? ''}
                    onChange={(e) => onPromptChange(ep.guid, e.target.value)}
                    placeholder="e.g. keep only the interview; cut 4:20 to 6:09"
                    rows={2}
                    maxLength={4000} // mirrors MAX_PROMPT_CHARS server-side cap
                    className={cn(
                      'mt-1 flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm transition-colors',
                      'placeholder:text-muted-foreground/70',
                      'focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
                    )}
                  />
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
