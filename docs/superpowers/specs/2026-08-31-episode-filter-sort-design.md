# Episode picker filter and sort

Date: 2026-08-31
Status: approved

## 1. Goal

After a podcast feed is resolved on New digest, the episode list is often
hundreds of rows, shown oldest-first with no search. Finding a specific episode
is slow.

Add a **client-side title filter** and a **newest/oldest sort** to the episode
picker so the user can locate episodes before selecting them. The digest
pipeline and job payload are unchanged: selected episode ids are still submitted
as today, and the worker still processes them in chronological `order_index`
order.

## 2. Non-goals

- Server-side search, pagination, or a new feed API field.
- Virtualized rendering of the list.
- Matching on guid, date, duration, or trailer flag.
- “Select all matching” / “select all visible”.
- Persisting sort or query in `localStorage`.
- Changing default feed parse order (`parse_feed` stays oldest-first).

## 3. Decisions (settled during brainstorming)

| Question | Decision |
|---|---|
| Where the controls live | Inside `EpisodePicker`, above the scrollable list |
| Default sort | Newest first (`order_index` descending) |
| Filter field | Episode `title` only, case-insensitive substring |
| Selection vs filter | Selection is by guid; hidden selected rows stay selected |
| Sort persistence | None; remounting on a new show resets to newest first |
| Backend | Untouched |

## 4. Placement

The controls sit in the existing “Choose episodes & format” card, **below** the
title and description (“Select the episodes to include, then tune the digest.”)
and **above** the episode list. They do **not** scroll with the list (`max-h-80`
overflow stays on the `<ul>` only).

```
Choose episodes & format
Select the episodes to include, then tune the digest.

[ Find an episode…                    ]  [ Newest first ▾ ]
Showing 487 episodes

  ☐  Latest episode title          Jan 12 · 48 min
  ☐  …
```

On a narrow viewport the sort control stacks under the search field. Target
length, hosts, custom instructions, selected count, and Create digest stay
below the list, unchanged.

## 5. UI copy and accessibility

| Control | Details |
|---|---|
| Search input | Placeholder `Find an episode…`. Accessible name `Filter episodes`. Existing `Input` primitive. |
| Sort select | Native `Select` with options `Newest first` (default) and `Oldest first`. Accessible name `Sort episodes`. |
| Count (no query) | `Showing N episodes` (`N` = full list length). |
| Count (active query) | `Showing K of N episodes` (`K` = visible matches, `N` = full list length). |
| Empty filter | Inside the list area: `No episodes match “{query}”.` (the trimmed query, wrapped in curly quotes). |

## 6. Behavior

### Filter

- Match `episode.title` with a case-insensitive substring
  (`title.toLowerCase().includes(query.toLowerCase())`).
- Trim the query. Whitespace-only is treated as empty (show all).
- Do not search guid, `published_at`, duration, or the trailer badge.

### Sort

- Canonical order is the feed’s `order_index` (oldest = 0), already assigned by
  `parse_feed`.
- **Newest first:** descending `order_index`.
- **Oldest first:** ascending `order_index` (today’s API order).
- Do not re-sort by `published_at`. Null dates already have a stable index.

### Selection

- `selected: Set<string>` remains owned by `NewDigest`. Toggling a visible row
  still calls `onToggle(guid)`.
- A guid that is selected and then filtered out of view stays in `selected`.
- The existing “N selected” label under the list counts the full set, including
  hidden rows.
- Create digest still posts `episode_ids: [...selected]` — the visible subset
  is irrelevant.

### Reset

- `NewDigest` remounts the picker when the resolved show changes:
  `<EpisodePicker key={resolve.data.rss_url} …>`.
- On remount, query is empty and sort is newest first.
- Open per-episode notes (`open` set inside the picker) reset with the remount.

### Local state

`EpisodePicker` owns:

```ts
query: string                    // default ''
sort: 'newest' | 'oldest'        // default 'newest'
open: Set<string>                // existing note-expand state
```

Visible rows are derived (not stored):

```
trimmed = query.trim()
filtered = trimmed === ''
  ? episodes
  : episodes.filter(ep => ep.title.toLowerCase().includes(trimmed.toLowerCase()))
visible = sort === 'newest'
  ? [...filtered].sort((a, b) => b.order_index - a.order_index)
  : [...filtered].sort((a, b) => a.order_index - b.order_index)
```

The incoming `episodes` array is never mutated.

## 7. Files

| Path | Change |
|---|---|
| `web/src/components/EpisodePicker.tsx` | Toolbar, derive `visible`, empty state, count line. |
| `web/src/components/EpisodePicker.test.tsx` | Filter/sort/selection cases below. |
| `web/src/routes/NewDigest.tsx` | `key={resolve.data.rss_url}` on `EpisodePicker`. |

No API, schema, worker, or Python test changes.

## 8. Tests

Keep the existing per-episode note tests. Add:

1. **Default order is newest first.** Fixture with `order_index` 0 then 1; the
   first checkbox/title in the list is the `order_index` 1 episode.
2. **Oldest first restores chronological order.** Choose `Oldest first`; the
   `order_index` 0 title is first.
3. **Title filter is case-insensitive.** Typing `alpha` hides a title that
   does not contain that substring and keeps `Alpha Episode`.
4. **Selection survives a hiding query.** Check episode A, type a query that
   hides A (A’s checkbox is gone), then clear the query; A’s checkbox is still
   checked. Do not use a parent-harness selected-count assertion — the visible
   checkbox after clearing is the proof.
5. **Empty state.** A query with no title matches renders
   `No episodes match “…”` and no episode checkboxes.

`NewDigest.test.tsx` keeps creating a job; it does not need new assertions
beyond remaining green (the picker default-sorts a single episode the same
either way).

## 9. Error handling

No new network path. A failed `POST /feeds/resolve` is still the existing
banner above this card. The only new empty state is the no-match line in §5.
