# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the MCP Tool Governance System. Each ADR documents a significant architectural decision: the context it was made in, the options considered, the decision reached, and its consequences.

ADRs are **immutable once accepted** — if a decision changes, a new ADR is written that supersedes the old one. This preserves the full reasoning history.

---

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [ADR-001](ADR-001-python-fastapi-stack.md) | Python + FastAPI as the API framework | Accepted | 2025-05 |
| [ADR-002](ADR-002-azure-openai-embeddings.md) | Azure OpenAI for embeddings (text-embedding-3-large) | Accepted | 2025-05 |
| [ADR-003](ADR-003-azure-ai-search-for-ann.md) | Azure AI Search for ANN vector search (over pgvector) | Accepted | 2025-05 |
| [ADR-004](ADR-004-celery-redis-async-workers.md) | Celery + Redis for async job processing | Accepted | 2025-05 |
| [ADR-005](ADR-005-recommendation-only-no-auto-apply.md) | Recommendations only — no automatic tool definition changes | Accepted | 2025-05 |
| [ADR-006](ADR-006-english-only-v1.md) | English-only tool descriptions for v1 | Accepted | 2025-05 |
| [ADR-007](ADR-007-weighted-linear-conflict-score.md) | Weighted-linear conflict scoring formula for v1 | Accepted | 2025-05 |
| [ADR-008](ADR-008-react-typescript-dashboard.md) | React + TypeScript + Tailwind for the governance dashboard | Accepted | 2025-05 |
| [ADR-009](ADR-009-claude-for-simulation-and-recommendations.md) | Claude Sonnet for routing simulation and recommendation generation | Accepted | 2025-05 |
| [ADR-010](ADR-010-manual-import-v1.md) | Manual import + JSON upload for v1 MCP server sync | Accepted | 2025-05 |
| [ADR-011](ADR-011-critical-suppression-approval.md) | CRITICAL conflict suppressions require explicit approver sign-off | Accepted | 2025-05 |

---

## ADR Format

Each ADR follows this structure:

```markdown
# ADR-NNN: Title

**Status:** Accepted | Superseded by ADR-XXX | Deprecated
**Date:** YYYY-MM
**Deciders:** [roles or team names]

## Context
What situation or problem prompted this decision?

## Decision Drivers
What forces shaped the decision?

## Options Considered
What alternatives were evaluated?

## Decision
What was decided?

## Consequences
What does this change? What becomes easier? What becomes harder?

## Alternatives Not Chosen
Why were other options ruled out?
```
