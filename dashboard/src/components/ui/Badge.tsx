import { cn, SEVERITY_COLORS } from '@/lib/utils'
import type { Severity, ToolStatus, ApprovalStatus, AnalysisStatus, CircuitState } from '@/types'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'severity' | 'status' | 'neutral'
  severity?: Severity
  className?: string
}

export function Badge({ children, variant = 'neutral', severity, className }: BadgeProps) {
  const base = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border'

  if (variant === 'severity' && severity) {
    const c = SEVERITY_COLORS[severity]
    return (
      <span className={cn(base, c.bg, c.text, c.border, className)}>
        <span className={cn('w-1.5 h-1.5 rounded-full', c.dot)} />
        {children}
      </span>
    )
  }

  return (
    <span className={cn(base, 'bg-gray-100 text-gray-600 border-gray-200', className)}>
      {children}
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge variant="severity" severity={severity}>{severity}</Badge>
}

const TOOL_STATUS_STYLE: Record<ToolStatus, string> = {
  ACTIVE:     'bg-green-50 text-green-700 border-green-200',
  BLOCKED:    'bg-red-50 text-red-700 border-red-200',
  DEPRECATED: 'bg-gray-100 text-gray-500 border-gray-200',
  PENDING:    'bg-blue-50 text-blue-700 border-blue-200',
}

export function ToolStatusBadge({ status }: { status: ToolStatus }) {
  return (
    <span className={cn(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium border',
      TOOL_STATUS_STYLE[status],
    )}>
      {status}
    </span>
  )
}

const APPROVAL_STATUS_STYLE: Record<ApprovalStatus, string> = {
  PENDING:  'bg-yellow-50 text-yellow-700 border-yellow-200',
  APPROVED: 'bg-green-50 text-green-700 border-green-200',
  REJECTED: 'bg-red-50 text-red-700 border-red-200',
  EXPIRED:  'bg-gray-100 text-gray-500 border-gray-200',
}

export function ApprovalStatusBadge({ status }: { status: ApprovalStatus }) {
  return (
    <span className={cn(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium border',
      APPROVAL_STATUS_STYLE[status],
    )}>
      {status}
    </span>
  )
}

const ANALYSIS_STATUS_STYLE: Record<AnalysisStatus, string> = {
  PENDING:   'bg-gray-100 text-gray-500 border-gray-200',
  RUNNING:   'bg-blue-50 text-blue-700 border-blue-200',
  COMPLETED: 'bg-green-50 text-green-700 border-green-200',
  FAILED:    'bg-red-50 text-red-700 border-red-200',
}

export function AnalysisStatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span className={cn(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium border',
      ANALYSIS_STATUS_STYLE[status],
    )}>
      {status}
    </span>
  )
}

const CIRCUIT_STATE_STYLE: Record<CircuitState, string> = {
  CLOSED:    'bg-green-50 text-green-700 border-green-200',
  HALF_OPEN: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  OPEN:      'bg-red-50 text-red-700 border-red-200',
}

export function CircuitStateBadge({ state }: { state: CircuitState }) {
  return (
    <span className={cn(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium border',
      CIRCUIT_STATE_STYLE[state],
    )}>
      {state}
    </span>
  )
}
