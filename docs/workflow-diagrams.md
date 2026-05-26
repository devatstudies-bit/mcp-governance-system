# MTGS — Workflow Diagrams

> Visual reference for every major flow in the MCP Tool Governance System.
> All diagrams are rendered as [Mermaid](https://mermaid.js.org/) — viewable in GitHub,
> GitLab, Notion, VS Code (Mermaid Preview extension), and the MkDocs site.

---

## 1. System Architecture — Component Overview

High-level map of every layer: clients → API → core engine → data stores.

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor":        "#6366f1",
    "primaryTextColor":    "#ffffff",
    "primaryBorderColor":  "#4f46e5",
    "lineColor":           "#94a3b8",
    "secondaryColor":      "#0ea5e9",
    "tertiaryColor":       "#f0fdf4",
    "background":          "#ffffff",
    "mainBkg":             "#6366f1",
    "nodeBorder":          "#4f46e5",
    "clusterBkg":          "#f8fafc",
    "titleColor":          "#1e293b",
    "edgeLabelBackground": "#f1f5f9"
  }
}}%%
flowchart TB
    classDef client    fill:#6366f1,stroke:#4f46e5,color:#fff,rx:8
    classDef api       fill:#0ea5e9,stroke:#0284c7,color:#fff,rx:8
    classDef core      fill:#10b981,stroke:#059669,color:#fff,rx:8
    classDef worker    fill:#f59e0b,stroke:#d97706,color:#fff,rx:8
    classDef store     fill:#8b5cf6,stroke:#7c3aed,color:#fff,rx:8
    classDef azure     fill:#0078d4,stroke:#005a9e,color:#fff,rx:8
    classDef alert     fill:#ef4444,stroke:#dc2626,color:#fff,rx:8

    subgraph CLIENTS["🖥️  Client Layer"]
        CLI["⌨️  CLI\nmtgs check / register"]
        GH["🔀  GitHub Actions\nCI/CD Webhook"]
        DASH["📊  Dashboard\nReact + D3.js"]
        IDE["🧩  IDE Extension"]
    end

    subgraph API["🌐  FastAPI Application  (port 8000)"]
        AUTH["🔐  Auth\nJWT + API Key + RBAC"]
        RT["📡  Routers\ntools · conflicts · approvals\nanalysis-runs · audit-logs\nwebhooks · health"]
        MW["🛡️  Middleware\nRequest-ID · Access Log · CORS"]
    end

    subgraph CORE["⚙️  Core Engine  (mtgs/core/)"]
        CDP["🔍  Conflict Detection\nPipeline  S1→S2→S3→S4"]
        SIM["📈  Impact Simulator\nRouting shift %"]
        REC["💡  Recommendation\nEngine  gpt-4o"]
        PRB["🎯  Probe Query\nGenerator"]
        ORC["🎼  Analysis\nOrchestrator"]
        APW["✅  Approval\nWorkflow"]
        AUD["📋  Audit Logger\nImmutable · CEF"]
        SYN["🔄  MCP Sync\nServer diff"]
        NOT["🔔  Notification\nRouter"]
        CB["⚡  Circuit\nBreakers"]
    end

    subgraph WORKERS["🔧  Celery Workers"]
        WA["📥  Analysis Queue"]
        WE["🧮  Embeddings Queue"]
        WB["⏰  Beat Scheduler\n15-min sync · hourly scan"]
    end

    subgraph STORES["🗄️  Data Stores"]
        PG["🐘  PostgreSQL 16\n10 ORM tables"]
        RD["⚡  Redis\nBroker + Cache"]
    end

    subgraph AZURE["☁️  Azure Services"]
        AOI["🤖  Azure OpenAI\ntext-embedding-3-large\ngpt-4o"]
        AIS["🔎  Azure AI Search\nHNSW · cosine · 3072-dim"]
    end

    subgraph NOTIFY["📣  Alert Channels"]
        SL["💬  Slack\nBlock Kit"]
        PD["🚨  PagerDuty\nEvents API v2"]
        EM["📧  Email\nSMTP"]
    end

    CLIENTS --> API
    API --> CORE
    CORE --> WORKERS
    WORKERS --> STORES
    WORKERS --> AZURE
    CORE --> STORES
    NOT --> NOTIFY
    CB -.->|"protects"| AZURE

    class CLI,GH,DASH,IDE client
    class AUTH,RT,MW api
    class CDP,SIM,REC,PRB,ORC,APW,AUD,SYN,NOT,CB core
    class WA,WE,WB worker
    class PG,RD store
    class AOI,AIS azure
    class SL,PD,EM alert
```

---

## 2. Tool Registration & Full Analysis Pipeline

End-to-end journey from a `POST /tools` request through all 4 detection stages,
simulation, recommendations, approval, and notification.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#6366f1", "lineColor": "#94a3b8", "edgeLabelBackground": "#f1f5f9"}}}%%
flowchart TD
    classDef start     fill:#6366f1,stroke:#4f46e5,color:#fff,font-weight:bold
    classDef stage1    fill:#3b82f6,stroke:#2563eb,color:#fff
    classDef stage2    fill:#0ea5e9,stroke:#0284c7,color:#fff
    classDef stage3    fill:#10b981,stroke:#059669,color:#fff
    classDef stage4    fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef decision  fill:#f59e0b,stroke:#d97706,color:#fff,shape:diamond
    classDef critical  fill:#ef4444,stroke:#dc2626,color:#fff,font-weight:bold
    classDef high      fill:#f97316,stroke:#ea580c,color:#fff
    classDef ok        fill:#22c55e,stroke:#16a34a,color:#fff,font-weight:bold
    classDef phase2    fill:#a855f7,stroke:#9333ea,color:#fff
    classDef action    fill:#64748b,stroke:#475569,color:#fff
    classDef notify    fill:#ec4899,stroke:#db2777,color:#fff

    REG(["🚀 Tool Registration\nPOST /v1/environments/:id/tools"])

    subgraph S1["🔵  Stage 1 · Lexical  &lt;1ms"]
        L1["Exact name match?"]
        L2["Levenshtein distance ≤ 2?"]
        L3["Jaccard token similarity ≥ 0.5?"]
    end

    subgraph S2["🔷  Stage 2 · Schema  &lt;1ms"]
        SC1["Type collision?\nsame param, different JSON type"]
        SC2["Required-field overlap ≥ 70%?"]
    end

    subgraph S3["🟢  Stage 3 · Semantic  ~50ms"]
        EM["Generate embedding\ntext-embedding-3-large"]
        ANN["ANN search\nAzure AI Search HNSW"]
        COS["Cosine similarity ≥ 0.80?"]
    end

    subgraph S4["🟣  Stage 4 · Behavioral  2–5s"]
        PQ["Generate probe queries\nProbeQueryGenerator"]
        BL["Baseline routing\nLLM picks tool — N trials"]
        CD["Candidate routing\nLLM picks from registry+candidate"]
        SH["Compute routing_shift_pct"]
    end

    subgraph REC_PHASE["💡  Recommendation Engine"]
        RB["Build conflict prompt"]
        GP["gpt-4o generates\nup to 3 recommendations\nRENAME · REWRITE · NARROW\nSCHEMA · DEPRECATE"]
    end

    PERSIST["💾 Persist conflicts\n+ analysis run to DB"]
    RISK["📊 Compute risk score\n0–100"]

    SEV_CHECK{"⚠️ Severity ≥ HIGH?"}

    APPR["✅ Create ApprovalRequest\nstatus: PENDING"]
    ACTIVE["🟢 Tool set ACTIVE"]

    NOT["🔔 NotificationRouter\nSlack · PagerDuty · Email"]
    AUD_ENT["📋 Write AuditEntry\nIMMUTABLE"]
    CI_PASS(["✅ CI Gate PASS\nHTTP 200"])
    CI_FAIL(["🚫 CI Gate FAIL\nHTTP 409 + recommendations"])

    REG --> S1
    L1 -->|"✅ exact match"| CRIT["🔴 CRITICAL\nEXACT_NAME"]
    L1 -->|"❌ no match"| L2
    L2 -->|"✅ close match"| MED["🟡 MEDIUM\nSIMILAR_NAME"]
    L2 -->|"❌"| L3
    L3 -->|"✅ overlap"| MED
    L3 -->|"❌ clean"| S2

    CRIT -->|"short-circuit\nskip S2–S4"| PERSIST
    MED --> S2

    SC1 -->|"✅ collision"| HIGH1["🟠 HIGH\nTYPE_COLLISION"]
    SC1 -->|"❌"| SC2
    SC2 -->|"✅ overlap"| HIGH1
    SC2 -->|"❌ clean"| S3

    HIGH1 --> PERSIST
    EM --> ANN --> COS
    COS -->|"✅ similar"| SEMOV["🟠 HIGH\nSEMANTIC_OVERLAP"]
    COS -->|"❌ distinct"| S4

    SEMOV --> S4
    PQ --> BL --> CD --> SH

    SH --> REC_PHASE
    RB --> GP

    GP --> PERSIST
    PERSIST --> RISK --> SEV_CHECK

    SEV_CHECK -->|"YES\nCRITICAL/HIGH"| APPR
    SEV_CHECK -->|"NO\nMEDIUM/LOW"| ACTIVE

    APPR --> NOT
    NOT --> AUD_ENT

    ACTIVE --> AUD_ENT
    AUD_ENT --> CI_PASS

    CRIT --> CI_FAIL
    HIGH1 --> CI_FAIL

    class REG start
    class L1,L2,L3 stage1
    class SC1,SC2 stage2
    class EM,ANN,COS stage3
    class PQ,BL,CD,SH stage4
    class RB,GP phase2
    class CRIT,CI_FAIL critical
    class HIGH1,SEMOV,APPR,NOT high
    class ACTIVE,CI_PASS ok
    class PERSIST,RISK,AUD_ENT action
```

---

## 3. Conflict Detection Pipeline — Stage Detail

A closer look at what each stage checks and how severity is assigned.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#1e293b", "lineColor": "#64748b"}}}%%
flowchart LR
    classDef s1  fill:#3b82f6,stroke:#1d4ed8,color:#fff,font-size:13px
    classDef s2  fill:#0ea5e9,stroke:#0369a1,color:#fff,font-size:13px
    classDef s3  fill:#10b981,stroke:#047857,color:#fff,font-size:13px
    classDef s4  fill:#8b5cf6,stroke:#6d28d9,color:#fff,font-size:13px
    classDef sev fill:#1e293b,stroke:#0f172a,color:#fff,font-size:11px
    classDef out fill:#f8fafc,stroke:#cbd5e1,color:#1e293b,font-size:12px

    subgraph STAGE1["Stage 1 — Lexical  🔵"]
        direction TB
        S1A["Exact name\ncomparison"]
        S1B["Levenshtein\ndistance"]
        S1C["Jaccard token\nsimilarity"]
        S1A -->|"match"| C1["🔴 CRITICAL\nEXACT_NAME"]
        S1B -->|"dist ≤ 2"| M1["🟡 MEDIUM\nSIMILAR_NAME"]
        S1C -->|"≥ 0.50"| M1
    end

    subgraph STAGE2["Stage 2 — Schema  🔷"]
        direction TB
        S2A["Parameter\ntype check"]
        S2B["Required fields\noverlap"]
        S2A -->|"collision"| H2["🟠 HIGH\nTYPE_COLLISION"]
        S2B -->|"Jaccard ≥ 0.70"| H2b["🟠 HIGH\nREQUIRED_OVERLAP"]
    end

    subgraph STAGE3["Stage 3 — Semantic  🟢"]
        direction TB
        S3A["Fingerprint text\nbuild"]
        S3B["text-embedding\n-3-large  3072D"]
        S3C["Azure AI Search\nHNSW ANN"]
        S3D["Cosine\nsimilarity"]
        S3A --> S3B --> S3C --> S3D
        S3D -->|"≥ 0.85\nthreshold"| H3["🟠 HIGH\nSEMANTIC_OVERLAP"]
    end

    subgraph STAGE4["Stage 4 — Behavioral  🟣"]
        direction TB
        S4A["Probe query\ngeneration\n(LLM)"]
        S4B["Baseline routing\nN trials majority\nvote"]
        S4C["Candidate routing\n+new tool in registry"]
        S4D["routing_shift_pct\n= changed / total × 100"]
        S4A --> S4B --> S4C --> S4D
        S4D -->|"shift > 20%"| H4["🟠 HIGH\nROUTING_INSTABILITY"]
    end

    STAGE1 -->|"no CRITICAL"| STAGE2
    STAGE2 -->|"no conflict"| STAGE3
    STAGE3 -->|"no conflict"| STAGE4
    C1 -.->|"⚡ short-circuit"| DONE["📊 Analysis\nComplete"]
    STAGE4 --> DONE

    class S1A,S1B,S1C s1
    class S2A,S2B s2
    class S3A,S3B,S3C,S3D s3
    class S4A,S4B,S4C,S4D s4
```

---

## 4. Impact Simulation — Routing Shift Measurement

How MTGS quantifies the blast radius of adding a new tool.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#8b5cf6", "lineColor": "#94a3b8"}}}%%
sequenceDiagram
    participant ORC  as 🎼 Orchestrator
    participant PRB  as 🎯 ProbeGenerator
    participant LLM  as 🤖 gpt-4o
    participant SIM  as 📈 ImpactSimulator
    participant CB   as ⚡ CircuitBreaker

    Note over ORC,CB: Phase A — Generate Probe Queries

    ORC->>PRB: generate_for_tool(candidate, count=10)
    PRB->>CB:  call(LLM.complete_json)
    CB-->>LLM: ✅ CLOSED — allow
    LLM-->>PRB: ["Run a SQL query", "Fetch data from warehouse", ...]
    PRB-->>ORC: 10 probe queries

    ORC->>PRB: generate_adversarial(candidate, conflicting_tool, count=5)
    PRB->>CB:  call(LLM.complete_json)
    CB-->>LLM: ✅ allow
    LLM-->>PRB: ["Pull data for my report", "Get me the numbers", ...]
    PRB-->>ORC: 5 adversarial queries  (15 total)

    Note over ORC,CB: Phase B — Baseline Routing  (existing tools only)

    loop For each probe × 3 trials
        SIM->>CB:  call(LLM.complete)
        CB-->>LLM: ✅ allow
        LLM-->>SIM: "query_database"
    end
    SIM-->>ORC: baseline_routing = {query → Counter}

    Note over ORC,CB: Phase C — Candidate Routing  (existing + new tool)

    loop For each probe × 3 trials
        SIM->>CB:  call(LLM.complete)
        CB-->>LLM: ✅ allow
        LLM-->>SIM: "new_db_tool"  ← routing changed!
    end
    SIM-->>ORC: candidate_routing = {query → Counter}

    Note over ORC,CB: Phase D — Compute routing_shift_pct

    ORC->>SIM: compare(baseline, candidate)
    SIM-->>ORC: ImpactReport(routing_shift_pct=40%, at_risk_tools=["query_database"])

    Note over ORC: routing_shift_pct = 6/15 × 100 = 40%  🔴 HIGH IMPACT
```

---

## 5. Approval Workflow — State Machine

How CRITICAL/HIGH conflicts are gated through human review.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#f59e0b", "lineColor": "#94a3b8"}}}%%
stateDiagram-v2
    direction LR

    [*] --> PENDING : Conflict detected\n(CRITICAL or HIGH)\n+ ApprovalRequest created

    state PENDING {
        [*] --> Waiting
        Waiting --> Waiting : time passes\n(TTL: 7 days)
        note right of Waiting
            🔔 Slack / PagerDuty / Email
            alert sent to reviewer+
        end note
    }

    PENDING --> APPROVED  : reviewer+ calls\nPATCH /approvals/{id}/decide\n{ decision: "approve" }
    PENDING --> REJECTED  : reviewer+ calls\nPATCH /approvals/{id}/decide\n{ decision: "reject" }
    PENDING --> EXPIRED   : TTL elapsed\nwithout decision

    APPROVED --> [*]  : Tool set ACTIVE\n📋 AuditEntry written\nAuditAction.APPROVAL_APPROVED

    REJECTED --> [*]  : Tool stays BLOCKED\n📋 AuditEntry written\nAuditAction.APPROVAL_REJECTED

    EXPIRED  --> [*]  : Tool stays BLOCKED\n📋 AuditEntry written\nAuditAction.APPROVAL_REJECTED

    note right of APPROVED
        Risk score recalculated
        Celery analysis re-queued
        Notification: "Tool approved"
    end note

    note right of REJECTED
        Recommendations surfaced
        Developer notified
        Conflict status → REJECTED
    end note
```

---

## 6. RBAC — Role Hierarchy & Permissions

Who can do what across every API surface.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#0ea5e9", "lineColor": "#94a3b8"}}}%%
flowchart TD
    classDef role   fill:#0ea5e9,stroke:#0284c7,color:#fff,font-weight:bold
    classDef perm   fill:#f0fdf4,stroke:#86efac,color:#166534,font-size:12px
    classDef denied fill:#fef2f2,stroke:#fca5a5,color:#991b1b,font-size:12px

    V["👁️  viewer"]
    D["👨‍💻  developer"]
    R["🔍  reviewer"]
    A["👑  admin"]
    CI["🤖  ci-agent"]

    V -->|"inherits"| D
    D -->|"inherits"| R
    R -->|"inherits"| A

    subgraph VP["Viewer permissions"]
        VP1["GET /health · /readiness"]
        VP2["GET /tools · /conflicts"]
        VP3["GET /analysis-runs · /audit-logs"]
        VP4["GET /approvals · /audit-logs/actions"]
        VP5["GET /environments/:id/health"]
    end

    subgraph DP["+ Developer permissions"]
        DP1["POST /tools  (register)"]
        DP2["POST /tools/check  (dry-run)"]
        DP3["POST /analysis-runs  (trigger)"]
        DP4["POST /approvals  (create request)"]
    end

    subgraph RP["+ Reviewer permissions"]
        RP1["PATCH /approvals/:id/decide"]
        RP2["PATCH /conflicts/:id  (update status)"]
        RP3["GET /audit-logs/export  (SIEM download)"]
    end

    subgraph AP["+ Admin permissions"]
        AP1["DELETE /tools/:id"]
        AP2["PATCH /environments/:id/policy"]
        AP3["POST /api-keys  (revoke)"]
    end

    subgraph CIP["CI-agent permissions"]
        CI1["POST /webhooks/ci-check"]
        CI2["Uses X-API-Key header\n(not Bearer JWT)"]
    end

    V --> VP
    D --> DP
    R --> RP
    A --> AP
    CI --> CIP

    class V,D,R,A,CI role
    class VP1,VP2,VP3,VP4,VP5,DP1,DP2,DP3,DP4,RP1,RP2,RP3,AP1,AP2,AP3,CI1,CI2 perm
```

---

## 7. Audit Log & SIEM Export Flow

How every governance action becomes an immutable, SIEM-ready audit entry.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#64748b", "lineColor": "#94a3b8"}}}%%
flowchart LR
    classDef event   fill:#6366f1,stroke:#4f46e5,color:#fff
    classDef logger  fill:#0ea5e9,stroke:#0284c7,color:#fff
    classDef entry   fill:#10b981,stroke:#059669,color:#fff
    classDef export  fill:#f59e0b,stroke:#d97706,color:#fff
    classDef siem    fill:#ec4899,stroke:#db2777,color:#fff

    subgraph EVENTS["🔵  Governance Events (13 types)"]
        E1["TOOL_REGISTERED"]
        E2["CONFLICT_DETECTED"]
        E3["APPROVAL_APPROVED"]
        E4["APPROVAL_REJECTED"]
        E5["ANALYSIS_RUN_COMPLETED"]
        E6["API_KEY_CREATED"]
        E7["... 7 more"]
    end

    AUD["🔐  AuditLogger\nawait logger.record(action, actor_id,\n  resource_id, resource_type,\n  environment_id, metadata)"]

    ENTRY["📋  AuditEntry\nfrozen=True 🔒\nentry_id · action · actor_id\nresource_id · timestamp\nmetadata: dict"]

    DB["🐘  PostgreSQL\nappend-only table"]

    subgraph API_LAYER["📡  GET /v1/api/audit-logs/"]
        FILT["Filter by:\naction · actor · resource\nenvironment · date range"]
        PAGE["Paginate\n(newest-first)"]
    end

    subgraph EXPORT["📤  GET /audit-logs/export  (reviewer+)"]
        JSON["format=json\n→ list[dict]\nContent-Disposition: attachment"]
        CEF["format=cef\n→ CEF string per line\n\nCEF:0|MTGS|MCPToolGovernance|1.0\n|CONFLICT_DETECTED|...|8|..."]
    end

    subgraph SIEM_TARGETS["🚨  SIEM Platforms"]
        SP["Splunk"]
        MS["Microsoft Sentinel"]
        QR["IBM QRadar"]
        EL["Elastic SIEM"]
    end

    EVENTS --> AUD
    AUD --> ENTRY
    ENTRY --> DB
    DB --> API_LAYER
    API_LAYER --> FILT --> PAGE
    PAGE --> EXPORT
    EXPORT --> JSON
    EXPORT --> CEF
    CEF --> SIEM_TARGETS

    class E1,E2,E3,E4,E5,E6,E7 event
    class AUD logger
    class ENTRY,DB entry
    class JSON,CEF export
    class SP,MS,QR,EL siem
```

---

## 8. Circuit Breaker — State Machine

How MTGS protects itself when Azure OpenAI, Azure AI Search, or webhooks degrade.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#22c55e", "lineColor": "#94a3b8"}}}%%
stateDiagram-v2
    direction LR

    [*]      --> CLOSED

    state CLOSED {
        [*]      --> Healthy
        Healthy  --> Healthy : ✅ call succeeds\nfailure_count reset to 0
        Healthy  --> Counting : ❌ call fails\nfailure_count++
        Counting --> Counting : ❌ another failure\nfailure_count < threshold
    }

    CLOSED   --> OPEN      : ❌ failure_count\n≥ threshold (default: 5)

    state OPEN {
        [*]      --> FailFast
        FailFast --> FailFast : 🚫 all calls rejected instantly\nraises CircuitOpenError\nstats.rejected++
        note right of FailFast
            recovery_timeout: 30s (Azure)
            60s (MCP sync)
            120s (notifications)
        end note
    }

    OPEN     --> HALF_OPEN  : ⏰ recovery_timeout elapsed

    state HALF_OPEN {
        [*]      --> Probe
        Probe    --> Probe : waiting for one real call
        note right of Probe
            Only 1 probe call allowed.
            All others still fail-fast.
        end note
    }

    HALF_OPEN --> CLOSED  : ✅ probe call succeeds\ncircuit healed
    HALF_OPEN --> OPEN    : ❌ probe call fails\nback to fail-fast

    note right of CLOSED
        4 named singletons:
        • azure-openai (threshold: 5)
        • azure-search (threshold: 5)
        • mcp-sync     (threshold: 3)
        • notifications (threshold: 3)
    end note
```

---

## 9. CI/CD Integration Flow

How MTGS acts as a governance gate inside GitHub Actions (or any CI pipeline).

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#1e293b", "lineColor": "#64748b"}}}%%
sequenceDiagram
    participant DEV  as 👨‍💻 Developer
    participant GH   as 🔀 GitHub Actions
    participant MTGS as 🛡️ MTGS Webhook
    participant CDP  as 🔍 Conflict Pipeline
    participant DB   as 🐘 PostgreSQL
    participant SL   as 💬 Slack

    DEV->>GH: git push / pull request

    GH->>GH: Build & lint pass ✅

    Note over GH,MTGS: Governance Gate Step

    GH->>MTGS: POST /v1/webhooks/ci-check\nHeaders: X-API-Key, X-Environment\nBody: { tool definition JSON }

    MTGS->>MTGS: Authenticate CI agent\nResolve environment policy

    MTGS->>CDP: run_sync(candidate, existing_tools)
    CDP-->>MTGS: PipelineResult\n(conflicts, has_critical, highest_severity)

    alt No conflicts  OR  severity < policy threshold
        MTGS-->>GH: HTTP 200 ✅\n{ "status": "pass", "conflicts": 0 }
        GH->>GH: ✅ Step passes → merge allowed
    else Conflicts at or above threshold
        MTGS->>DB: Persist conflicts + recommendations
        MTGS->>SL: 🚨 Slack alert fired
        MTGS-->>GH: HTTP 409 🚫\n{ "status": "blocked",\n  "conflicts": [...],\n  "recommendations": [...] }
        GH->>GH: ❌ Step fails → merge blocked
        GH-->>DEV: PR blocked — review MTGS report
    end
```

---

## 10. MCP Server Sync — Periodic Drift Detection

How Celery beat keeps the database in sync with live MCP servers.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#f59e0b", "lineColor": "#94a3b8"}}}%%
flowchart TD
    classDef beat    fill:#f59e0b,stroke:#d97706,color:#fff,font-weight:bold
    classDef task    fill:#0ea5e9,stroke:#0284c7,color:#fff
    classDef diff    fill:#8b5cf6,stroke:#7c3aed,color:#fff
    classDef result  fill:#10b981,stroke:#059669,color:#fff
    classDef warn    fill:#ef4444,stroke:#dc2626,color:#fff

    BEAT(["⏰ Celery Beat\nEvery 15 minutes"])

    ENUM["sync_all_mcp_servers_task\nenumerate all active MCPServer rows"]

    subgraph FAN["Fan-out: one task per server"]
        T1["sync_mcp_server_task\nserver_id=A"]
        T2["sync_mcp_server_task\nserver_id=B"]
        T3["sync_mcp_server_task\nserver_id=..."]
    end

    subgraph SYNC_TASK["Per-server sync flow"]
        HTTP["POST {server.base_url}/tools/list\nMCP JSON-RPC 2.0"]
        LOAD["Load DB tools\nfor this server"]
        DIFF["MCPServerSyncService.diff()\nremote vs DB"]
    end

    subgraph REPORT["SyncReport"]
        ADDED["added [ ]\nnew tools on remote"]
        REMOVED["removed [ ]\ngone from remote"]
        UPDATED["updated [ ]\ndescription changed"]
        UNCHANGED["unchanged [ ]\nno change"]
    end

    subgraph ACTIONS["Actions on changes"]
        QA["Queue conflict analysis\nfor each ADDED tool"]
        QU["Queue conflict analysis\nfor each UPDATED tool"]
        LOG["Log REMOVED tools\nfor admin review"]
        AUD["Write AuditEntry\nTOOL_REGISTERED / TOOL_UPDATED"]
    end

    HOURLY(["⏰ Celery Beat\nEvery 60 minutes"])
    SCAN["scheduled_conflict_scan_task\nRe-scan ALL active tools\nacross ALL environments"]

    BEAT --> ENUM --> FAN
    T1 & T2 & T3 --> SYNC_TASK
    HTTP --> LOAD --> DIFF --> REPORT
    ADDED --> QA --> AUD
    UPDATED --> QU --> AUD
    REMOVED --> LOG

    HOURLY --> SCAN

    class BEAT,HOURLY beat
    class ENUM,T1,T2,T3,HTTP,LOAD,DIFF task
    class ADDED,REMOVED,UPDATED,UNCHANGED diff
    class QA,QU,LOG,AUD result
```

---

## 11. Recommendation Engine — From Conflict to Fix

How gpt-4o turns a conflict report into actionable tool improvements.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#a855f7", "lineColor": "#94a3b8"}}}%%
flowchart LR
    classDef input   fill:#6366f1,stroke:#4f46e5,color:#fff
    classDef build   fill:#0ea5e9,stroke:#0284c7,color:#fff
    classDef llm     fill:#a855f7,stroke:#9333ea,color:#fff
    classDef parse   fill:#10b981,stroke:#059669,color:#fff
    classDef output  fill:#f59e0b,stroke:#d97706,color:#1e293b

    subgraph INPUT["📥  Input"]
        CF["Conflict dict\ntype · severity · evidence"]
        TOOLS["ToolDef list\n(candidate + conflicting)"]
    end

    subgraph PROMPT["📝  Prompt Builder\n_build_prompt()"]
        P1["Conflict type\n+ severity header"]
        P2["Tool names\n+ descriptions"]
        P3["Evidence JSON\n(cosine_similarity, etc.)"]
        P4["JSON schema\nfor response format"]
    end

    LLM["🤖  gpt-4o\ncomplete_json()\ntemp=0.0"]

    subgraph PARSE["🔍  Response Parser\n_parse_recommendations()"]
        VAL["Validate\nrecommendation_type\nmust be in closed set"]
        FILT["Filter malformed\nor incomplete items"]
    end

    subgraph OUTPUT["💡  Recommendations (up to 3)"]
        R1["RENAME\ntarget_tool: create_task\nbefore: create_task\nafter: create_jira_task\npredicted_improvement: 95%"]
        R2["SCOPE_NARROWING\ntarget_tool: create_task\nfield: description\nbefore: Creates a task...\nafter: Creates a Jira task only...\npredicted_improvement: 45%"]
        R3["DESCRIPTION_REWRITE\n..."]
    end

    ERR["⚠️  On any error\nreturn []  — never raises"]

    INPUT --> PROMPT
    P1 & P2 & P3 & P4 --> LLM
    LLM --> PARSE
    PARSE --> VAL --> FILT --> OUTPUT
    LLM -.->|"exception"| ERR

    class CF,TOOLS input
    class P1,P2,P3,P4 build
    class LLM llm
    class VAL,FILT parse
    class R1,R2,R3 output
    class ERR output
```

---

> **Tip:** Install the [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
> VS Code extension to render all diagrams inline while editing this file.
