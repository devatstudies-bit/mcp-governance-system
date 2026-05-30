import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { AppLayout } from '@/components/layout/AppLayout'
import { DashboardPage }  from '@/pages/DashboardPage'
import { ConflictsPage }  from '@/pages/ConflictsPage'
import { ToolsPage }      from '@/pages/ToolsPage'
import { AnalysisPage }   from '@/pages/AnalysisPage'
import { ApprovalsPage }  from '@/pages/ApprovalsPage'
import { AuditPage }      from '@/pages/AuditPage'
import { SettingsPage }   from '@/pages/SettingsPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index           element={<DashboardPage />}  />
            <Route path="conflicts" element={<ConflictsPage />}  />
            <Route path="tools"     element={<ToolsPage />}      />
            <Route path="analysis"  element={<AnalysisPage />}   />
            <Route path="approvals" element={<ApprovalsPage />}  />
            <Route path="audit"     element={<AuditPage />}      />
            <Route path="settings"  element={<SettingsPage />}   />
          </Route>
        </Routes>
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </StrictMode>,
)
