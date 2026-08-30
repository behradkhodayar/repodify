import { Loader2, Pause, Play } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { Button } from './ui/button'

type Playing = { id: string; audio: HTMLAudioElement; url: string }

let current: Playing | null = null
const listeners = new Set<() => void>()

function stopCurrent() {
  if (!current) return
  current.audio.pause()
  URL.revokeObjectURL(current.url)
  current = null
  listeners.forEach((fn) => fn())
}

/** Test-only: stop any playing sample so suites don't leak Audio state. */
export function resetVoiceSampleForTests() {
  stopCurrent()
}

/**
 * Play/pause a catalog voice's short preview. Only one sample plays at a time;
 * starting another stops the current one. Fetches with the API token because
 * `<audio src>` would not send the Bearer header.
 */
export function PlaySample({ voiceId, name }: { voiceId: string; name: string }) {
  const [playing, setPlaying] = useState(current?.id === voiceId)
  const [loading, setLoading] = useState(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    const sync = () => setPlaying(current?.id === voiceId)
    listeners.add(sync)
    return () => {
      mounted.current = false
      listeners.delete(sync)
    }
  }, [voiceId])

  async function toggle() {
    if (current?.id === voiceId) {
      stopCurrent()
      return
    }
    stopCurrent()
    setLoading(true)
    let url: string | undefined
    try {
      const blob = await api.getVoiceSample(voiceId)
      if (!mounted.current) return
      url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => {
        if (current?.audio === audio) stopCurrent()
      }
      await audio.play()
      if (!mounted.current) {
        audio.pause()
        URL.revokeObjectURL(url)
        return
      }
      current = { id: voiceId, audio, url }
      setLoading(false)
      listeners.forEach((fn) => fn())
    } catch {
      if (url) URL.revokeObjectURL(url)
      stopCurrent()
      if (mounted.current) setLoading(false)
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={playing ? `Pause sample of ${name}` : `Play sample of ${name}`}
      onClick={(e) => {
        e.stopPropagation()
        void toggle()
      }}
    >
      {loading ? (
        <Loader2 className="animate-spin" />
      ) : playing ? (
        <Pause />
      ) : (
        <Play />
      )}
    </Button>
  )
}
