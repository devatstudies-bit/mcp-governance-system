import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const PAGE_META: Record<string, { title: string; subtitle?: string }> = {
  '/':          { title: 'Dashboard', subtitle: 'Governance health overview' },
  '/conflicts': { title: 'Conflicts', subtitle: 'Detected tool routing conflicts' },
  '/tools':     { title: 'Tools Registry', subtitle: 'Registered MCP tools by environment' },
  '/analysis':  { title: 'Analysis Runs', subtitle: 'Conflict detection and simulation history' },
  '/approvals': { title: 'Approvals', subtitle: 'Pending sign-offs for CRITICAL / HIGH conflicts' },
  '/audit':     { title: 'Audit Log', subtitle: 'Immutable governance action trail' },
  '/settings':  { title: 'Settings', subtitle: 'Circuit breakers, MCP sync, environment config' },
}

export function AppLayout() {
  const { pathname } = useLocation()
  const meta = PAGE_META[pathname] ?? { title: 'MTGS' }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title={meta.title} subtitle={meta.subtitle} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
