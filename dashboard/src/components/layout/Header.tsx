import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '@/api/endpoints'
import { Bell, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

interface HeaderProps {
  title: string
  subtitle?: string
}

export function Header({ title, subtitle }: HeaderProps) {
  const { data: health, isFetching } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  })

  const statusColor = {
    healthy: 'bg-green-400',
    degraded: 'bg-yellow-400',
    unhealthy: 'bg-red-400',
  }[health?.status ?? 'healthy']

  return (
    <header className="h-14 px-6 border-b border-gray-200 bg-white flex items-center justify-between flex-shrink-0">
      <div>
        <h1 className="text-gray-900 font-semibold text-base">{title}</h1>
        {subtitle && <p className="text-gray-500 text-xs">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-3">
        {/* API status indicator */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className={cn('w-2 h-2 rounded-full', statusColor)} />
          <span className="capitalize">{health?.status ?? 'connecting…'}</span>
          {isFetching && <RefreshCw className="w-3 h-3 animate-spin text-gray-400" />}
        </div>

        <button className="relative p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
          <Bell className="w-4 h-4" />
        </button>

        {/* Avatar placeholder */}
        <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center">
          <span className="text-white text-xs font-semibold">D</span>
        </div>
      </div>
    </header>
  )
}
