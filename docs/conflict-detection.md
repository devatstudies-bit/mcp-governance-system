# Conflict Detection

This document is a deep dive into MTGS's 4-stage conflict detection pipeline — what it detects, how it scores conflicts, and the design reasoning behind each stage.

---

## Overview

The pipeline is designed around two principles:

1. **Cost-ordered execution** — Cheap stages run first; expensive LLM calls only run when cheaper signals indicate a problem.
2. **Additive evidence** — Each stage adds evidence to conflicts found by previous stages. A CRITICAL from Stage 1 escalates severity; behavioral evidence from Stage 4 refines the final score.

```
Input: candidate ToolDef + existing[] ToolDef
           │
     ┌─────▼──────────────────────────────────────┐
     │  Stage 1: Lexical Analysis          < 100ms │
     │  Hash lookup, edit distance, token overlap  │
     └─────┬──────────────────────────────────────┘
           │  Any CRITICAL? → short-circuit (skip Stage 3)
     ┌─────▼──────────────────────────────────────┐
     │  Stage 2: Schema Analysis           < 200ms │
     │  Parameter name intersections, type checks  │
     └─────┬──────────────────────────────────────┘
           │  No embedding service? → skip Stage 3
     ┌─────▼──────────────────────────────────────┐
     │  Stage 3: Semantic Analysis         1–3s    │
     │  Embedding cosine similarity via ANN        │
     └─────┬──────────────────────────────────────┘
           │  No Stage 3 hits? → skip Stage 4
     ┌─────▼──────────────────────────────────────┐
     │  Stage 4: Behavioral Simulation     10–60s  │
     │  LLM routing tests with probe queries       │
     └─────┬──────────────────────────────────────┘
           │
    PipelineResult { conflicts[], stages_executed[], duration_ms }
```

---

## Stage 1 — Lexical Analysis

**File:** `mtgs/core/conflict_detection/lexical.py`  
**Target latency:** < 100ms  
**Conflict types produced:** `EXACT_NAME`, `SIMILAR_NAME`

### 1.1 Exact Name Match

```python
existing_names = {t.name for t in existing}
if candidate.name in existing_names:
    → EXACT_NAME, severity=CRITICAL
```

Hash set lookup — O(1) regardless of registry size. The `same_server_ok` parameter allows tools on the same server to share names (update scenario).

**Why CRITICAL?** When two tools have the exact same name on different servers, the LLM has no disambiguation signal at all. Selection is effectively random. This is categorically different from semantic overlap.

### 1.2 Edit Distance (Levenshtein)

Uses `rapidfuzz.distance.Levenshtein.distance()` for fast computation.

```
Levenshtein(candidate.name, existing.name) ≤ 2 → SIMILAR_NAME, severity=MEDIUM
```

Examples that trigger this:
- `create_task` vs `create_tasks` (distance=1)
- `send_message` vs `send_messages` (distance=1)
- `get_user` vs `get_users` (distance=1)
- `update_ticket` vs `update_ticked` (distance=1, typo)

### 1.3 Token Overlap (Jaccard Similarity)

Tokenizes names by splitting on `_`, `-`, and whitespace:

```
"create_jira_task" → {"create", "jira", "task"}
"create_task_jira" → {"create", "task", "jira"}
Jaccard = |intersection| / |union| = 3/3 = 1.0 → SIMILAR_NAME, severity=MEDIUM
```

Catches reorderings and semantic-equivalent names that edit distance misses.

**Conflict score mapping (Stage 1):**
```
EXACT_NAME  → score=100,  severity=CRITICAL
SIMILAR_NAME (edit distance=1) → score=80, severity=MEDIUM
SIMILAR_NAME (jaccard ≥ 0.8)   → score=70, severity=MEDIUM
```

---

## Stage 2 — Schema Analysis

**File:** `mtgs/core/conflict_detection/schema_analysis.py`  
**Target latency:** < 200ms  
**Conflict types produced:** `SCHEMA_COLLISION`

### What it checks

For every shared parameter name between the candidate and each existing tool:

1. **Type conflict** — same param name, different JSON Schema types
   ```
   create_task.user_id: integer  vs  send_message.user_id: string
   → SCHEMA_COLLISION, severity=HIGH
   ```

2. **Description mismatch** — same param name + type, but semantically different descriptions
   ```
   create_task.priority: "1=low, 5=high"  vs  update_ticket.priority: "low|medium|high"
   → SCHEMA_COLLISION, severity=MEDIUM
   ```

3. **Required field clash** — one tool requires a param the other treats as optional with different semantics

### Why this matters

An LLM might route correctly to a tool but then hallucinate parameter values based on the wrong tool's schema, causing silent data corruption. This is especially dangerous for fields like `user_id`, `project_id`, `status` which appear across many tools.

**Conflict score mapping (Stage 2):**
```
Type conflict       → score=75, severity=HIGH
Description mismatch → score=50, severity=MEDIUM
```

---

## Stage 3 — Semantic Analysis

**File:** `mtgs/core/conflict_detection/pipeline.py` (`_run_semantic_stage`)  
**Target latency:** 1–3 seconds  
**Conflict types produced:** `SEMANTIC_OVERLAP`

### Embedding Strategy

`ToolFingerprinter.build_fingerprint_text()` creates a structured composite:

```
Tool name: create_salesforce_task
Purpose: Creates a new task record in Salesforce CRM for the specified contact.
Parameters accepted: contact_id (string): Salesforce Contact ID, due_date (string): ISO8601 date, priority (string): high|medium|low
Server context: salesforce-mcp
```

**Why composite and not just description?**

Consider:
- `create_jira_issue`: "Creates an issue in the project management system. Use for bug tracking."
  Params: `project_key`, `summary`, `issue_type`
- `create_linear_task`: "Creates a task in the project management system."
  Params: `team_id`, `title`, `state_id`

Description-only embeddings would flag these as HIGH similarity. But the parameter sets are completely different — an LLM that sees both tools has enough signal to distinguish them from params alone. The composite embedding captures this.

### ANN Search via Azure AI Search

Rather than computing cosine similarity against all tools O(N), MTGS uses Approximate Nearest Neighbor search:

```python
nearest = await azure_search_client.search_nearest(
    embedding=candidate_embedding,
    top_k=20
)
```

Top-20 is enough to catch any meaningful conflicts. Beyond K=20, the similarity drops below our threshold.

### Threshold and Severity

| Cosine Similarity | Severity | Meaning |
|---|---|---|
| ≥ 0.90 | HIGH | Near-identical semantic intent — LLM routing is unreliable |
| 0.80–0.90 | MEDIUM | Significant overlap — routing errors are likely in ambiguous phrasing |
| 0.70–0.80 | LOW (advisory) | Noticeable overlap — worth monitoring, may not cause routing errors |
| < 0.70 | (no conflict) | Tools are semantically distinct |

The default threshold is `0.80` (configurable via `DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD`).

**Short-circuit:** If Stage 1 found a CRITICAL (exact name match), Stage 3 is skipped. The routing problem is already definitively unacceptable; the embedding call would waste money and latency confirming what we already know.

---

## Stage 4 — Behavioral Simulation

**File:** `mtgs/core/simulation/impact_simulator.py`  
**Target latency:** 10–60s  
**Conflict types produced:** `INTENT_AMBIGUITY`

Stage 4 runs only for tool pairs flagged by Stage 3, keeping overall cost manageable.

### The Simulation Loop

```python
for query in probe_queries:
    for trial in range(trials):  # default: 3 trials
        selected_tool = await llm_tool_select(all_tools, query)
        routing_counter[selected_tool] += 1

routing_split = routing_counter[tool_a] / total_trials
```

### LLM Prompt Design

```
You are an AI assistant with access to the following tools.
Given the user's request, respond ONLY with the name of the single best tool.
Do not call the tool. Do not explain. Output only the tool name.

Available tools:
{tool_definitions_formatted}

User request: {probe_query}
Best tool name:
```

The prompt is deliberately minimal. It isolates the routing signal from explanation noise and gives reproducible results. Temperature is set to `0.0` (configurable) for maximum stability.

### Probe Query Sources

The simulation uses probe queries from three sources:

1. **Auto-generated** — `ProbeQueryGenerator` calls Claude to generate 10 diverse queries per tool, varying formality, specificity, and phrasing. It also generates **adversarial** queries that are maximally ambiguous between two conflicting tools.

2. **Manual** — Team members add known "golden" queries via the dashboard or API.

3. **Production log import** — Real user queries that previously routed to specific tools (imported via `POST /environments/{id}/probe-queries`).

### Routing Shift Calculation

```python
# For each probe query, compare baseline routing vs candidate routing
baseline_winner  = most_common(baseline_routing_counter[query_id])
candidate_winner = most_common(candidate_routing_counter[query_id])

changed = baseline_winner != candidate_winner

routing_shift_pct = changed_queries / total_queries × 100
```

**At-risk tools:** Any tool whose routing share (fraction of queries it wins) drops by > 10% after the candidate is added.

### Final Conflict Score

The composite `risk_score` (0–100) combines conflict severity with routing shift:

```
base = Σ severity_weight(conflict)  [capped at 60]
     where: CRITICAL=40, HIGH=20, MEDIUM=10, LOW=5

simulation_component = routing_shift_pct × 0.4  [max 40]

risk_score = min(base + simulation_component, 100)
```

---

## Conflict Types Reference

| Type | Stage | Description | Default Severity |
|---|---|---|---|
| `EXACT_NAME` | 1 | Two tools share an identical name across different servers | CRITICAL |
| `SIMILAR_NAME` | 1 | Names have edit distance ≤ 2 or high Jaccard token overlap | MEDIUM |
| `SCHEMA_COLLISION` | 2 | Shared parameter name with type or semantic mismatch | HIGH / MEDIUM |
| `SEMANTIC_OVERLAP` | 3 | Embedding cosine similarity ≥ 0.80 | HIGH / MEDIUM |
| `INTENT_AMBIGUITY` | 4 | LLM routing split > 30% between two tools for same probe queries | HIGH |
| `SCOPE_BLEED` | 4 | Tool A's description matches probe queries clearly intended for Tool B | MEDIUM |
| `SUPERSEDED` | 4 | New tool's description fully subsumes an older tool's scope | MEDIUM |

---

## Severity Levels

| Severity | CI Behavior | Dashboard Color | Example Trigger |
|---|---|---|---|
| CRITICAL | Always blocks by default | 🔴 Red | Exact name collision across servers |
| HIGH | Blocks by default (configurable) | 🟠 Orange | Semantic similarity ≥ 0.90, or routing ambiguity > 40% |
| MEDIUM | Warning, does not block by default | 🟡 Yellow | Similarity 0.80–0.90, similar names, schema collision |
| LOW | Info only | 🔵 Blue | Similarity 0.70–0.80, minor description similarity |
| INFO | Info only | ⚪ Gray | Advisory, no routing risk |

The CI blocking threshold is configurable: `CI_FAIL_ON_SEVERITY=HIGH` (default). Set to `CRITICAL` to only block on the most severe issues.

---

## Idempotency

The pipeline is fully idempotent: running the same inputs always produces the same output. This is important for the audit trail and for debugging.

- Stages 1 and 2 are deterministic by design.
- Stage 3 uses deterministic ANN (same index, same vector → same results).
- Stage 4 uses `temperature=0.0` by default, making LLM routing calls stable. The `trials=3` majority vote further smooths any residual non-determinism.

The `analysis_runs.tool_set_snapshot` column stores the exact tool set used at run time, so any run can be replayed weeks later and compared.
