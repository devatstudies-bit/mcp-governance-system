import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPendingApprovals, decideApproval } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { ApprovalStatusBadge } from '@/components/ui/Badge'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { formatDate } from '@/lib/utils'
import { CheckSquare, CheckCircle, XCircle, Clock } from 'lucide-react'

export function ApprovalsPage() {
  const qc = useQueryClient()

  const { data: pending, isLoading } = useQuery({
    queryKey: ['pending-approvals'],
    queryFn: fetchPendingApprovals,
    refetchInterval: 15_000,
  })

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'approve' | 'reject' }) =>
      decideApproval(id, decision),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-approvals'] })
    },
  })

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-4 py-2.5 bg-yellow-50 border border-yellow-200 rounded-xl">
          <Clock className="w-4 h-4 text-yellow-600" />
          <span className="text-sm font-medium text-yellow-700">
            {isLoading ? '…' : pending?.length ?? 0} pending
          </span>
        </div>
        <p className="text-sm text-gray-500">
          CRITICAL and HIGH conflicts require reviewer+ sign-off before the tool becomes active.
        </p>
      </div>

      {isLoading ? (
        <Spinner />
      ) : (pending?.length ?? 0) === 0 ? (
        <Card>
          <EmptyState
            icon={<CheckSquare className="w-6 h-6" />}
            title="No pending approvals"
            description="All CRITICAL and HIGH conflicts have been reviewed. The queue is clear."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {pending?.map((a) => (
            <Card key={a.id} className="border-l-4 border-l-yellow-400">
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <ApprovalStatusBadge status={a.status} />
                    <span className="text-xs text-gray-400 font-mono">{a.id.slice(0, 8)}</span>
                  </div>
                  <p className="text-sm text-gray-700">
                    <span className="font-medium">Conflict:</span>{' '}
                    <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{a.conflictId.slice(0, 8)}</span>
                  </p>
                  <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-400">
                    <span>Requested by <strong className="text-gray-600">{a.requestedBy}</strong></span>
                    <span>Created {formatDate(a.createdAt)}</span>
                    <span>Expires {formatDate(a.expiresAt)}</span>
                  </div>
                  {a.reason && (
                    <p className="mt-2 text-xs text-gray-500 bg-gray-50 rounded p-2 border">
                      {a.reason}
                    </p>
                  )}
                </div>
                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button
                    onClick={() => decide.mutate({ id: a.id, decision: 'approve' })}
                    disabled={decide.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                  >
                    <CheckCircle className="w-3.5 h-3.5" /> Approve
                  </button>
                  <button
                    onClick={() => decide.mutate({ id: a.id, decision: 'reject' })}
                    disabled={decide.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 text-xs font-medium rounded-lg hover:bg-red-100 disabled:opacity-50 transition-colors"
                  >
                    <XCircle className="w-3.5 h-3.5" /> Reject
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
