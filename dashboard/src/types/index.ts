// ─────────────────────────────────────────────────────────────────────────────
// Shared domain types — mirror the FastAPI Pydantic response schemas
// ─────────────────────────────────────────────────────────────────────────────

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type ConflictStatus = 'DETECTED' | 'ACKNOWLEDGED' | 'RESOLVED' | 'IGNORED'
export type ToolStatus = 'ACTIVE' | 'BLOCKED' | 'DEPRECATED' | 'PENDING'
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED'
export type AnalysisStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN'

// ── Health ────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  version: string
  environment: string
}

export interface CircuitBreakerInfo {
  name: string
  state: CircuitState
  totalCalls: number
  successful: number
  failed: number
  rejected: number
  stateChanges: number
}

export interface ReadinessResponse {
  status: string
  circuitBreakers: Record<string, CircuitBreakerInfo>
}

export interface EnvironmentHealth {
  environmentId: string
  healthScore: number          // 0–100
  totalTools: number
  activeTools: number
  blockedTools: number
  criticalConflicts: number
  highConflicts: number
  pendingApprovals: number
}

// ── Tools ─────────────────────────────────────────────────────────────────────

export interface ToolResponse {
  id: string
  name: string
  description: string
  serverId: string
  status: ToolStatus
  inputSchema: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

// ── Conflicts ─────────────────────────────────────────────────────────────────

export interface ConflictResponse {
  id: string
  toolAId: string
  toolBId: string
  toolAName: string
  toolBName: string
  severity: Severity
  status: ConflictStatus
  conflictScore: number
  detectedStages: string[]
  createdAt: string
}

// ── Analysis Runs ─────────────────────────────────────────────────────────────

export interface AnalysisRunResponse {
  id: string
  environmentId: string
  trigger: string
  status: AnalysisStatus
  riskScore: number | null
  routingShiftPct: number | null
  totalConflictsFound: number | null
  startedAt: string | null
  completedAt: string | null
  llmModel: string
  embeddingModel: string
}

export interface AnalysisStatsResponse {
  totalRuns: number
  completedRuns: number
  failedRuns: number
  averageRiskScore: number
  averageRoutingShiftPct: number
  lastRunAt: string | null
}

// ── Approvals ─────────────────────────────────────────────────────────────────

export interface ApprovalResponse {
  id: string
  conflictId: string
  requestedBy: string
  reviewedBy: string | null
  status: ApprovalStatus
  reason: string | null
  createdAt: string
  decidedAt: string | null
  expiresAt: string
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

export interface AuditEntryResponse {
  id: string
  action: string
  actorId: string
  resourceId: string
  environmentId: string | null
  metadata: Record<string, unknown>
  timestamp: string
}

// ── Pagination ────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}
