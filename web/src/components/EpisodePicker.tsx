import type { EpisodeOut } from '../api/types'

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
    <ul className="divide-y border rounded">
      {episodes.map((ep) => (
        <li key={ep.guid} className="p-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={ep.title}
              checked={selected.has(ep.guid)}
              onChange={() => onToggle(ep.guid)}
            />
            <span className="font-medium">{ep.title}</span>
            {ep.is_short_or_trailer && (
              <span className="text-xs bg-slate-200 rounded px-1">trailer</span>
            )}
          </label>
        </li>
      ))}
    </ul>
  )
}
