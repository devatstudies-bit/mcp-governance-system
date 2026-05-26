# ADR-010: Manual Import + JSON Upload for v1 MCP Server Sync

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team  
**PRD Reference:** Open Question #5

---

## Context

MCP servers expose a `tools/list` endpoint that returns all registered tool definitions. MTGS can theoretically auto-sync by polling this endpoint on a schedule. However, the MCP ecosystem in 2025 is heterogeneous:

- Some MCP servers support `tools/list` as defined in the spec
- Some have modified implementations with non-standard schemas
- Some MCP servers are behind auth barriers that require token negotiation
- Some don't support `tools/list` at all (only expose tools dynamically per session)
- Enterprise MCP servers may be on private networks unreachable from the MTGS service

---

## Decision Drivers

- **Reliability:** Sync must not fail silently. If MTGS can't reach an MCP server, the registry becomes stale without warning.
- **v1 scope:** Building robust agent-based crawling for non-standard servers is Phase 2+ scope at minimum
- **Security:** MTGS should not need network access to customer's internal MCP servers in v1
- **User control:** Teams want to choose when their tools are submitted to the registry, not have them auto-discovered

---

## Options Considered

### Option A: Manual import only (JSON file upload)

Users export tool definitions from their MCP server and upload via CLI or API.

**Pros:** Works for all MCP implementations, no network dependency, user controls timing  
**Cons:** Manual step, can become stale if teams forget to update

### Option B: Polling sync (scheduled auto-sync from `tools/list`)

MTGS polls the `tools/list` endpoint on a configurable schedule.

**Pros:** Always up-to-date, no manual step  
**Cons:** Network connectivity requirement, fails for non-standard/private MCP servers, auth complexity

### Option C: Agent-based crawl

An autonomous agent discovers and imports tools from MCP servers.

**Pros:** Handles non-standard servers  
**Cons:** Very complex, out of v1 scope, security concerns

### Option D: Both manual import and optional polling sync

**Pros:** Covers both use cases  
**Cons:** More implementation work

---

## Decision

**Manual import + JSON upload as the only sync mechanism for v1.**

`mtgs servers sync` command initiates a one-time sync from a live MCP server when the URL is reachable:

```bash
mtgs servers sync \
  --server-url http://my-mcp-server:8080 \
  --env dev \
  --server-name my-mcp
```

When the server is not reachable (air-gapped, private network), users export JSON and upload:

```bash
# Export from MCP server (user's responsibility)
curl http://my-mcp:8080/tools/list > my-tools.json

# Bulk import to MTGS
mtgs tools import --file my-tools.json --server my-mcp --env dev
```

A `sync_enabled` flag on `mcp_servers` records whether the server supports auto-sync. Scheduled sync via Celery beat is implemented in `core/sync/mcp_sync.py` but **only triggers when `sync_enabled=true`** — this must be explicitly opted into by the team.

---

## Consequences

**Positive:**
- Works for all MCP server types (private, public, non-standard)
- No security concerns about MTGS reaching into internal networks
- Teams have explicit control over when their tools enter the registry
- Simple to implement and reason about

**Negative:**
- Registry can drift from actual server state if teams don't re-sync
- No real-time conflict detection for tools added directly to MCP without going through MTGS

**Drift detection (partial mitigation):**
The `mcp_servers.last_synced_at` field enables the dashboard to show a warning when a server hasn't been synced in > 7 days (configurable). This prompts teams to re-run sync before relying on conflict reports.

**Roadmap:**
Phase 2 adds scheduled auto-sync for servers that support standard `tools/list`. Phase 4 evaluates agent-based crawling for servers that don't conform to the spec.
