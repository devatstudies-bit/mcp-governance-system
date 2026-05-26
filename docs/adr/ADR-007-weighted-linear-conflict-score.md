# ADR-007: Weighted-Linear Conflict Scoring Formula for v1

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team  
**PRD Reference:** Open Question #4

---

## Context

Every detected conflict needs a numeric `conflict_score` (0–100) and a composite `risk_score` (0–100) for the overall analysis run. These scores drive:
- Severity classification (CRITICAL/HIGH/MEDIUM/LOW)
- CI/CD gate pass/fail decisions
- Dashboard health score
- Notification thresholds
- Priority ordering in the conflict queue

The question is how to compute these scores.

---

## Decision Drivers

- **Transparency:** Governance teams need to explain to stakeholders why a tool was blocked or flagged. "The LLM judged it risky" is not an acceptable explanation in a compliance-sensitive enterprise.
- **Debuggability:** Engineers need to understand what changed in a score when they update a tool definition. A formula with clear inputs is easier to reason about than a model.
- **Stability:** The score should be consistent across runs with the same inputs. Learned models can drift as training data changes.
- **v1 timeline:** Training an ML model requires labeled conflict data, which doesn't exist yet. Linear scoring can be implemented and validated immediately.

---

## Options Considered

### Option A: Weighted linear formula

Explicit formula with known coefficients:
```
conflict_score = w1 × similarity_score + w2 × routing_split + w3 × schema_mismatch_count
```

**Pros:** Transparent, explainable, deterministic, debuggable, no training data needed  
**Cons:** Coefficients are hand-tuned; may not capture non-linear interactions

### Option B: ML-trained classifier

Train a model on labeled (conflict, severity) pairs.

**Pros:** Can capture non-linear interactions, may generalize better  
**Cons:** Requires labeled training data (doesn't exist at v1), black-box, drift risk, added MLOps complexity

### Option C: LLM-judged scoring

Ask Claude to score conflicts: "On a scale of 0–100, how severe is this conflict?"

**Pros:** Can use reasoning and context  
**Cons:** Non-deterministic, costly (LLM call per conflict), hard to explain to governance teams, violates idempotency requirement

---

## Decision

**Weighted linear formula for v1.** All coefficients are explicitly defined in code and documented.

### Conflict Score (per-pair, 0–100)

| Signal | Formula | Max Contribution |
|---|---|---|
| Cosine similarity | `similarity × 100` | 100 (Stage 3 hit) |
| Exact name match | +100 (overrides all) | 100 |
| Edit distance | `max(0, 100 - distance × 30)` | 100 (distance=0) |
| Token overlap (Jaccard) | `jaccard × 80` | 80 |
| Schema type collision | +25 per colliding param | 75 (3+ params) |
| Routing ambiguity | `split_pct × 100` | 100 (50/50 split) |

### Risk Score (per analysis run, 0–100)

```python
base = Σ severity_weight(conflict)    # capped at 60
       { CRITICAL: 40, HIGH: 20, MEDIUM: 10, LOW: 5 }
simulation_component = routing_shift_pct × 0.4   # max 40
risk_score = min(base + simulation_component, 100)
```

### Severity Mapping

| Score | Severity |
|---|---|
| = 100 (exact name) | CRITICAL |
| ≥ 80 | HIGH |
| 60–80 | MEDIUM |
| 40–60 | LOW |
| < 40 | INFO |

---

## Consequences

**Positive:**
- Every score is fully explainable: "similarity was 0.91 → score 91 → HIGH"
- Governance teams can audit scoring logic without ML expertise
- Deterministic: same inputs always produce the same score
- Coefficients can be tuned via configuration without retraining

**Negative:**
- Hand-tuned coefficients may not perfectly capture severity in edge cases
- Doesn't capture interaction effects (e.g., low similarity + high routing split = possibly more severe than either alone)
- Will require recalibration once real-world conflict data is available

**Path to ML scoring (Phase 4):**
Once production data accumulates (real conflicts with human-assigned severities from the approval workflow), this formula will be used as the feature engineering baseline for an ML-trained severity classifier. The linear formula provides the labeled ground truth for training.
