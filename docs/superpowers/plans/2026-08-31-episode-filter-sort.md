# Episode Picker Filter and Sort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a feed resolves on New digest, let the user filter the episode list by title and switch between newest-first and oldest-first display so they can find episodes in long catalogs.

**Architecture:** `EpisodePicker` owns local `query` and `sort` state and derives a visible list (filter on `title`, sort by `order_index`). `NewDigest` still owns `selected: Set<string>` and remounts the picker with `key={rss_url}` when the show changes. The feed API, job payload, and worker stay oldest-first / chronological.

**Tech Stack:** React 19 + TypeScript, existing `Input` / `Select` primitives, Vitest + Testing Library + userEvent. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-31-episode-filter-sort-design.md`. Copy strings below are verbatim from it.
- Client-side only. Do not change Python, API schemas, workers, or `parse_feed` order.
- Native form controls (`Input`, `Select`, `Checkbox`). Do not introduce a custom combobox or headless select.
- Search accessible name: `Filter episodes`. Placeholder: `Find an episode…` (Unicode ellipsis U+2026, not `...`).
- Sort accessible name: `Sort episodes`. Option labels: `Newest first` (value `newest`, default) and `Oldest first` (value `oldest`).
- Count with no query: `Showing N episodes`. Count with a trimmed query: `Showing K of N episodes`. Always the word `episodes`, even when N or K is 1.
- Empty filter copy: `No episodes match “{trimmed}”.` with curly quotes U+201C / U+201D around the trimmed query.
- Filter: `title.toLowerCase().includes(trimmed.toLowerCase())`. Do not match guid, date, duration, or trailer.
- Sort key is `order_index` only. Newest = descending. Oldest = ascending. Never sort by `published_at`. Never mutate the `episodes` prop.
- Selection is by guid in the parent. Hidden selected rows stay selected. Create digest still posts the full selected set.
- Web tests from `web/`: `npm test`. Typecheck: `npm run lint`. Do not start `./launch --real` or import GPU stacks.
- Commit messages: imperative mood, what + why, no emojis, no `feat:`/`fix:` prefixes, no Claude co-authoring. One commit per task.
- Branch: `feat/episode-filter-sort` (already created off `main`).

---

### Task 1: Newest-first default and oldest-first sort

**Files:**
- Modify: `web/src/components/EpisodePicker.tsx`
- Test: `web/src/components/EpisodePicker.test.tsx`

**Interfaces:**
- Consumes: existing `EpisodePicker` props (`episodes`, `selected`, `onToggle`, `prompts`, `onPromptChange`). `EpisodeOut.order_index` is already on the type.
- Produces: local `sort: 'newest' | 'oldest'` defaulting to `'newest'`; a native select named `Sort episodes`; list rows rendered from a sorted copy of `episodes`; count line `Showing N episodes`.

- [ ] **Step 1: Write the failing sort tests**

Keep the existing `EP`, `Harness`, `StatefulHarness`, and the two per-episode note tests. Append a factory, a stateful list harness, and a new describe block at the bottom of `web/src/components/EpisodePicker.test.tsx`:

```tsx
function ep(
  partial: Partial<EpisodeOut> & Pick<EpisodeOut, 'guid' | 'title' | 'order_index'>,
): EpisodeOut {
  return {
    published_at: null,
    duration_s: 60,
    is_short_or_trailer: false,
    ...partial,
  }
}

function ListHarness({
  episodes,
  initialSelected = new Set<string>(),
}: {
  episodes: EpisodeOut[]
  initialSelected?: Set<string>
}) {
  const [selected, setSelected] = useState(new Set(initialSelected))
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  return (
    <EpisodePicker
      episodes={episodes}
      selected={selected}
      onToggle={(guid) =>
        setSelected((prev) => {
          const next = new Set(prev)
          if (next.has(guid)) next.delete(guid)
          else next.add(guid)
          return next
        })
      }
      prompts={prompts}
      onPromptChange={(guid, value) => setPrompts((p) => ({ ...p, [guid]: value }))}
    />
  )
}

function checkboxNames(): string[] {
  return screen.getAllByRole('checkbox').map((el) => el.getAttribute('aria-label') ?? '')
}

const OLD = ep({ guid: 'old', title: 'Alpha Episode', order_index: 0 })
const NEW = ep({ guid: 'new', title: 'Beta Latest', order_index: 1 })

describe('EpisodePicker filter and sort', () => {
  it('lists newest first by default', () => {
    render(<ListHarness episodes={[OLD, NEW]} />)
    expect(checkboxNames()).toEqual(['Beta Latest', 'Alpha Episode'])
    expect(screen.getByLabelText(/sort episodes/i)).toHaveValue('newest')
    expect(screen.getByText('Showing 2 episodes')).toBeInTheDocument()
  })

  it('lists oldest first when that sort is chosen', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.selectOptions(screen.getByLabelText(/sort episodes/i), 'oldest')
    expect(checkboxNames()).toEqual(['Alpha Episode', 'Beta Latest'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npm test -- src/components/EpisodePicker.test.tsx`

Expected: FAIL. The default-order test sees `['Alpha Episode', 'Beta Latest']` (prop order) instead of newest-first, and `getByLabelText(/sort episodes/i)` is missing. Existing note tests still pass.

- [ ] **Step 3: Implement sort state, select, and derived order**

Replace `web/src/components/EpisodePicker.tsx` with this file. Keep the note-expand behavior byte-for-byte; only the wrapper, sort state, sorted copy, and count line are new. Map `visible`, not `episodes`.

```tsx
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { EpisodeOut } from '../api/types'
import { cn } from '../lib/utils'
import { Badge } from './ui/badge'
import { Checkbox } from './ui/checkbox'
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

  const visible = [...episodes].sort((a, b) =>
    sort === 'newest' ? b.order_index - a.order_index : a.order_index - b.order_index,
  )

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
        <Select
          aria-label="Sort episodes"
          value={sort}
          onChange={(e) => setSort(parseSort(e.target.value))}
          className="sm:ml-auto sm:w-44"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground">Showing {episodes.length} episodes</p>
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
    </div>
  )
}
```

Do not mutate `episodes` in place (`episodes.sort` is wrong). The `[...episodes].sort(...)` copy is required.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- src/components/EpisodePicker.test.tsx`

Expected: PASS (note tests + both new sort tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/EpisodePicker.tsx web/src/components/EpisodePicker.test.tsx
git commit -m "$(cat <<'EOF'
Sort the episode picker newest-first by default

Long catalogs buried recent episodes at the bottom. Display order now
follows order_index descending, with an oldest-first option, without
changing the feed API or job payload.
EOF
)"
```

---

### Task 2: Title filter, counts, and empty state

**Files:**
- Modify: `web/src/components/EpisodePicker.tsx`
- Test: `web/src/components/EpisodePicker.test.tsx`

**Interfaces:**
- Consumes: `sort: 'newest' | 'oldest'`, `parseSort`, `ListHarness`, `ep`, `checkboxNames`, `OLD`/`NEW` from Task 1.
- Produces: local `query: string` defaulting to `''`; native input named `Filter episodes`; visible rows = title substring filter then `order_index` sort; count `Showing K of N episodes` when `query.trim()` is non-empty; empty copy `No episodes match “{trimmed}”.`.

- [ ] **Step 1: Write the failing filter tests**

Append these three `it(...)` blocks inside the existing `describe('EpisodePicker filter and sort')` in `web/src/components/EpisodePicker.test.tsx` (after the oldest-first test):

```tsx
  it('filters titles case-insensitively', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), 'alpha')
    expect(checkboxNames()).toEqual(['Alpha Episode'])
    expect(screen.getByText('Showing 1 of 2 episodes')).toBeInTheDocument()
  })

  it('treats a whitespace-only query as no filter', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), '   ')
    expect(checkboxNames()).toEqual(['Beta Latest', 'Alpha Episode'])
    expect(screen.getByText('Showing 2 episodes')).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.type(screen.getByLabelText(/filter episodes/i), 'zzzz')
    expect(screen.getByText('No episodes match “zzzz”.')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByText('Showing 0 of 2 episodes')).toBeInTheDocument()
  })
```

The empty-state string uses curly quotes: `“` (U+201C) and `”` (U+201D). Do not type straight `"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npm test -- src/components/EpisodePicker.test.tsx`

Expected: FAIL with `Unable to find a label with the text of: /filter episodes/i`. Sort tests still pass.

- [ ] **Step 3: Implement query state, filter, count variants, and empty state**

In `web/src/components/EpisodePicker.tsx`:

1. Import `Input`:

```tsx
import { Input } from './ui/input'
```

2. Add `query` state next to `sort`, and derive `trimmed` / `visible` / `countLabel` (replace the Task 1 `visible` and hard-coded count):

```tsx
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
```

Use `item` (not `ep`) in the filter callback so it does not shadow the `visible.map((ep) => ...)` parameter.

3. Replace the toolbar + count + list wrapper (everything currently returned inside the outer `<div className="space-y-2">` except the map body of each row, which stays as in Task 1) with:

```tsx
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
            /* existing row body from Task 1 — do not change note/checkbox markup */
          })}
        </ul>
      )}
    </div>
  )
```

Placeholder must be `Find an episode…` with Unicode ellipsis (U+2026). Empty-state quotes must be U+201C / U+201D. Drop `sm:ml-auto` on the select now that the input takes `sm:flex-1`. The `max-h-80 overflow-y-auto` class stays on the `<ul>` only — the toolbar and count do not scroll with the rows.

The completed file after this step:

```tsx
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npm test -- src/components/EpisodePicker.test.tsx`

Expected: PASS (notes + sort + three filter tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/EpisodePicker.tsx web/src/components/EpisodePicker.test.tsx
git commit -m "$(cat <<'EOF'
Filter the episode picker by title

A client-side case-insensitive substring match lets users find one
episode in a long catalog without a new feed API. Whitespace-only
queries show the full list; no matches render an empty state.
EOF
)"
```

---

### Task 3: Selection survives a hiding query; remount on show change

**Files:**
- Modify: `web/src/components/EpisodePicker.test.tsx`
- Modify: `web/src/routes/NewDigest.tsx` (the `EpisodePicker` JSX, currently around line 129)
- Test: `web/src/components/EpisodePicker.test.tsx`, `web/src/routes/NewDigest.test.tsx` (run only — no new assertions)

**Interfaces:**
- Consumes: `ListHarness`, `OLD`/`NEW`, `query` input from Task 2. Parent still owns `selected: Set<string>` and `onToggle(guid: string)`.
- Produces: no new props. `NewDigest` passes `key={resolve.data.rss_url}` so query/sort/`open` reset when the resolved show changes.

- [ ] **Step 1: Write the failing selection-persistence test**

Append this `it(...)` inside `describe('EpisodePicker filter and sort')` in `web/src/components/EpisodePicker.test.tsx`:

```tsx
  it('keeps a selection after the query hides then reveals the episode', async () => {
    const user = userEvent.setup()
    render(<ListHarness episodes={[OLD, NEW]} />)
    await user.click(screen.getByRole('checkbox', { name: 'Alpha Episode' }))
    expect(screen.getByRole('checkbox', { name: 'Alpha Episode' })).toBeChecked()

    await user.type(screen.getByLabelText(/filter episodes/i), 'beta')
    expect(screen.queryByRole('checkbox', { name: 'Alpha Episode' })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Beta Latest' })).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/filter episodes/i))
    expect(screen.getByRole('checkbox', { name: 'Alpha Episode' })).toBeChecked()
  })
```

Do not assert on a parent selected-count. The checkbox after clearing the query is the proof.

This test is expected to **pass on the first run** if Task 2 kept `selected` in the parent (the spec’s intended design). If it fails, the picker is deriving selection from the visible list — fix that in Step 3 by toggling via `onToggle(guid)` and reading `selected.has(ep.guid)` only.

- [ ] **Step 2: Run the new test**

Run: `cd web && npm test -- src/components/EpisodePicker.test.tsx`

Expected: PASS for the new test if Task 2’s selection wiring is unchanged. If FAIL, continue to Step 3 and restore parent-owned `selected` as in the Task 2 completed file (`checked={selected.has(ep.guid)}` and `onChange={() => handleToggle(ep.guid)}`).

- [ ] **Step 3: Remount the picker when the show changes**

In `web/src/routes/NewDigest.tsx`, add `key={resolve.data.rss_url}` on `EpisodePicker`. The block becomes:

```tsx
            <EpisodePicker
              key={resolve.data.rss_url}
              episodes={resolve.data.episodes}
              selected={selected}
              onToggle={toggle}
              prompts={episodePrompts}
              onPromptChange={(guid, value) =>
                setEpisodePrompts((prev) => ({ ...prev, [guid]: value }))
              }
            />
```

`onSelectShow` already clears `selected` and `episodePrompts` before resolving. The key clears the picker’s `query`, `sort`, and `open` when `rss_url` changes. Do not add NewDigest assertions; the spec leaves that page’s tests as “remain green”.

- [ ] **Step 4: Run picker tests, New digest tests, and the web suite**

```bash
cd web && npm test -- src/components/EpisodePicker.test.tsx src/routes/NewDigest.test.tsx
cd web && npm test
cd web && npm run lint
```

Expected: all PASS. `tsc -b` exits 0.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/EpisodePicker.test.tsx web/src/routes/NewDigest.tsx
git commit -m "$(cat <<'EOF'
Keep episode selection while filtering and reset the picker per show

A checked episode stays checked if the title query hides it. Remounting
EpisodePicker on rss_url clears search and sort when the user picks a
different podcast.
EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Toolbar inside `EpisodePicker`, above the list, not inside `overflow-y-auto` | 1 (sort/count), 2 (search) |
| Default newest first (`order_index` descending) | 1 |
| Oldest first option | 1 |
| Title-only case-insensitive substring | 2 |
| Trim / whitespace-only = no filter | 2 |
| `Showing N episodes` / `Showing K of N episodes` | 1 / 2 |
| Empty state with curly quotes | 2 |
| Do not mutate `episodes` | 1, 2 |
| Selection by guid survives hiding query | 3 |
| `key={rss_url}` remount | 3 |
| Tests 1–5 in spec §8 | 1 (1–2), 2 (3, 5 + whitespace), 3 (4) |
| No API / worker / Python changes | Global constraint |
| NewDigest tests remain green | 3 |

No placeholders. Sort type is `'newest' | 'oldest'` in every task. Helper `parseSort` is defined in Task 1 and reused in Task 2’s completed file.
