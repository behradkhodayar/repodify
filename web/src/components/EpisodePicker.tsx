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
}: {
  episodes: EpisodeOut[]
  selected: Set<string>
  onToggle: (guid: string) => void
}) {
  return (
    <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
      {episodes.map((ep) => {
        const isSelected = selected.has(ep.guid)
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
          </li>
        )
      })}
    </ul>
  )
}
