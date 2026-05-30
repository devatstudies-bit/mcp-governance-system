import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchAuditLogs, exportAuditLogs } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatDate } from '@/lib/utils'
import { ScrollText, Download } from 'lucide-react'

const ACTION_COLORS: Record<string, string> = {
  TOOL_REGISTERED:       'text-green-700 bg-green-50',
  TOOL_UPDATED:          'text-blue-700 bg-blue-50',
  TOOL_DELETED:          'text-red-700 bg-red-50',
  CONFLICT_DETECTED:     'text-orange-700 bg-orange-50',
  APPROVAL_APPROVED:     'text-green-700 bg-green-50',
  APPROVAL_REJECTED:     'text-red-700 bg-red-50',
  APPROVAL_REQUESTED:    'text-yellow-700 bg-yellow-50',
  ANALYSIS_RUN_STARTED:  'text-purple-700 bg-purple-50',
  ANALYSIS_RUN_COMPLETED:'text-purple-700 bg-purple-50',
  USER_LOGIN:            'text-gray-700 bg-gray-100',
}

export function AuditPage() {
  const [action, setAction]   = useState('')
  const [actorId, setActorId] = useState('')
  const [page, setPage]       = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['audit-logs', action, actorId, page],
    queryFn: () => fetchAuditLogs({
      action: action || undefined,
      actorId: actorId || undefined,
      page,
      pageSize: 25,
    }),
    placeholderData: (prev) => prev,
  })

  const handleExport = async (format: 'json' | 'cef') => {
    const blob = await exportAuditLogs(format)
    const url  = URL.createObjectURL(new Blob([
      typeof blob === 'string' ? blob : JSON.stringify(blob, null, 2),
    ]))
    const a = document.createElement('a')
    a.href = url
    a.download = `audit.${format === 'cef' ? 'cef' : 'json'}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Filter + export bar */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            placeholder="Filter by action (e.g. TOOL_REGISTERED)"
            value={action}
            onChange={(e) => { setAction(e.target.value); setPage(1) }}
            className="flex-1 min-w-48 px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-300"
          />
          <input
            type="text"
            placeholder="Filter by actor ID"
            value={actorId}
            onChange={(e) => { setActorId(e.target.value); setPage(1) }}
            className="flex-1 min-w-36 px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-300"
          />
          <div className="flex gap-2 ml-auto">
            <button
              onClick={() => handleExport('json')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> JSON
            </button>
            <button
              onClick={() => handleExport('cef')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> CEF (SIEM)
            </button>
          </div>
        </div>
      </Card>

      {/* Audit table */}
      <Card padding={false}>
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-700">Audit Entries</p>
          <span className="text-xs text-gray-400">{data?.total ?? 0} entries · immutable</span>
        </div>

        {isLoading ? (
          <Spinner />
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={<ScrollText className="w-6 h-6" />}
            title="No audit entries"
            description="Governance actions will appear here as they happen."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Timestamp', 'Action', 'Actor', 'Resource', 'Environment'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 font-mono">
                {data?.items.map((e) => (
                  <tr key={e.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">
                      {formatDate(e.timestamp)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                        ACTION_COLORS[e.action] ?? 'text-gray-600 bg-gray-100'
                      }`}>
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-600 truncate max-w-[120px]">
                      {e.actorId}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-400 truncate max-w-[120px]">
                      {e.resourceId.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-400">
                      {e.environmentId ? e.environmentId.slice(0, 8) + '…' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.total > 25 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-xs text-gray-400">Page {page} of {Math.ceil(data.total / 25)}</span>
          <div className="flex gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50">
              Previous
            </button>
            <button onClick={() => setPage((p) => p + 1)} disabled={page * 25 >= data.total}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50">
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
