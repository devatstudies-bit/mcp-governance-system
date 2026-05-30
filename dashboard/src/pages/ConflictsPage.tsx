import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchConflicts } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { SeverityBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatDate } from '@/lib/utils'
import { Shield, Filter } from 'lucide-react'
import type { Severity } from '@/types'

const ENV_ID = import.meta.env.VITE_DEFAULT_ENV_ID ?? '00000000-0000-0000-0000-000000000001'

const SEVERITIES: Array<Severity | 'ALL'> = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const STATUSES = ['ALL', 'DETECTED', 'ACKNOWLEDGED', 'RESOLVED', 'IGNORED']

export function ConflictsPage() {
  const [severity, setSeverity] = useState<string>('ALL')
  const [status, setStatus]     = useState<string>('ALL')
  const [page, setPage]         = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['conflicts', ENV_ID, severity, status, page],
    queryFn: () => fetchConflicts(ENV_ID, {
      severity: severity === 'ALL' ? undefined : severity,
      status:   status   === 'ALL' ? undefined : status,
      page,
      pageSize: 15,
    }),
    placeholderData: (prev) => prev,
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Filter className="w-4 h-4 text-gray-400" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Severity:</span>
            {SEVERITIES.map((s) => (
              <button
                key={s}
                onClick={() => { setSeverity(s); setPage(1) }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                  severity === s
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 ml-2">
            <span className="text-xs text-gray-500">Status:</span>
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => { setStatus(s); setPage(1) }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                  status === s
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          {data && (
            <span className="ml-auto text-xs text-gray-400">{data.total} total</span>
          )}
        </div>
      </Card>

      {/* Table */}
      <Card padding={false}>
        {isLoading ? (
          <Spinner />
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={<Shield className="w-6 h-6" />}
            title="No conflicts found"
            description="No tool routing conflicts match the current filters."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Severity', 'Tool A', 'Tool B', 'Score', 'Stages', 'Status', 'Detected'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data?.items.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <SeverityBadge severity={c.severity} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.toolAName}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.toolBName}</td>
                    <td className="px-4 py-3 text-xs font-semibold text-gray-700">
                      {(c.conflictScore * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {c.detectedStages.map((s) => (
                          <span key={s} className="px-1.5 py-0.5 bg-brand-50 text-brand-700 rounded text-xs">
                            S{s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">{formatDate(c.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.total > 15 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400 text-xs">
            Page {page} of {Math.ceil(data.total / 15)}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page * 15 >= data.total}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
