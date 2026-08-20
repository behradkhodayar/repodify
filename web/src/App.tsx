import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { JobDetail } from './routes/JobDetail'
import { Jobs } from './routes/Jobs'
import { NewDigest } from './routes/NewDigest'
import { Settings } from './routes/Settings'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <nav className="flex gap-4 p-4 border-b bg-slate-900 text-white">
          <Link to="/">New digest</Link>
          <Link to="/jobs">History</Link>
          <Link to="/settings" className="ml-auto">
            Settings
          </Link>
        </nav>
        <main className="max-w-3xl mx-auto p-4">
          <Routes>
            <Route path="/" element={<NewDigest />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
