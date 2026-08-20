import { useState } from 'react'
import { useToken } from '../lib/useToken'

export function Settings() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  return (
    <div className="space-y-3 max-w-md">
      <h1 className="text-xl font-semibold">Settings</h1>
      <label className="block">
        API token
        <input
          className="border rounded px-2 py-1 w-full mt-1"
          aria-label="API token"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="leave blank if the API is open"
        />
      </label>
      <button
        className="bg-slate-900 text-white rounded px-3 py-1"
        onClick={() => setToken(value)}
      >
        Save
      </button>
    </div>
  )
}
