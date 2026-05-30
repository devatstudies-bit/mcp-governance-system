import { api } from './client'
import type {
  HealthResponse,
  ReadinessResponse,
  EnvironmentHealth,
  ToolResponse,
  ConflictResponse,
  AnalysisRunResponse,
  AnalysisStatsResponse,
  ApprovalResponse,
  AuditEntryResponse,
  PaginatedResponse,
} from '@/types'

// ── Health ────────────────────────────────────────────────────────────────────

export const fetchHealth = () =>
  api.get<HealthResponse>('/health').then((r) => r.data)

export const fetchReadiness = () =>
  api.get<ReadinessResponse>('/readiness').then((r) => r.data)

export const fetchEnvironmentHealth = (envId: string) =>
  api.get<EnvironmentHealth>(`/v1/environments/${envId}/health`).then((r) => r.data)

// ── Tools ─────────────────────────────────────────────────────────────────────

export const fetchTools = (envId: string, page = 1, pageSize = 20) =>
  api
    .get<PaginatedResponse<ToolResponse>>(`/v1/environments/${envId}/tools`, {
      params: { page, page_size: pageSize },
    })
    .then((r) => r.data)

export const checkTool = (envId: string, payload: unknown) =>
  api.post(`/v1/environments/${envId}/tools/check`, payload).then((r) => r.data)

export const registerTool = (envId: string, payload: unknown) =>
  api.post(`/v1/environments/${envId}/tools`, payload).then((r) => r.data)

// ── Conflicts ─────────────────────────────────────────────────────────────────

export const fetchConflicts = (
  envId: string,
  params?: { severity?: string; status?: string; page?: number; pageSize?: number },
) =>
  api
    .get<PaginatedResponse<ConflictResponse>>(`/v1/environments/${envId}/conflicts`, {
      params: {
        severity: params?.severity,
        status: params?.status,
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 20,
      },
    })
    .then((r) => r.data)

// ── Analysis Runs ─────────────────────────────────────────────────────────────

export const fetchAnalysisRuns = (page = 1, pageSize = 20) =>
  api
    .get<PaginatedResponse<AnalysisRunResponse>>('/v1/api/analysis-runs/', {
      params: { page, page_size: pageSize },
    })
    .then((r) => r.data)

export const fetchAnalysisStats = () =>
  api.get<AnalysisStatsResponse>('/v1/api/analysis-runs/stats').then((r) => r.data)

export const triggerAnalysis = (payload: {
  toolId: string
  environmentId: string
  probeCount?: number
  runSimulation?: boolean
}) =>
  api
    .post<AnalysisRunResponse>('/v1/api/analysis-runs/', {
      tool_id: payload.toolId,
      environment_id: payload.environmentId,
      probe_count: payload.probeCount ?? 10,
      run_simulation: payload.runSimulation ?? true,
    })
    .then((r) => r.data)

// ── Approvals ─────────────────────────────────────────────────────────────────

export const fetchPendingApprovals = () =>
  api.get<ApprovalResponse[]>('/v1/api/approvals/pending').then((r) => r.data)

export const fetchApprovals = (page = 1, pageSize = 20) =>
  api
    .get<PaginatedResponse<ApprovalResponse>>('/v1/api/approvals/', {
      params: { page, page_size: pageSize },
    })
    .then((r) => r.data)

export const decideApproval = (
  approvalId: string,
  decision: 'approve' | 'reject',
  reason?: string,
) =>
  api
    .post(`/v1/api/approvals/${approvalId}/decide`, { decision, reason })
    .then((r) => r.data)

// ── Audit Log ─────────────────────────────────────────────────────────────────

export const fetchAuditLogs = (params?: {
  action?: string
  actorId?: string
  page?: number
  pageSize?: number
}) =>
  api
    .get<PaginatedResponse<AuditEntryResponse>>('/v1/api/audit-logs/', {
      params: {
        action: params?.action,
        actor_id: params?.actorId,
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 50,
      },
    })
    .then((r) => r.data)

export const exportAuditLogs = (format: 'json' | 'cef') =>
  api
    .get(`/v1/api/audit-logs/export`, {
      params: { format },
      responseType: format === 'cef' ? 'text' : 'json',
    })
    .then((r) => r.data)
