import type { StageOut } from '../api/types'

const ICON: Record<string, string> = {
  done: '✓',
  running: '…',
  failed: '✗',
  skipped: '–',
  pending: '·',
}

export function StageProgress({ stages }: { stages: StageOut[] }) {
  return (
    <ul className="space-y-1">
      {stages.map((s, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span className="w-4">{ICON[s.state] ?? '·'}</span>
          <span className="font-medium">{s.stage}</span>
          {s.detail && <span className="text-slate-500">— {s.detail}</span>}
        </li>
      ))}
    </ul>
  )
}
