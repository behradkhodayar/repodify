import { AlertCircle, Loader2, Rss, Search, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateJob, useResolveFeed } from '../api/queries'
import { EpisodePicker } from '../components/EpisodePicker'
import { PageHeader } from '../components/PageHeader'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Checkbox } from '../components/ui/checkbox'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { Separator } from '../components/ui/separator'
import { Textarea } from '../components/ui/textarea'

export function NewDigest() {
  const [url, setUrl] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [targetMinutes, setTargetMinutes] = useState(30)
  const [hostCount, setHostCount] = useState(1)
  const [reviewVoices, setReviewVoices] = useState(false)
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

  async function onCreate() {
    const episode_prompts: Record<string, string> = {}
    for (const guid of selected) {
      const note = episodePrompts[guid]?.trim()
      if (note) episode_prompts[guid] = note
    }
    const { job_id } = await create.mutateAsync({
      feed_url: url,
      episode_ids: [...selected],
      host_count: hostCount,
      target_minutes: targetMinutes,
      review_voices: reviewVoices,
      custom_prompt: customPrompt.trim() || undefined,
      episode_prompts,
    })
    navigate(`/jobs/${job_id}`)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="New digest"
        description="Point repodify at a podcast feed, choose the episodes, and generate a short digest."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Rss className="size-[18px] text-primary" /> Source feed
          </CardTitle>
          <CardDescription>Paste an RSS feed URL to load its episodes.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              aria-label="Feed URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/feed.xml"
              className="sm:flex-1"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && url) resolve.mutate(url)
              }}
            />
            <Button onClick={() => resolve.mutate(url)} disabled={!url || resolve.isPending}>
              {resolve.isPending ? (
                <>
                  <Loader2 className="animate-spin" /> Resolving
                </>
              ) : (
                <>
                  <Search /> Resolve
                </>
              )}
            </Button>
          </div>
          {resolve.isError && (
            <p className="flex items-center gap-1.5 text-sm text-status-failed">
              <AlertCircle className="size-4" /> Couldn&apos;t reach that feed. Check the URL and try
              again.
            </p>
          )}
          {resolve.data && (
            <p className="text-sm text-muted-foreground">
              Loaded <span className="font-medium text-foreground">{resolve.data.feed_title}</span> ·{' '}
              {resolve.data.episodes.length} episode
              {resolve.data.episodes.length === 1 ? '' : 's'}.
            </p>
          )}
        </CardContent>
      </Card>

      {resolve.data && (
        <Card>
          <CardHeader>
            <CardTitle>Choose episodes &amp; format</CardTitle>
            <CardDescription>
              Select the episodes to include, then tune the digest.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <EpisodePicker
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
              <label className="space-y-1.5">
                <span className="block text-sm font-medium">Target length</span>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    value={targetMinutes}
                    onChange={(e) => setTargetMinutes(Number(e.target.value))}
                    className="w-24"
                  />
                  <span className="text-sm text-muted-foreground">min</span>
                </div>
              </label>

              <label className="space-y-1.5">
                <span className="block text-sm font-medium">Hosts</span>
                <Select
                  value={hostCount}
                  onChange={(e) => setHostCount(Number(e.target.value))}
                  className="w-44"
                >
                  <option value={1}>1 · narrator</option>
                  <option value={2}>2 · dialogue</option>
                </Select>
              </label>

              <label className="flex items-center gap-2 sm:pb-2.5">
                <Checkbox
                  checked={reviewVoices}
                  onChange={(e) => setReviewVoices(e.target.checked)}
                />
                <span className="text-sm font-medium">Assign voices per speaker</span>
              </label>

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
