import { Check, KeyRound, Save } from 'lucide-react'
import { useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { useToken } from '../lib/useToken'

export function Settings() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  const [saved, setSaved] = useState(false)

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader title="Settings" description="Configure how the web client talks to the cutcast API." />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-[18px] text-primary" /> API token
          </CardTitle>
          <CardDescription>
            Sent as a Bearer token with every request. Leave blank if the API is open.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">API token</span>
            <Input
              aria-label="API token"
              type="password"
              value={value}
              onChange={(e) => {
                setValue(e.target.value)
                setSaved(false)
              }}
              placeholder="leave blank if the API is open"
            />
          </label>
          <div className="flex items-center gap-3">
            <Button
              onClick={() => {
                setToken(value)
                setSaved(true)
              }}
            >
              <Save /> Save
            </Button>
            {saved && (
              <span className="flex items-center gap-1.5 text-sm text-status-done">
                <Check className="size-4" /> Saved
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
