import { useQuery } from '@tanstack/react-query'
import { fetchAnalysisRuns, fetchAnalysisStats } from '@/api/endpoints'
import { Card, StatCard } from '@/components/ui/Card'
import { AnalysisStatusBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatDate, formatRelative, riskColor, riskLabel } from '@/lib/utils'
import { FlaskConical, Activity, TrendingUp, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'

export function AnalysisPage() {
  const runs  = useQuery({ queryKey: ['analysis-runs'],  queryFn: () => fetchAnalysisRuns(1, 20) })
  const stats = useQuery({ queryKey: ['analysis-stats'], queryFn: fetchAnalysisStats, refetchInterval: 30_000 })

  const s = stats.data

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Runs"      value={s?.totalRuns ?? '—'}      icon={<FlaskConical className="w-5 h-5" />} color="blue" />
        <StatCard label="Completed"        value={s?.completedRuns ?? '—'}  icon={<Activity className="w-5 h-5" />}    color="green" />
        <StatCard label="Avg Risk Score"   value={s?.averageRiskScore != null ? s.averageRiskScore.toFixed(1) : '—'}
                                                                             icon={<TrendingUp className="w-5 h-5" />}  color="purple" />
        <StatCard label="Last Run"         value={formatRelative(s?.lastRunAt ?? null)} icon={<Clock className="w-5 h-5" />} />
      </div>

      {/* Run list */}
      <Card padding={false}>
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-700">Analysis Run History</p>
          <span className="text-xs text-gray-400">{runs.data?.total ?? 0} runs</span>
        </div>

        {runs.isLoading ? (
          <Spinner />
        ) : (runs.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={<FlaskConical className="w-6 h-6" />}
            title="No analysis runs yet"
            description="Register a tool to trigger the first conflict analysis run."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Status', 'Trigger', 'Risk Score', 'Routing Shift', 'Conflicts', 'Model', 'Started', 'Duration'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {runs.data?.items.map((r) => {
                  const duration =
                    r.startedAt && r.completedAt
                      ? `${((new Date(r.completedAt).getTime() - new Date(r.startedAt).getTime()) / 1000).toFixed(1)}s`
                      : '—'
                  return (
                    <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3"><AnalysisStatusBadge status={r.status} /></td>
                      <td className="px-4 py-3 text-xs text-gray-600 capitalize">{r.trigger}</td>
                      <td className="px-4 py-3">
                        {r.riskScore != null ? (
                          <span className={cn('text-sm font-semibold', riskColor(r.riskScore))}>
                            {r.riskScore.toFixed(1)}
                            <span className="ml-1 text-xs font-normal text-gray-400">
                              ({riskLabel(r.riskScore)})
                            </span>
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-700">
                        {r.routingShiftPct != null ? `${r.routingShiftPct.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-700">{r.totalConflictsFound ?? '—'}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">{r.llmModel || '—'}</td>
                      <td className="px-4 py-3 text-xs text-gray-400">{formatDate(r.startedAt)}</td>
                      <td className="px-4 py-3 text-xs text-gray-400">{duration}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
