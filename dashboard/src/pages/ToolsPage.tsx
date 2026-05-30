import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTools } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { ToolStatusBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatDate } from '@/lib/utils'
import { Wrench, Search } from 'lucide-react'

const ENV_ID = import.meta.env.VITE_DEFAULT_ENV_ID ?? '00000000-0000-0000-0000-000000000001'

export function ToolsPage() {
  const [search, setSearch] = useState('')
  const [page, setPage]     = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['tools', ENV_ID, page],
    queryFn: () => fetchTools(ENV_ID, page, 20),
    placeholderData: (prev) => prev,
  })

  const filtered = (data?.items ?? []).filter((t) =>
    search === '' ||
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.description.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <Card>
        <div className="flex items-center gap-3">
          <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            type="text"
            placeholder="Search tools by name or description…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 text-sm bg-transparent outline-none placeholder:text-gray-400"
          />
          {data && (
            <span className="text-xs text-gray-400 flex-shrink-0">{data.total} tools</span>
          )}
        </div>
      </Card>

      {/* Table */}
      <Card padding={false}>
        {isLoading ? (
          <Spinner />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Wrench className="w-6 h-6" />}
            title="No tools found"
            description="Register a tool via the CLI or CI/CD gate to see it here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Name', 'Description', 'Server', 'Status', 'Registered'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((t) => (
                  <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs font-semibold text-gray-800">{t.name}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 max-w-xs truncate">
                      {t.description}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{t.serverId.slice(0, 8)}…</td>
                    <td className="px-4 py-3"><ToolStatusBadge status={t.status} /></td>
                    <td className="px-4 py-3 text-xs text-gray-400">{formatDate(t.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.total > 20 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">Page {page} of {Math.ceil(data.total / 20)}</span>
          <div className="flex gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50">
              Previous
            </button>
            <button onClick={() => setPage((p) => p + 1)} disabled={page * 20 >= data.total}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs disabled:opacity-40 hover:bg-gray-50">
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
