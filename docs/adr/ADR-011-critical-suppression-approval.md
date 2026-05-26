# ADR-011: CRITICAL Conflict Suppressions Require Explicit Approver Sign-Off

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team  
**PRD Reference:** Open Question #7

---

## Context

Conflict suppression allows a team to mark a conflict as intentionally accepted — "we know these tools overlap, and we've decided to live with it." This is a legitimate governance action when, for example, two tools have high semantic similarity but are owned by the same team and serve clearly distinct user segments.

The question is whether suppression should require approval, and if so, for which severities.

---

## Decision Drivers

- **CRITICAL conflicts are categorically different:** An exact name collision across servers isn't a nuanced severity judgment — it's a clear-cut routing failure waiting to happen. Suppressing it without review means deliberately deploying a known-broken configuration.
- **Audit trail:** Compliance teams need to see that a human with authority explicitly accepted the risk, not just any team member.
- **Practical usability:** Requiring approval for every LOW/INFO suppression would create friction with no governance value.
- **Role hierarchy:** The system already has APPROVER and ADMIN roles — suppression approval is a natural fit.

---

## Options Considered

### Option A: Suppression always requires approval

Every conflict suppression must be approved by an APPROVER+ role.

**Pros:** Strongest governance  
**Cons:** Too much friction for LOW/INFO suppression (e.g., suppressing advisory similarity warnings)

### Option B: No approval required for any suppression

Any EDITOR can suppress any conflict.

**Pros:** Maximum flexibility  
**Cons:** CRITICAL conflicts could be silently suppressed with no oversight

### Option C: Approval required only for CRITICAL suppressions

CRITICAL: must be approved by APPROVER+ role  
HIGH and below: EDITOR can self-suppress

**Pros:** Balances governance with usability  
**Cons:** HIGH conflicts can be suppressed without review (mitigated by notification)

### Option D: Approval required for CRITICAL and HIGH

CRITICAL + HIGH: require APPROVER+ sign-off  
MEDIUM and below: self-suppress

---

## Decision

**Approval required for CRITICAL conflict suppressions.** HIGH and below may be self-suppressed by EDITOR+, but the suppression is logged and notified.

Full matrix:

| Severity | Suppress by | Notification |
|---|---|---|
| CRITICAL | APPROVER or ADMIN only | ✅ Always + Audit log |
| HIGH | EDITOR+ (self-suppress) | ✅ Slack/email to tool owners |
| MEDIUM | EDITOR+ | ⚠️ Audit log only |
| LOW | EDITOR+ | Audit log only |
| INFO | EDITOR+ | Audit log only |

The approval workflow for CRITICAL suppression:
1. EDITOR submits suppression request with reason
2. MTGS routes approval request to all APPROVERs in the environment
3. Any APPROVER (or ADMIN) can approve or deny
4. Approved: conflict moves to `suppressed` status; audit log records approver + reason
5. Denied: conflict remains `open`; requester notified

---

## Consequences

**Positive:**
- CRITICAL suppressions have a traceable approval chain — satisfies compliance requirements
- The APPROVER role has a concrete, meaningful purpose beyond tool registration
- HIGH suppressions still proceed without a bottleneck while being fully auditable
- Governance teams can filter the audit log for "CRITICAL suppression approved" events during compliance reviews

**Negative:**
- CRITICAL suppression approval adds process latency (someone must act on the approval request)
- Small teams without dedicated APPROVERs may find CRITICAL suppression hard to complete

**Mitigation for small teams:**
The `ADMIN` role can always approve suppressions. In small organizations, the same person may hold both EDITOR and ADMIN roles — they can self-approve, which is recorded in the audit log for transparency.
