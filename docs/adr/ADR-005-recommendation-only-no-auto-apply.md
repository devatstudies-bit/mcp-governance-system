# ADR-005: Recommendations Only — No Automatic Tool Definition Changes

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team  
**PRD Reference:** Open Question #3

---

## Context

When MTGS detects a conflict, it can generate recommendations to resolve it. The question is: should the system apply those recommendations automatically (updating the tool definition without human intervention), or only propose them for human review?

This is a consequential product design decision. Tool definitions are production artifacts — incorrect automated changes could introduce new routing failures, break contracts with tool consumers, or violate team ownership policies.

---

## Decision Drivers

- **Human control:** Tool owners must consent to changes to definitions they own
- **Trust:** The governance system is new — users need to build confidence in its recommendations before trusting them to self-apply
- **Auditability:** Every tool definition change must be traceable to a human decision
- **Risk of auto-apply failure:** An LLM recommendation that reduces one conflict score might inadvertently introduce another conflict or change the tool's intended behavior
- **Compliance:** In regulated industries, changes to production tool definitions may require change management processes that cannot be bypassed by automated systems

---

## Options Considered

### Option A: Auto-apply all recommendations

System automatically updates tool definitions when a recommendation is generated.

**Pros:** Fastest path to conflict resolution, minimal friction  
**Cons:** No human oversight, risk of cascading failures, breaks team ownership, audit trail shows machine as author

### Option B: Recommendation-only (human must accept)

System proposes changes. Humans review, accept, or reject. On accept, the system optionally applies the change.

**Pros:** Full human control, clear audit trail, builds trust over time  
**Cons:** Resolution is slower, recommendations may be ignored

### Option C: Tiered approach

Auto-apply LOW/INFO conflicts, require approval for MEDIUM+.

**Pros:** Balance of automation and control  
**Cons:** More complex logic, "safe" auto-applies might still be wrong, harder to explain to governance teams

---

## Decision

**Recommendation-only for v1** (Option B). The system generates specific, actionable recommendations but never modifies tool definitions without explicit human acceptance.

Acceptance modes:
1. **Accept + Apply** (via dashboard or API): System updates the tool definition in-place, increments version, writes audit log entry with `changed_by = current_user`
2. **Accept (manual)**: User acknowledges the recommendation but applies the change themselves (e.g., in their source control)
3. **Reject**: User provides a reason; recommendation is archived; conflict remains open

A tiered auto-apply mode may be introduced in Phase 4 once the recommendation quality has been validated against production data and users have established trust in the engine.

---

## Consequences

**Positive:**
- Tool owners retain full control over their definitions
- Audit log always shows a human as the author of every definition change
- Builds user confidence in the system before increasing automation
- Aligns with change management requirements in regulated industries

**Negative:**
- Open conflicts may persist if teams don't act on recommendations
- Resolution velocity depends on human responsiveness
- High-volume environments (100+ conflicts) may face recommendation fatigue

**Mitigation for recommendation fatigue:**
- Dashboard surfaces conflicts sorted by risk score — highest-risk first
- Slack/email notifications route alerts to the owning team, not a central queue
- Bulk "acknowledge" flow for LOW/INFO conflicts that teams choose to accept as known-good
