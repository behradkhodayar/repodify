import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { TooltipProvider } from './components/ui/tooltip'
import { ThemeProvider } from './lib/theme'
import { JobDetail } from './routes/JobDetail'
import { Jobs } from './routes/Jobs'
import { NewDigest } from './routes/NewDigest'
import { Overview } from './routes/Overview'
import { Settings } from './routes/Settings'

const queryClient = new QueryClient()

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter basename="/app">
            <Routes>
              <Route element={<AppShell />}>
                <Route path="/" element={<Overview />} />
                <Route path="/new" element={<NewDigest />} />
                <Route path="/jobs" element={<Jobs />} />
                <Route path="/jobs/:id" element={<JobDetail />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
