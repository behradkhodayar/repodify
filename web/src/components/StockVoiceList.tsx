import type { StockVoiceOut } from '../api/types'
import { stockVoiceLabel } from '../lib/format'
import { PlaySample } from './PlaySample'
import { Badge } from './ui/badge'
import { Checkbox } from './ui/checkbox'

/**
 * Catalog of stock voices: a playable sample, the given name, and an explicit
 * gender tag. Used on Settings to pick the preferred pool gender-matching
 * assigns from.
 */
export function StockVoiceList({
  voices,
  preferredIds,
  onPreferredChange,
}: {
  voices: StockVoiceOut[]
  preferredIds: string[]
  onPreferredChange: (ids: string[]) => void
}) {
  const preferred = new Set(preferredIds)

  function toggle(id: string, checked: boolean) {
    if (checked) {
      if (preferred.has(id)) return
      onPreferredChange([...preferredIds, id])
    } else {
      onPreferredChange(preferredIds.filter((v) => v !== id))
    }
  }

  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {voices.map((v) => {
        const label = stockVoiceLabel(v.name, v.gender)
        return (
          <li key={v.id} className="flex items-center gap-2 px-2 py-1.5">
            <PlaySample voiceId={v.id} name={v.name} />
            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
              <Checkbox
                aria-label={`Prefer ${label}`}
                checked={preferred.has(v.id)}
                onChange={(e) => toggle(v.id, e.target.checked)}
              />
              <span className="min-w-0 flex-1 truncate text-sm">{v.name}</span>
              {v.gender && (
                <Badge variant="secondary" className="shrink-0 capitalize">
                  {v.gender}
                </Badge>
              )}
            </label>
          </li>
        )
      })}
    </ul>
  )
}
