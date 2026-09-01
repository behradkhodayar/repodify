import { AlertCircle, Loader2, Rss, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useCreateJob, useResolveFeed } from '../api/queries'
import type { CandidateOut } from '../api/types'
import { EpisodePicker } from '../components/EpisodePicker'
import { PageHeader } from '../components/PageHeader'
import { PodcastSearch } from '../components/PodcastSearch'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Separator } from '../components/ui/separator'
import { Textarea } from '../components/ui/textarea'

function resolveErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown }
      if (typeof parsed.detail === 'string') return parsed.detail
    } catch {
      /* body was not JSON */
    }
    if (/private feed/i.test(err.message)) return 'Private feed unsupported.'
  }
  return "Couldn't reach that feed. Check the URL and try again."
}

export function NewDigest() {
  const [query, setQuery] = useState('')
  const [rssUrl, setRssUrl] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [customPrompt, setCustomPrompt] = useState('')
  const [episodePrompts, setEpisodePrompts] = useState<Record<string, string>>({})
  const resolve = useResolveFeed()
  const create = useCreateJob()
  const navigate = useNavigate()

  function toggle(guid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(guid)) next.delete(guid)
      else next.add(guid)
      return next
    })
  }

  function onSelectShow(candidate: CandidateOut) {
    setSelected(new Set())
    setEpisodePrompts({})
    setRssUrl(candidate.feed_url)
    resolve.mutate(candidate.feed_url, {
      onSuccess: (data) => setRssUrl(data.rss_url),
    })
  }

  async function onCreate() {
    const feed_url = resolve.data?.rss_url || rssUrl
    const episode_prompts: Record<string, string> = {}
    for (const guid of selected) {
      const note = episodePrompts[guid]?.trim()
      if (note) episode_prompts[guid] = note
    }
    const { job_id } = await create.mutateAsync({
      feed_url,
      episode_ids: [...selected],
      custom_prompt: customPrompt.trim() || undefined,
      episode_prompts,
    })
    navigate(`/jobs/${job_id}`)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="New digest"
        description="Search for a show, choose the episodes, and generate a short digest."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Rss className="size-[18px] text-primary" /> Source show
          </CardTitle>
          <CardDescription>
            Type a podcast name. Pasting an RSS or Apple Podcasts URL still works.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <PodcastSearch value={query} onChange={setQuery} onSelect={onSelectShow} />
          {resolve.isPending && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Loading episodes…
            </p>
          )}
          {resolve.isError && (
            <p className="flex items-center gap-1.5 text-sm text-status-failed">
              <AlertCircle className="size-4" /> {resolveErrorMessage(resolve.error)}
            </p>
          )}
          {resolve.data && (
            <p className="text-sm text-muted-foreground">
              Loaded <span className="font-medium text-foreground">{resolve.data.feed_title}</span> ·{' '}
              {resolve.data.episodes.length} episode
              {resolve.data.episodes.length === 1 ? '' : 's'}
              {resolve.data.cached ? ' · cached' : ''}.
            </p>
          )}
        </CardContent>
      </Card>

      {resolve.data && (
        <Card>
          <CardHeader>
            <CardTitle>Choose episodes</CardTitle>
            <CardDescription>
              Select the episodes to include. Length, voices, and local vs hosted
              backends are chosen after download, at each pipeline step.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
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

            <Separator />

            <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
              <label className="w-full space-y-1.5">
                <span className="block text-sm font-medium">Custom instructions</span>
                <Textarea
                  aria-label="Custom instructions"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  placeholder="Steer the whole digest — e.g. focus on the funding news; skip sponsor reads. You can reference times like 4:20."
                  rows={3}
                  maxLength={4000} // mirrors MAX_PROMPT_CHARS server-side cap
                />
                <span className="block text-xs text-muted-foreground">
                  Optional. Leave blank to use the default summary.
                </span>
              </label>

              <div className="flex items-center gap-3 sm:ml-auto">
                <span className="text-sm text-muted-foreground">
                  {selected.size} selected
                </span>
                <Button
                  variant="wave"
                  size="lg"
                  disabled={selected.size === 0 || create.isPending}
                  onClick={onCreate}
                >
                  {create.isPending ? (
                    <>
                      <Loader2 className="animate-spin" /> Creating
                    </>
                  ) : (
                    <>
                      <Sparkles /> Create digest
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {create.data && (
        <p className="text-sm text-muted-foreground">Created job {create.data.job_id}…</p>
      )}
    </div>
  )
}
