import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Shield, Wrench, FlaskConical,
  CheckSquare, ScrollText, Settings, ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/conflicts', icon: Shield,          label: 'Conflicts' },
  { to: '/tools',     icon: Wrench,          label: 'Tools' },
  { to: '/analysis',  icon: FlaskConical,    label: 'Analysis Runs' },
  { to: '/approvals', icon: CheckSquare,     label: 'Approvals' },
  { to: '/audit',     icon: ScrollText,      label: 'Audit Log' },
  { to: '/settings',  icon: Settings,        label: 'Settings' },
]

export function Sidebar() {
  return (
    <aside className="w-60 min-h-screen bg-gray-900 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-white font-semibold text-sm leading-tight">MTGS</p>
            <p className="text-gray-400 text-xs">Tool Governance</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors group',
                isActive
                  ? 'bg-brand-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span className="flex-1">{label}</span>
                {isActive && <ChevronRight className="w-3 h-3 opacity-60" />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-gray-800">
        <p className="text-gray-500 text-xs">v0.1.0 · Phase 4B</p>
      </div>
    </aside>
  )
}
