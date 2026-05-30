# MTGS Dashboard — Complete Explainer

> **Audience:** Anyone who needs to explain how the dashboard works end-to-end — what each screen shows, how the frontend renders it, and which backend APIs power it.

---

## What Is This System?

MTGS (MCP Tool Governance System) is a governance platform for AI tool registries. When AI assistants (LLMs) use MCP (Model Context Protocol) tools, they rely on tool names and descriptions to decide which tool to call. If two tools have similar names or overlapping descriptions, the LLM may pick the wrong one — a "routing conflict." MTGS detects these conflicts, quantifies the risk, routes approvals, and keeps an audit trail.

The **dashboard** is a React single-page application (SPA) that gives operators a visual window into the system's health, conflicts, tools, analysis runs, approvals, and audit logs.

---

## Tech Stack at a Glance

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| API Client | Axios with JWT auth injection |
| State / Data | TanStack Query (React Query) |
| Charts | Recharts (area chart), D3.js (force graph) |
| Backend | FastAPI (Python), async SQLAlchemy |
| Database | PostgreSQL (async via asyncpg) |
| Job Queue | Celery + Redis/RabbitMQ |
| AI Services | Azure OpenAI (embeddings + LLM), Azure AI Search |

---

## How the Frontend Talks to the Backend

Every API call in the dashboard goes through a single Axios instance defined in `dashboard/src/api/client.ts`.

- It reads the base URL from the `VITE_API_URL` environment variable (e.g. `http://localhost:8000`).
- Before every request it reads a JWT token from `localStorage` and injects it as `Authorization: Bearer <token>`.
- All responses come back as JSON. The backend serializes field names in **camelCase** (FastAPI's Pydantic models auto-convert from Python's snake_case).
- TanStack Query wraps every call with a 10-second stale time and 1 automatic retry, so the UI refreshes data roughly every 10 seconds without manual polling on most pages (the Approvals page uses a 15-second explicit polling interval because approvals change frequently).

---

## Application Shell

Before looking at individual pages, understand the two components that are always visible.

### Sidebar (`AppLayout` + `Sidebar`)

The sidebar renders on every page. It contains:

- **Logo** — "MTGS" brand mark in the top-left.
- **Navigation links** — seven items, each maps to a route:
  - Dashboard (`/`)
  - Conflicts (`/conflicts`)
  - Tools (`/tools`)
  - Analysis (`/analysis`)
  - Approvals (`/approvals`)
  - Audit Log (`/audit`)
  - Settings (`/settings`)
- **Version footer** — shows the app version string at the bottom.

The active link is highlighted. Clicking a link changes the route and swaps the main content area (React Router `<Outlet>`).

### Header (`Header`)

The header shows at the top of every page:

- **Page title and subtitle** — injected by each page component.
- **Health status dot** — a colored circle (green/yellow/red) updated by polling `GET /health`. It is green when the API is reachable, red otherwise.
- **Notification bell** — icon only, no dropdown in current build.
- **User avatar** — static placeholder.

---

## Page 1 — Dashboard (Home) `/`

![Dashboard](screenshots/dashboard_annotated.png)

| # | Element |
|---|---------|
| 1 | **Sidebar** — navigation links to all 7 pages; active page is highlighted |
| 2 | **Page title / subtitle** — injected by the current page component |
| 3 | **Health status dot** — green = API reachable, red = API down (`GET /health`) |
| 4 | **Total Tools** — count of registered tools in the environment |
| 5 | **Critical Conflicts** — count of open CRITICAL severity conflicts |
| 6 | **Pending Approvals** — count of approval requests awaiting a reviewer |
| 7 | **Avg Risk Score** — average risk score (0–100) across recent analysis runs |
| 8 | **Environment Health Gauge** — semi-circle arc filled based on health score (0–100) |
| 9 | **Conflict Trend Chart** — 7-day area chart: CRITICAL / HIGH / MEDIUM series |
| 10 | **Conflict Map** — D3 force graph: tool nodes, conflict edges colored by severity |
| 11 | **Recent Conflicts** — 8 most recent conflicts with severity badge and date |
| 12 | **Analysis Stats row** — total runs, completed, avg routing shift %, last run time |

This is the first screen a user sees. It gives a high-level answer to "Is everything OK right now?"

### What's on Screen

**Row 1 — KPI Cards (4 stat cards)**

| Card | What it Shows |
|------|--------------|
| Total Tools | Count of all registered tools in the default environment |
| Critical Conflicts | Count of open conflicts with CRITICAL severity |
| Pending Approvals | Count of approval requests awaiting a decision |
| Avg Risk Score | Average risk score across recent analysis runs (0–100) |

Each card has an icon on the left, a large number, and a small label. These numbers update whenever TanStack Query's stale time expires.

**Row 2 — Health Gauge + Conflict Trend Chart**

- **Health Gauge** (left half): A D3-drawn SVG semi-circle arc, like a speedometer. The arc fills from red (0) through yellow to green (100) based on the current health score. The number is printed below the arc with a label: "Healthy", "Degraded", or "Critical". A trend label ("↑ Improving" / "→ Stable" / "↓ Degrading") appears beneath that.
- **Conflict Trend Chart** (right half): A Recharts `AreaChart` with three stacked area series — CRITICAL (red), HIGH (orange), MEDIUM (yellow) — plotted over the last 7 days. Each point is a day's conflict count per severity. This gives a sense of whether conflict volume is growing.

**Row 3 — Conflict Map (full width)**

An interactive D3.js force-directed graph. Each node is a tool. Edges between nodes represent detected conflicts. Edge color encodes severity (red = CRITICAL, orange = HIGH, yellow = MEDIUM, gray = LOW). Users can:
- **Drag nodes** to rearrange the graph.
- **Zoom and pan** with mouse wheel / trackpad.
- **Hover** over an edge to see a tooltip with the conflict type and score.

This visualization makes it immediately obvious which tools are "hot" (many edges) and which conflict relationships are most severe.

**Row 4 — Recent Conflicts List + Analysis Stats**

- **Recent Conflicts** (left): The 8 most recently detected conflicts. Each row shows Tool A name, Tool B name, severity badge, conflict type, and detected date.
- **Analysis Stats** (right): Total runs, completed runs, average routing shift %, last run timestamp.

### Backend APIs Called

**`GET /health`**
- Called by the Header on every page. Returns `{ "message": "ok" }` with HTTP 200.
- The frontend only checks the HTTP status code — 200 means the dot is green, any error makes it red.

**`GET /v1/environments/{envId}/health`**
- The main call for this page. Returns a `EnvironmentHealthResponse`:

  ```json
  {
    "score": 72,
    "active_tools": 45,
    "open_conflicts": { "CRITICAL": 2, "HIGH": 5, "MEDIUM": 8, "LOW": 3 },
    "last_analysis": "2026-05-30T06:00:00Z",
    "coverage": { "probe_queries": 120, "tools_with_probes_pct": 87.5 },
    "trend": "stable"
  }
  ```

- **How the score is computed (backend):** Starts at 100. Subtracts 20 for each CRITICAL open conflict, 10 for HIGH, 5 for MEDIUM, 2 for LOW. Floor is 0.
- **Trend** is "improving" if the score went up since the last analysis, "degrading" if it went down, "stable" otherwise.
- The 4 KPI cards, the gauge, and the trend label all derive from this single response.

**`GET /v1/environments/{envId}/conflicts?page=1&pageSize=8`**
- Fetches the most recent 8 conflicts for the "Recent Conflicts" list.

**`GET /v1/api/analysis-runs/stats`**
- Returns aggregate stats for the "Analysis Stats" block.

---

## Page 2 — Conflicts `/conflicts`

![Conflicts](screenshots/conflicts_annotated.png)

| # | Element |
|---|---------|
| 1 | **Severity filter** — ALL / CRITICAL / HIGH / MEDIUM / LOW toggle buttons |
| 2 | **Status filter** — ALL / DETECTED / ACKNOWLEDGED / RESOLVED / IGNORED |
| 3 | **Conflicts table** — paginated list of detected tool routing conflicts (15 per page) |

This page is the primary operational view. An operator comes here to understand what conflicts exist and take action on them.

### What's on Screen

**Filter Bar**

Two dropdowns at the top:
- **Severity filter**: ALL / CRITICAL / HIGH / MEDIUM / LOW
- **Status filter**: ALL / DETECTED / ACKNOWLEDGED / RESOLVED / IGNORED

Selecting a filter immediately re-queries the backend (no debounce needed — the page count resets to 1).

**Conflicts Table**

Each row represents one conflict with these columns:

| Column | Content |
|--------|---------|
| Tool A | Name of the first conflicting tool |
| Tool B | Name of the second conflicting tool |
| Conflict Score | % similarity score (e.g. 94%) |
| Detection Stages | Which pipeline stages caught it (e.g. "Lexical", "Semantic") |
| Severity | Color-coded badge: red=CRITICAL, orange=HIGH, yellow=MEDIUM, gray=LOW |
| Status | open / acknowledged / resolved |
| Detected | Human-readable date |

Clicking a row could open a detail view (not yet wired in current build — the data model supports it).

**Pagination**

15 rows per page. "← Previous" / "Next →" buttons. The total count comes from the API response's `total` field.

### Backend API Called

**`GET /v1/environments/{envId}/conflicts`**

Query parameters the frontend sends:
- `severity` — one of the enum values or omitted for ALL
- `status` — one of the enum values or omitted for ALL
- `page` — current page (1-indexed)
- `page_size=15`

Response shape:

```json
{
  "items": [
    {
      "id": "uuid",
      "conflictType": "SEMANTIC_OVERLAP",
      "severity": "HIGH",
      "status": "open",
      "toolIds": ["uuid-a", "uuid-b"],
      "conflictScore": 0.94,
      "evidence": { "stage": "semantic", "similarity": 0.94 },
      "detectedAt": "2026-05-29T14:22:00Z",
      "recommendationsCount": 2
    }
  ],
  "total": 48,
  "page": 1,
  "pageSize": 15,
  "pages": 4
}
```

**How the backend handles this (route: `conflicts.py`):**
1. Validates that the environment exists and the caller has access.
2. Builds a SQLAlchemy query with optional `WHERE severity = ?` and `WHERE status = ?` clauses.
3. Runs a count query first (for `total`), then the paginated data query.
4. Converts ORM `Conflict` models to `ConflictResponse` Pydantic schemas (auto-camelCase).
5. Returns the `PaginatedResponse` wrapper.

**`PATCH /v1/environments/{envId}/conflicts/{id}`**

When an operator marks a conflict as acknowledged or resolved, the frontend sends:

```json
{ "status": "acknowledged", "resolutionNotes": "Reviewed, not a real conflict" }
```

The backend updates the `Conflict` row's `status` field and, if the status is `resolved` or `suppressed`, sets `resolved_at` and `resolved_by_id`. Suppressing a CRITICAL conflict requires admin role (enforced server-side). The updated conflict is returned.

---

## Page 3 — Tools `/tools`

![Tools](screenshots/tools_annotated.png)

| # | Element |
|---|---------|
| 1 | **Search bar** — client-side filter on tool name and description |
| 2 | **Tools table** — name, description, server ID, status badge, registered date (20 per page) |

This page lists every registered tool in the environment.

### What's on Screen

**Search Bar**

A text input at the top. Filtering is **client-side** — the frontend loads all tools and filters the list in-memory using JavaScript's `.filter()`. The filter matches on tool name or description (case-insensitive).

**Tools Table**

| Column | Content |
|--------|---------|
| Name | Tool name |
| Description | Full description text |
| Server ID | UUID of the MCP server, truncated to 8 chars + "…" |
| Status | Color-coded badge |
| Registered | Human-readable creation date |

Status badge colors:
- **ACTIVE** → green
- **BLOCKED** → red
- **DEPRECATED** → gray
- **PENDING** → blue

**Pagination**

20 rows per page (client-side on the already-fetched data).

### Backend API Called

**`GET /v1/environments/{envId}/tools`**

Returns all tools in one paginated response. The frontend requests a large page size to get all tools at once for client-side filtering.

Response shape per tool:

```json
{
  "id": "uuid",
  "name": "create_calendar_event",
  "description": "Creates a new event on the user's Google Calendar",
  "inputSchema": { "type": "object", "properties": { ... } },
  "status": "active",
  "version": 3,
  "serverId": "uuid",
  "embeddingModel": "text-embedding-3-large",
  "conflictCount": 1,
  "createdAt": "2026-05-01T10:00:00Z",
  "updatedAt": "2026-05-28T14:00:00Z"
}
```

**How the backend stores a tool:**

When a tool is first registered via `POST /v1/environments/{envId}/tools`, the backend:
1. Validates the request (name, description, input_schema are required).
2. Writes a `Tool` row to PostgreSQL with status `active` and version `1`.
3. Enforces uniqueness on `(environment_id, server_id, name)` — same-named tool on the same server is rejected.
4. Fires a Celery task `run_conflict_analysis_task(tool_id, env_id)` asynchronously — the API returns immediately (202) while analysis runs in the background.
5. The Celery worker computes an embedding via Azure OpenAI, searches for similar tools via Azure AI Search (ANN), runs the 4-stage pipeline, and writes any detected conflicts back to the DB.

---

## Page 4 — Analysis `/analysis`

![Analysis Runs](screenshots/analysis_annotated.png)

| # | Element |
|---|---------|
| 1 | **Total Runs** — count of all analysis runs ever triggered |
| 2 | **Completed** — count of runs that finished successfully |
| 3 | **Avg Risk Score** — numeric average of all run risk scores |
| 4 | **Last Run** — timestamp of the most recent analysis run |
| 5 | **Run history table** — status, trigger, risk score (color-coded), routing shift %, conflicts found, model, duration |

This page shows the history of conflict analysis runs — every time the system ran its pipeline to check for conflicts.

### What's on Screen

**Stats Row (4 cards)**

| Card | Content |
|------|---------|
| Total Runs | Count of all analysis runs ever |
| Completed | Runs with status = "completed" |
| Avg Risk Score | Numeric average of all risk scores |
| Last Run | Timestamp of the most recent run |

**Analysis Runs Table**

Each row is one analysis run:

| Column | Content |
|--------|---------|
| Status | pending / running / completed / failed (with spinner for running) |
| Trigger | What caused it: `tool_registration`, `manual`, `scheduled`, `ci_webhook` |
| Risk Score | Number 0–100 with a colored label |
| Routing Shift | % change in how the LLM would route queries after this tool was added |
| Conflicts Found | Integer count |
| LLM Model | e.g. `gpt-4o` |
| Started | Timestamp |
| Duration | Seconds |

**Risk Score Color Coding:**
- ≥ 80 → red ("Critical Risk")
- ≥ 60 → orange ("High Risk")
- ≥ 40 → yellow ("Medium Risk")
- < 40 → green ("Low Risk")

**Pagination:** 20 rows per page.

### Backend APIs Called

**`GET /v1/api/analysis-runs/stats`**

Powers the 4 stat cards:

```json
{
  "totalRuns": 142,
  "avgRiskScore": 34.2,
  "avgDurationSeconds": 8.1,
  "runsLast24h": 7,
  "criticalConflictsLast24h": 1
}
```

**`GET /v1/api/analysis-runs/`**

Returns paginated list of `AnalysisRunResponse` objects:

```json
{
  "items": [
    {
      "id": "uuid",
      "environmentId": "uuid",
      "trigger": "tool_registration",
      "status": "completed",
      "llmModel": "gpt-4o",
      "embeddingModel": "text-embedding-3-large",
      "riskScore": 72.4,
      "routingShiftPct": 18.6,
      "totalConflictsFound": 3,
      "startedAt": "2026-05-30T08:00:00Z",
      "completedAt": "2026-05-30T08:00:09Z",
      "durationSeconds": 9
    }
  ],
  "total": 142,
  "page": 1,
  "pageSize": 20
}
```

**How the risk score is calculated (backend `orchestrator.py`):**

The `AnalysisOrchestrator` runs after the conflict detection pipeline completes:

1. **Conflict severity component** (max 60 points):
   - +40 per CRITICAL conflict
   - +20 per HIGH
   - +10 per MEDIUM
   - +5 per LOW
   - Capped at 60.

2. **Simulation component** (max 40 points):
   - The system sends probe queries to Azure OpenAI and measures how much the LLM's tool routing changes when the new tool is added.
   - `routing_shift_pct × 0.4` (so a 100% shift = 40 points).

3. **Final score:** `min(conflict_component + simulation_component, 100)`.

**`POST /v1/api/analysis-runs/`**

Lets an operator manually trigger an analysis:

```json
{
  "toolId": "uuid",
  "environmentId": "uuid",
  "probeCount": 10,
  "runSimulation": true,
  "runRecommendations": true
}
```

Returns HTTP 202 (Accepted) with the new `AnalysisRun` record in `pending` status. The actual work happens in Celery workers asynchronously.

---

## Page 5 — Approvals `/approvals`

![Approvals](screenshots/approvals_annotated.png)

| # | Element |
|---|---------|
| 1 | **Pending summary banner** — yellow card showing total count of approvals awaiting a decision |
| 2 | **Approval cards** — each card shows conflict ID, tool, requester, reason, expiry, and Approve / Reject buttons |

When a HIGH or CRITICAL conflict is detected, the system creates an approval request. A reviewer must explicitly approve or reject the tool registration before it can proceed. This page is where reviewers take those actions.

### What's on Screen

**Summary Banner**

A yellow card at the top showing "N pending approvals" — an at-a-glance count so reviewers know how much work is waiting.

**Approval Cards**

Each pending approval is shown as a card (not a table row) with:
- **Status badge** — PENDING (yellow), APPROVED (green), REJECTED (red)
- **Conflict ID** — the UUID of the linked conflict
- **Tool info** — which tool triggered this approval
- **Requested by** — the actor who registered the tool
- **Created / Expires** — timestamps
- **Reason** — the requester's justification text

At the bottom of each card:
- **Approve button** (green) — calls PATCH with `{ "decision": "approve" }`
- **Reject button** (red, outlined) — calls PATCH with `{ "decision": "reject" }`

After a decision is made, TanStack Query invalidates the cache and re-fetches, so the card disappears from the pending list immediately.

**Polling:** This page re-fetches every 15 seconds so new approvals appear without a manual refresh.

### Backend APIs Called

**`GET /v1/api/approvals/pending`**

Returns only approvals with status `pending`:

```json
{
  "items": [
    {
      "id": "uuid",
      "conflictId": "uuid",
      "toolId": "uuid",
      "environmentId": "uuid",
      "requestedBy": "user-uuid",
      "reason": "New analytics tool for the data team",
      "status": "pending",
      "reviewerId": null,
      "comment": null,
      "createdAt": "2026-05-30T09:00:00Z",
      "decidedAt": null
    }
  ],
  "total": 3,
  "pendingCount": 3
}
```

**`PATCH /v1/api/approvals/{id}/decide`**

The reviewer's action:

```json
{
  "decision": "approve",
  "comment": "Reviewed - distinct enough from existing tools"
}
```

**How the backend enforces this (route: `approvals.py`):**
- Only users with role `reviewer` or `admin` can call this endpoint (role check enforced in the service layer).
- The `ApprovalService` updates the `Approval` row: sets `status`, `reviewer_id`, `comment`, and `decided_at`.
- If approved: the linked `Tool` record's status is updated to `active`.
- If rejected: the linked `Tool` is set to `blocked`.
- An `AuditLog` entry is written for every decision (immutable record).

---

## Page 6 — Audit Log `/audit`

![Audit Log](screenshots/audit_annotated.png)

| # | Element |
|---|---------|
| 1 | **Action filter** — free-text input to filter by action type (e.g. `TOOL_REGISTERED`) |
| 2 | **Actor ID filter** — free-text input to filter by the UUID of the user who acted |
| 3 | **Export JSON** — downloads the filtered log as a JSON file |
| 4 | **Export CEF** — downloads in Common Event Format for SIEM tools (Splunk, ArcSight, QRadar) |
| 5 | **Audit entries table** — timestamp, action (color-coded), actor, resource ID, environment (25 per page) |

Every action in the system is logged to an immutable audit trail. This page lets operators search and export that log. It is the compliance and forensics view.

### What's on Screen

**Filter Bar**

Two free-text inputs:
- **Action** — filter by action type (e.g. type "TOOL" to see all tool-related events)
- **Actor ID** — filter by the UUID of the user who performed the action

**Export Buttons**

- **Export JSON** — downloads the filtered log as a JSON array
- **Export CEF** — downloads in Common Event Format (the standard format used by SIEM tools like Splunk, ArcSight, QRadar)

**Audit Table**

| Column | Content |
|--------|---------|
| Timestamp | ISO datetime |
| Action | Color-coded action type string |
| Actor | UUID of the user who acted |
| Resource ID | UUID of the thing that was acted on |
| Environment | Environment UUID |

**Action type color codes:**
- `TOOL_REGISTERED` → green
- `TOOL_UPDATED` → blue
- `CONFLICT_DETECTED` → orange
- `APPROVAL_APPROVED` → green
- `APPROVAL_REJECTED` → red
- All others → gray

**Pagination:** 25 rows per page.

### Backend APIs Called

**`GET /v1/api/audit-logs/`**

```
?action=TOOL_REGISTERED&actor_id=uuid&page=1&page_size=25
```

Returns:

```json
{
  "items": [
    {
      "entryId": "uuid",
      "action": "TOOL_REGISTERED",
      "actorId": "user-uuid",
      "resourceId": "tool-uuid",
      "resourceType": "Tool",
      "environmentId": "env-uuid",
      "metadata": { "tool_name": "send_email", "version": 1 },
      "timestamp": "2026-05-30T10:15:00Z"
    }
  ],
  "total": 892,
  "page": 1,
  "pageSize": 25
}
```

**`GET /v1/api/audit-logs/export?format=cef`**

Returns a plain-text CEF file. Example CEF line:
```
CEF:0|MTGS|MTGS|1.0|TOOL_REGISTERED|Tool registered|5|...
```

**How audit logs are written (backend design):**

Every mutating endpoint (tool registration, conflict update, approval decision) calls the `AuditService` to write an `AuditLog` row. These rows are **never updated or deleted** — they are append-only by design. There is no `UPDATE` or `DELETE` issued against the `audit_logs` table anywhere in the codebase. This makes the audit trail tamper-evident.

---

## Page 7 — Settings `/settings`

![Settings](screenshots/settings_annotated.png)

| # | Element |
|---|---------|
| 1 | **Circuit Breakers section** — table of breaker states for Azure OpenAI, Azure AI Search, and other external services |
| 2 | **Refresh button** — re-fetches `/readiness` on demand to get latest breaker states |
| 3 | **Dashboard Configuration section** — read-only display of env-var–driven settings |
| 4 | **API Base URL** — the backend URL the frontend is pointed at (`VITE_API_URL`) |
| 5 | **Default Environment ID** — which environment the dashboard queries by default (`VITE_DEFAULT_ENV_ID`) |
| 6 | **System Status** — operational / degraded, derived from the `/readiness` HTTP status code |

This page has two sections: system health internals (circuit breakers) and dashboard configuration.

### What's on Screen

**Circuit Breaker Status**

A table showing the state of every circuit breaker in the system. A circuit breaker wraps calls to external services (Azure OpenAI, Azure AI Search) and "opens" (stops making calls) after too many failures, to prevent cascading failures.

| Column | Content |
|--------|---------|
| Name | Which service the breaker protects |
| Total Calls | Lifetime call count |
| Successful | Count of successful calls |
| Failed | Count of failed calls |
| Rejected | Calls rejected because the breaker was OPEN |
| State | CLOSED (healthy) / OPEN (failing fast) / HALF_OPEN (recovering) |
| Transitions | How many times the breaker has changed state |

State badge colors:
- **CLOSED** → green (normal operation)
- **OPEN** → red (failing fast, not calling the service)
- **HALF_OPEN** → yellow (testing if the service recovered)

A **Refresh** button re-fetches this data on demand.

**Dashboard Configuration**

A read-only display of:
- API Base URL (from environment variable)
- Default Environment ID
- System Status ("operational" or "degraded")

### Backend API Called

**`GET /readiness`**

This is the only endpoint this page calls. Example response:

```json
{
  "message": "ready",
  "database": "ok",
  "redis": "ok",
  "circuit_breakers": {
    "azure_openai": {
      "state": "CLOSED",
      "total_calls": 1204,
      "successful_calls": 1198,
      "failed_calls": 6,
      "rejected_calls": 0,
      "state_transitions": 2
    },
    "azure_search": {
      "state": "OPEN",
      "total_calls": 850,
      "successful_calls": 844,
      "failed_calls": 11,
      "rejected_calls": 245,
      "state_transitions": 3
    }
  }
}
```

If the database is unreachable, this endpoint returns HTTP 503 (Service Unavailable) instead of 200. The frontend detects this and shows a system status of "degraded."

---

## The 4-Stage Conflict Detection Pipeline

This is the core intelligence of the system. Every time a tool is registered, this pipeline runs in a Celery worker.

```
Tool Registered
      │
      ▼
┌─────────────────────────────────────┐
│  Stage 1: Lexical Analysis          │  ~100ms, pure Python
│  • Exact name match                 │
│  • Fuzzy name match (>80% similar)  │
│  • Duplicate tool detection         │
└─────────────┬───────────────────────┘
              │ CRITICAL found? ──────────────────┐
              ▼                                   │
┌─────────────────────────────────────┐           │
│  Stage 2: Schema Analysis           │  ~200ms   │
│  • Input parameter overlap          │           │
│  • Schema collision detection       │           │
└─────────────┬───────────────────────┘           │
              │ CRITICAL found? ──────────────────┤
              ▼                                   │
┌─────────────────────────────────────┐           │
│  Stage 3: Semantic Analysis         │  async    │
│  • Azure OpenAI embedding           │           │
│  • ANN search (top 20 nearest)      │           │
│  • Cosine similarity ≥ 0.80 = flag  │           │
└─────────────┬───────────────────────┘           │
              │                                   │
              ▼ ◄─────────────────────────────────┘
┌─────────────────────────────────────┐
│  Stage 4: Behavioral Simulation     │  separate Celery queue
│  • Probe queries sent to LLM        │
│  • Routing shift % measured         │
│  • Risk score calculated            │
└─────────────────────────────────────┘
```

**Short-circuit behavior:** If Stage 1 or Stage 2 finds a CRITICAL conflict, Stage 3 is skipped entirely. This saves expensive LLM API calls when the problem is already obvious.

**Severity thresholds for Stage 3 (semantic):**
- Cosine similarity ≥ 0.90 → HIGH conflict
- Cosine similarity ≥ 0.80 → MEDIUM conflict
- Cosine similarity < 0.80 → no conflict flagged

---

## Celery Background Workers

The dashboard and API are fast because heavy work runs asynchronously in Celery workers.

| Task | Queue | Trigger | What It Does |
|------|-------|---------|-------------|
| `run_conflict_analysis_task` | `analysis` | Tool registration / update | Runs full conflict pipeline, persists conflicts, updates risk score |
| `generate_embeddings_task` | `embeddings` | After conflict analysis | Batch-embeds tools, upserts into Azure AI Search |
| `sync_mcp_server_task` | `analysis` | Every 15 minutes (beat) | Fetches live tool list from MCP server, diffs with DB, queues analysis for changed tools |
| `scheduled_conflict_scan_task` | `analysis` | Every hour (beat) | Re-analyses all active tools in all environments |

Workers use `acks_late=True` — a task is only acknowledged (removed from queue) after it successfully completes. If a worker crashes mid-task, the task is re-queued. Max retries: 3.

---

## Data Flow: Registering a Tool End-to-End

Here is the complete journey when an operator registers a new tool:

```
1. Operator calls POST /v1/environments/{envId}/tools
   Body: { name, description, inputSchema, serverId }

2. Backend (tools.py route):
   a. Validates request fields
   b. Checks (environment_id, server_id, name) uniqueness in DB
   c. Creates Tool row (status=active, version=1)
   d. Creates AnalysisRun row (status=pending)
   e. Writes AuditLog entry (action=TOOL_REGISTERED)
   f. Enqueues run_conflict_analysis_task to Celery
   g. Returns HTTP 201 with { toolId, status: "registered", analysisRunId }

3. Celery worker (run_conflict_analysis_task):
   a. Loads the new tool + all existing tools in the environment
   b. Checks if tool's embedding is stale → calls Azure OpenAI to recompute if needed
   c. Runs Stage 1 (lexical) and Stage 2 (schema) synchronously
   d. If no CRITICAL: runs Stage 3 (Azure AI Search ANN query)
   e. Writes Conflict rows for each detected conflict
   f. Updates AnalysisRun: status=completed, risk_score, duration_seconds

4. Celery worker (generate_embeddings_task, chained):
   a. Batch-embeds tool via Azure OpenAI text-embedding-3-large
   b. Upserts vector into Azure AI Search index

5. If CRITICAL or HIGH conflict found → ApprovalService.create_approval()
   a. Creates Approval row (status=pending)
   b. Tool status updated to pending_approval

6. Notification dispatch (async):
   a. Slack webhook (if configured)
   b. Email via SMTP (if configured)
   c. PagerDuty (for CRITICAL, if configured)

7. Dashboard reflects all of this:
   - /conflicts page shows new conflicts
   - /approvals page shows pending approval
   - /analysis page shows completed analysis run
   - /dashboard health score decreases
```

---

## Key Data Models (Simplified)

```
Organization
  └── Environment (has a Policy: max_severity_to_block, notification_channels)
        ├── McpServer
        │     └── Tool (name, description, input_schema, status, version)
        │           └── ToolVersion (immutable snapshots with diffs)
        ├── Conflict (tool_ids[], severity, status, conflict_score, evidence)
        │     └── Recommendation (proposed_change, predicted_score_after)
        ├── AnalysisRun (trigger, status, risk_score, routing_shift_pct)
        ├── ProbeQuery (query_text used for behavioral simulation)
        └── Approval (conflict_id, tool_id, decision, comment)

AuditLog (append-only: action, actor_id, resource_id, metadata, timestamp)
User (email, role: viewer/developer/reviewer/admin)
ApiKey (key_hash, scopes, expires_at)
```

---

## Role-Based Access Control

| Role | Can Do |
|------|--------|
| `viewer` | Read everything — health, conflicts, tools, audit |
| `developer` | Register tools, trigger manual analysis |
| `reviewer` | Approve / reject approval requests |
| `admin` | Everything above + suppress CRITICAL conflicts, manage environments |

Role checks are enforced in the Python service layer, not just at the route level.

---

## API Authentication

All API endpoints (except `/health` and `/readiness`) require a JWT bearer token:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

The dashboard injects this automatically from `localStorage` on every Axios request. The backend validates the token's signature (using `JWT_SECRET_KEY`), extracts the `user_id` and `role` claims, and makes the current user available to every route handler.

The CI/CD webhook endpoint (`POST /v1/webhooks/ci-check`) uses an API key header instead of JWT:
```
X-API-Key: <api-key>
X-Environment: <environment-id>
```

---

## Summary Table: Every Frontend Screen → Backend Endpoint

| Page | Action | Endpoint |
|------|--------|----------|
| All pages | Health dot in header | `GET /health` |
| Dashboard | Load KPIs + gauge + trend | `GET /v1/environments/{id}/health` |
| Dashboard | Recent conflicts list | `GET /v1/environments/{id}/conflicts?pageSize=8` |
| Dashboard | Analysis stats block | `GET /v1/api/analysis-runs/stats` |
| Conflicts | Load conflict table | `GET /v1/environments/{id}/conflicts?severity=&status=&page=` |
| Conflicts | Acknowledge / resolve | `PATCH /v1/environments/{id}/conflicts/{conflictId}` |
| Tools | Load all tools | `GET /v1/environments/{id}/tools` |
| Analysis | Load stats cards | `GET /v1/api/analysis-runs/stats` |
| Analysis | Load run history | `GET /v1/api/analysis-runs/` |
| Analysis | Trigger manual run | `POST /v1/api/analysis-runs/` |
| Approvals | Load pending approvals | `GET /v1/api/approvals/pending` |
| Approvals | Approve / reject | `PATCH /v1/api/approvals/{id}/decide` |
| Audit | Load audit log | `GET /v1/api/audit-logs/?action=&actor_id=&page=` |
| Audit | Export JSON | `GET /v1/api/audit-logs/export?format=json` |
| Audit | Export CEF (SIEM) | `GET /v1/api/audit-logs/export?format=cef` |
| Settings | Circuit breaker status | `GET /readiness` |
