import { useQuery } from '@tanstack/react-query'
import { fetchReadiness } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { CircuitStateBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { Settings, Zap, RefreshCw } from 'lucide-react'

export function SettingsPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['readiness'],
    queryFn: fetchReadiness,
    refetchInterval: 15_000,
  })

  return (
    <div className="space-y-5 max-w-3xl">
      {/* Circuit Breakers */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-brand-500" />
            <p className="text-sm font-semibold text-gray-700">Circuit Breakers</p>
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {isLoading ? (
          <Spinner />
        ) : (
          <div className="space-y-3">
            {Object.entries(data?.circuitBreakers ?? {}).map(([name, cb]) => (
              <div
                key={name}
                className="flex items-center gap-4 px-4 py-3 rounded-lg bg-gray-50 border border-gray-100"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-700 font-mono">{name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {cb.totalCalls} calls · {cb.successful} ok · {cb.failed} failed · {cb.rejected} rejected
                  </p>
                </div>
                <CircuitStateBadge state={cb.state} />
                <div className="text-right text-xs text-gray-400">
                  <p>{cb.stateChanges} transitions</p>
                  <p className="text-gray-300">
                    {cb.failed > 0 ? `${((cb.failed / cb.totalCalls) * 100).toFixed(1)}% err rate` : 'no errors'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 text-xs text-gray-400">
          Circuit breakers protect Azure OpenAI, Azure AI Search, MCP server sync, and notification channels.
          An OPEN breaker means the service is unavailable — requests fail-fast until recovery timeout.
        </p>
      </Card>

      {/* API Config */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Settings className="w-4 h-4 text-brand-500" />
          <p className="text-sm font-semibold text-gray-700">Dashboard Configuration</p>
        </div>
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">API Base URL</span>
            <span className="font-mono text-xs text-gray-700">
              {import.meta.env.VITE_API_URL || 'http://localhost:8000 (proxied)'}
            </span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">Default Environment ID</span>
            <span className="font-mono text-xs text-gray-700">
              {import.meta.env.VITE_DEFAULT_ENV_ID || '00000000-0000-0000-0000-000000000001'}
            </span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">System Status</span>
            <span className="font-mono text-xs text-gray-700 capitalize">
              {data?.status ?? 'checking…'}
            </span>
          </div>
        </div>
        <p className="mt-3 text-xs text-gray-400">
          Set <code className="bg-gray-100 px-1 rounded">VITE_API_URL</code> and{' '}
          <code className="bg-gray-100 px-1 rounded">VITE_DEFAULT_ENV_ID</code>{' '}
          in <code className="bg-gray-100 px-1 rounded">dashboard/.env.local</code> to customise.
        </p>
      </Card>
    </div>
  )
}
