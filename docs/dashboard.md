# Governance Dashboard

The MTGS dashboard is a React + TypeScript + Tailwind CSS application that provides full visibility into your MCP tool registry's health. It connects to the MTGS API and presents conflict state, routing risk, and governance workflows through a visual interface.

---

## Overview

The dashboard is structured around five primary views:

| View | Purpose |
|---|---|
| **Dashboard Home** | Health score, conflict breakdown, activity feed |
| **Tool Registry** | Browse, filter, and inspect all registered tools |
| **Conflict Map** | Interactive force-directed graph of tool conflicts |
| **Conflict Queue** | Actionable list of open conflicts with workflow controls |
| **Audit Log** | Filterable timeline of all state changes |

---

## Dashboard Home

The landing view gives an at-a-glance health summary for the selected environment.

```
┌─────────────────────────────────────────────────────────────────────┐
│  MTGS  [Environment: prod ▼]                           ⚙ Settings  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────┐   ┌───────────────────────────────────┐  │
│  │  Environment Health │   │  Open Conflicts                   │  │
│  │                     │   │                                   │  │
│  │        74           │   │  ●  CRITICAL   0                  │  │
│  │       ──────        │   │  ●  HIGH       2  ████            │  │
│  │         B           │   │  ●  MEDIUM     5  ██████████      │  │
│  │   (↑ from 68)       │   │  ●  LOW       11  ████████████    │  │
│  │                     │   │  ●  INFO       3  ██████          │  │
│  └─────────────────────┘   └───────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Recent Activity                                             │   │
│  │  ─────────────────────────────────────────────────────────  │   │
│  │  ✓  create_zendesk_ticket  registered   2 min ago  no conflicts  │
│  │  ⚠  create_task            conflict resolved  15 min ago        │
│  │  ✗  send_notification      blocked (HIGH conflict)  1h ago      │
│  │  ✓  delete_user            registered   2h ago  no conflicts    │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Quick Check                                                 │   │
│  │  Paste a tool definition to check before registering  [→]   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Health Score (0–100)** is computed by the API (`GET /v1/environments/{id}/health`):
- Starts at 100; each open conflict deducts points by severity
- Capped deductions prevent single-incident catastrophizing
- Probe query coverage adds up to +15 bonus points
- Trend arrow shows change from previous analysis run

---

## Tool Registry View

A paginated table of all registered tools with inline conflict status.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Tool Registry  [prod]          [🔍 Search]  [Filter ▼]  [+ Register]│
├──────────────────┬──────────┬────────┬──────────────┬───────────────┤
│  Name            │  Server  │ Status │ Conflicts    │ Last Updated  │
├──────────────────┼──────────┼────────┼──────────────┼───────────────┤
│ create_jira_issue│ jira-mcp │ active │ ⚠ 1 MEDIUM  │ 3 days ago    │
│ send_slack_msg   │ slack-mcp│ active │ ✓ none       │ 1 week ago    │
│ create_task      │ asana-mcp│ flagged│ ✗ 1 HIGH    │ 2 hours ago   │
│ get_user_profile │ auth-mcp │ active │ ✓ none       │ 5 days ago    │
│ create_ticket    │ snow-mcp │ active │ ⚠ 1 MEDIUM  │ yesterday     │
└──────────────────┴──────────┴────────┴──────────────┴───────────────┘
  Showing 1–50 of 142 tools
```

**Row click** opens the Tool Detail panel:

```
┌─────────────────────────────────────────────────────────────────────┐
│  create_jira_issue                        [Edit]  [Deprecate]  [×]  │
├─────────────────────────────────────────────────────────────────────┤
│  Server: jira-mcp                                                    │
│  Team: Engineering Platform                                          │
│  Status: active  Version: 3  Last updated: 2025-05-23               │
│                                                                      │
│  Description:                                                        │
│  Creates a new issue in Jira for the specified project. Use this     │
│  tool when the user wants to create a bug report, feature request,  │
│  or task in the Jira project management system.                     │
│                                                                      │
│  Input Schema:   project_key (string, required)                     │
│                  summary (string, required)                         │
│                  issue_type (enum: Bug|Task|Story|Epic)             │
│                                                                      │
│  ── Active Conflicts ─────────────────────────────────────────────  │
│  ⚠ MEDIUM  SEMANTIC_OVERLAP  ↔ create_linear_task  score: 83.4     │
│     [View Conflict]  [View Recommendations]                         │
│                                                                      │
│  ── Version History ──────────────────────────────────────────────  │
│  v3  Alice  "Narrowed to Jira only"  May 20  [View diff]           │
│  v2  Bob    "Added issue_type param"  Apr 10  [View diff]           │
│  v1  Alice  Initial registration     Apr 1                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Conflict Map

The Conflict Map is a **force-directed graph** built with D3.js that visualizes all active conflicts as a network.

```
                    ┌─────────────────────────────────────────────────┐
                    │  Conflict Map  [prod]                           │
                    │  Filter: [All Severities ▼]  [All Servers ▼]   │
                    │  Toggle: [● Show resolved]  [● Cluster by server]│
                    ├─────────────────────────────────────────────────┤
                    │                                                 │
                    │        ◉ create_jira_issue                      │
                    │       ╱                                         │
                    │  ══════ (HIGH, SEMANTIC_OVERLAP)                │
                    │       ╲                                         │
                    │        ◉ create_linear_task                     │
                    │         ╲                                       │
                    │     ─────  (MEDIUM, SEMANTIC_OVERLAP)           │
                    │           ╲                                     │
                    │            ◉ create_asana_task                  │
                    │                                                 │
                    │        ◉ send_slack_message                     │
                    │       ╱                                         │
                    │  ─────  (MEDIUM, SIMILAR_NAME)                  │
                    │       ╲                                         │
                    │        ◉ send_slack_msg                         │
                    │                                                 │
                    └─────────────────────────────────────────────────┘
```

**Node encoding:**
- Node size: proportional to number of conflict edges
- Node color: status (green=active, yellow=flagged, gray=deprecated)

**Edge encoding:**
- 🔴 Thick solid line: CRITICAL
- 🟠 Solid line: HIGH
- 🟡 Dashed line: MEDIUM
- 🔵 Thin dashed line: LOW

**Interactions:**
- **Click node** → highlight all conflicts for that tool; open tool detail panel
- **Click edge** → open conflict detail panel with full evidence
- **Hover node** → tooltip shows tool name, server, conflict count
- **Drag node** → reposition (layout is preserved until refresh)
- **Scroll/pinch** → zoom in/out
- **Filter panel** → filter by severity, server, team; toggle resolved conflicts

---

## Conflict Queue

The Conflict Queue is the primary workflow view for resolving conflicts.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Conflict Queue  [prod]  [Filter: all ▼]  [Bulk: Acknowledge ▼]    │
├─────────────────────────────────────────────────────────────────────┤
│  ☐  ✗ HIGH   SEMANTIC_OVERLAP          2 tools affected             │
│     create_task ↔ create_jira_issue    similarity: 0.91             │
│     Detected 2h ago  ·  Assigned: unassigned  ·  2 recommendations  │
│     [View]  [Acknowledge]  [Assign to me]                           │
├─────────────────────────────────────────────────────────────────────┤
│  ☐  ✗ HIGH   SEMANTIC_OVERLAP          2 tools affected             │
│     send_email ↔ send_notification     similarity: 0.88             │
│     Detected 5h ago  ·  Assigned: Bob  ·  1 recommendation         │
│     [View]  [Acknowledge]  [Reassign]                               │
├─────────────────────────────────────────────────────────────────────┤
│  ☐  ⚠ MEDIUM  SCHEMA_COLLISION         2 tools affected             │
│     get_user ↔ get_user_profile        param: user_id type mismatch │
│     Detected 1 day ago  ·  Assigned: Alice  ·  1 recommendation     │
│     [View]  [Acknowledge]  [Suppress]                               │
└─────────────────────────────────────────────────────────────────────┘
```

**Conflict Detail** (on click):

```
┌─────────────────────────────────────────────────────────────────────┐
│  Conflict: SEMANTIC_OVERLAP  ✗ HIGH                             [×] │
├─────────────────────────────────────────────────────────────────────┤
│  Tools involved:                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  create_task (asana-mcp)          create_jira_issue (jira-mcp)│  │
│  │  "Creates a new task or work     "Creates a new issue in Jira │  │
│  │   item in the project management  for the specified project..." │
│  │   system..."                                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Evidence:                                                           │
│  Cosine similarity: 0.91  (threshold: 0.80)                        │
│  Routing split: 47% → create_task, 53% → create_jira_issue          │
│  Affected probe queries (12/50 changed routing):                    │
│    "Add a task for the new feature"  →  create_task (was: create_jira)│
│    "I need to create a work item"   →  create_jira  (was: create_task)│
│    ... 10 more                                                       │
│                                                                      │
│  ── Recommendations ──────────────────────────────────────────────  │
│  1.  DESCRIPTION_REWRITE for create_task                            │
│      Score after: 42  (was: 91)                                     │
│      Change description to explicitly scope to Asana:              │
│      Before: "Creates a new task or work item in..."               │
│      After:  "Creates a task in Asana project management. Use ONLY │
│               for Asana. Do not use for Jira, Linear, or GitHub."  │
│      [Accept + Apply]  [Accept (manual)]  [Reject]                 │
│                                                                      │
│  2.  SCOPE_NARROWING for create_jira_issue                          │
│      [Accept + Apply]  [Accept (manual)]  [Reject]                 │
│                                                                      │
│  ── Actions ──────────────────────────────────────────────────────  │
│  [Acknowledge]  [Suppress (requires approval)]  [Mark resolved]    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tool Registration Wizard

A guided UI for registering a new tool with real-time conflict checking.

```
Step 1: Define Tool
        ┌────────────────────────────────────────────┐
        │  Name:        [create_zendesk_ticket      ]│
        │  Description: [Creates a ticket in Zendesk │
        │                customer support platform...│
        │               ]                           │
        │  Server:      [zendesk-mcp ▼]              │
        │  Team:        [Support Engineering ▼]      │
        │  Schema:      [Paste JSON or use builder]  │
        │                                            │
        │                            [Next: Run Check→]│
        └────────────────────────────────────────────┘

Step 2: Running Check  (live progress)
        ✓  Stage 1: Lexical    (0ms)
        ✓  Stage 2: Schema     (12ms)
        ⟳  Stage 3: Semantic...

Step 3: Results
        ┌─────────────────────────────────────────┐
        │  ✓ PASSED  No blocking conflicts         │
        │                                         │
        │  Warnings:                              │
        │  ⚠ LOW  Similarity 0.74 with            │
        │         create_support_ticket           │
        │         (advisory — below threshold)    │
        │                                         │
        │  Impact: 0% routing shift               │
        │                                         │
        │            [← Back]  [Register Tool →]  │
        └─────────────────────────────────────────┘
```

---

## Audit Log

A filterable, searchable timeline of all state changes in the system.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Audit Log  [prod]   [Filter: all events ▼]  [From: 2025-05-01 ▼] │
├─────────────────────────────────────────────────────────────────────┤
│  2025-05-26 14:32   Alice   RECOMMENDATION_ACCEPTED                 │
│  create_jira_issue description updated (v3 → v4)  [View diff]      │
├─────────────────────────────────────────────────────────────────────┤
│  2025-05-26 12:15   CI/CD   TOOL_REGISTRATION_BLOCKED               │
│  create_task (asana-mcp)  HIGH conflict with create_jira_issue     │
│  run_id: run-abc  [View analysis]                                   │
├─────────────────────────────────────────────────────────────────────┤
│  2025-05-26 10:00   System  ANALYSIS_RUN_COMPLETED                 │
│  Full environment scan  47 tools  3 conflicts found  risk: 28.5    │
│  [View report]                                                      │
├─────────────────────────────────────────────────────────────────────┤
│  2025-05-25 16:44   Bob     CONFLICT_SUPPRESSED                     │
│  get_user ↔ get_user_profile  MEDIUM  "Same team owns both tools"  │
│  Approval: Alice (APPROVER)                                         │
└─────────────────────────────────────────────────────────────────────┘
```

**Event types logged:**
- `TOOL_REGISTERED`, `TOOL_UPDATED`, `TOOL_DEPRECATED`
- `CONFLICT_DETECTED`, `CONFLICT_RESOLVED`, `CONFLICT_SUPPRESSED`, `CONFLICT_ACKNOWLEDGED`
- `TOOL_REGISTRATION_BLOCKED`
- `RECOMMENDATION_ACCEPTED`, `RECOMMENDATION_REJECTED`
- `ANALYSIS_RUN_STARTED`, `ANALYSIS_RUN_COMPLETED`, `ANALYSIS_RUN_FAILED`
- `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_DENIED`

---

## Navigation Structure

```
/                          Dashboard Home (default env)
/environments/{id}         Environment-scoped home
/environments/{id}/tools   Tool Registry
/environments/{id}/map     Conflict Map
/environments/{id}/conflicts  Conflict Queue
/environments/{id}/runs/{run_id}  Analysis Run Detail
/environments/{id}/audit   Audit Log
/tools/register            Tool Registration Wizard
/settings                  Organization + environment configuration
/settings/api-keys         API key management
```

---

## Technology Stack (Frontend)

| Technology | Version | Purpose |
|---|---|---|
| React | 18+ | Component framework |
| TypeScript | 5+ | Type safety across codebase |
| Tailwind CSS | 3+ | Utility-first styling |
| D3.js | 7+ | Force-directed conflict map |
| React Query (TanStack) | 5+ | API data fetching, caching, real-time updates |
| React Router | 6+ | Client-side routing |
| Vite | 5+ | Build tooling |
| Vitest | — | Unit testing |
| Playwright | — | E2E testing |

---

## Development Setup

```bash
# From the project root
cd dashboard
npm install
npm run dev   # starts on http://localhost:3000

# The dashboard proxies /v1/* to localhost:8000 (API) in dev mode
```

`vite.config.ts` proxy:
```typescript
server: {
  proxy: {
    '/v1': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    }
  }
}
```

---

## Environment Variables (Frontend)

```bash
VITE_API_URL=https://api.mtgs.yourdomain.com
VITE_APP_ENV=production
```

In development, API calls are proxied via Vite — no `VITE_API_URL` needed.
