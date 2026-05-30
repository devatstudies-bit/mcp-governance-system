import { useQuery } from '@tanstack/react-query'
import {
  fetchEnvironmentHealth, fetchConflicts,
  fetchAnalysisStats, fetchPendingApprovals,
} from '@/api/endpoints'
import { StatCard, Card } from '@/components/ui/Card'
import { HealthGauge } from '@/components/charts/HealthGauge'
import { ConflictTrendChart } from '@/components/charts/ConflictTrendChart'
import { ConflictMapD3 } from '@/components/charts/ConflictMapD3'
import { SeverityBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { formatRelative } from '@/lib/utils'
import {
  Shield, Wrench, FlaskConical, CheckSquare,
  AlertTriangle, Activity, TrendingUp,
} from 'lucide-react'

// For local testing we use a fixed env ID; in production this comes from a selector
const ENV_ID = import.meta.env.VITE_DEFAULT_ENV_ID ?? '00000000-0000-0000-0000-000000000001'

export function DashboardPage() {
  const health = useQuery({
    queryKey: ['env-health', ENV_ID],
    queryFn: () => fetchEnvironmentHealth(ENV_ID),
    refetchInterval: 15_000,
  })

  const conflicts = useQuery({
    queryKey: ['conflicts', ENV_ID],
    queryFn: () => fetchConflicts(ENV_ID, { pageSize: 50 }),
    refetchInterval: 30_000,
  })

  const stats = useQuery({
    queryKey: ['analysis-stats'],
    queryFn: fetchAnalysisStats,
    refetchInterval: 60_000,
  })

  const approvals = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: fetchPendingApprovals,
    refetchInterval: 30_000,
  })

  const h = health.data
  const s = stats.data

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Tools"
          value={h?.totalTools ?? '—'}
          sub={`${h?.activeTools ?? 0} active · ${h?.blockedTools ?? 0} blocked`}
          icon={<Wrench className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Critical Conflicts"
          value={h?.criticalConflicts ?? '—'}
          sub="require immediate review"
          icon={<AlertTriangle className="w-5 h-5" />}
          color={h?.criticalConflicts ? 'red' : 'green'}
        />
        <StatCard
          label="Pending Approvals"
          value={approvals.data?.length ?? '—'}
          sub="awaiting reviewer sign-off"
          icon={<CheckSquare className="w-5 h-5" />}
          color={(approvals.data?.length ?? 0) > 0 ? 'orange' : 'green'}
        />
        <StatCard
          label="Avg Risk Score"
          value={s?.averageRiskScore != null ? s.averageRiskScore.toFixed(1) : '—'}
          sub={`${s?.totalRuns ?? 0} analysis runs`}
          icon={<TrendingUp className="w-5 h-5" />}
          color="purple"
        />
      </div>

      {/* Health gauge + trend */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Gauge */}
        <Card className="flex flex-col items-center justify-center">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
            Environment Health Score
          </p>
          {health.isLoading ? (
            <Spinner />
          ) : (
            <HealthGauge score={h?.healthScore ?? 0} size={160} />
          )}
          <div className="mt-4 grid grid-cols-3 gap-3 w-full text-center">
            <div>
              <p className="text-xs text-gray-400">High</p>
              <p className="text-sm font-semibold text-orange-600">{h?.highConflicts ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Critical</p>
              <p className="text-sm font-semibold text-red-600">{h?.criticalConflicts ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Blocked</p>
              <p className="text-sm font-semibold text-gray-700">{h?.blockedTools ?? 0}</p>
            </div>
          </div>
        </Card>

        {/* Conflict trend */}
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-brand-500" />
              Conflict Trend (7 days)
            </p>
            <span className="text-xs text-gray-400">Last 7 days</span>
          </div>
          <ConflictTrendChart />
        </Card>
      </div>

      {/* Conflict map + recent conflicts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* D3 conflict map */}
        <Card padding={false} className="overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-500" />
            <p className="text-sm font-semibold text-gray-700">Conflict Map</p>
            <span className="ml-auto text-xs text-gray-400">drag nodes · scroll to zoom</span>
          </div>
          {conflicts.isLoading ? (
            <Spinner className="h-64" />
          ) : (
            <ConflictMapD3
              conflicts={conflicts.data?.items ?? []}
              height={300}
            />
          )}
        </Card>

        {/* Recent conflicts list */}
        <Card padding={false}>
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-700">Recent Conflicts</p>
            <a href="/conflicts" className="text-xs text-brand-600 hover:underline">View all</a>
          </div>
          {conflicts.isLoading ? (
            <Spinner />
          ) : (
            <ul className="divide-y divide-gray-100">
              {(conflicts.data?.items ?? []).slice(0, 8).map((c) => (
                <li key={c.id} className="px-5 py-3 flex items-center gap-3">
                  <SeverityBadge severity={c.severity} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 truncate font-medium">
                      {c.toolAName} ↔ {c.toolBName}
                    </p>
                    <p className="text-xs text-gray-400">{formatRelative(c.createdAt)}</p>
                  </div>
                  <span className="text-xs font-mono text-gray-400">
                    {(c.conflictScore * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
              {(conflicts.data?.items ?? []).length === 0 && (
                <li className="px-5 py-8 text-center text-sm text-gray-400">
                  No conflicts detected 🎉
                </li>
              )}
            </ul>
          )}
        </Card>
      </div>

      {/* Analysis stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Analysis Runs"
          value={s?.totalRuns ?? '—'}
          icon={<FlaskConical className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Completed Runs"
          value={s?.completedRuns ?? '—'}
          sub={s ? `${s.failedRuns} failed` : undefined}
          icon={<Activity className="w-5 h-5" />}
          color="green"
        />
        <StatCard
          label="Avg Routing Shift"
          value={s?.averageRoutingShiftPct != null ? `${s.averageRoutingShiftPct.toFixed(1)}%` : '—'}
          sub="before → after tool add"
          icon={<TrendingUp className="w-5 h-5" />}
          color={(s?.averageRoutingShiftPct ?? 0) > 20 ? 'orange' : 'green'}
        />
        <StatCard
          label="Last Run"
          value={formatRelative(s?.lastRunAt ?? null)}
          icon={<FlaskConical className="w-5 h-5" />}
        />
      </div>
    </div>
  )
}
