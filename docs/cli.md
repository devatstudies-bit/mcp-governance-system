# CLI Reference

The `mtgs` CLI provides a terminal interface to all MTGS capabilities — checking tools before registering, running environment analyses, managing conflicts, and syncing from live MCP servers.

---

## Installation

The CLI is installed automatically with the Python package:

```bash
pip install -e .
mtgs --help
```

---

## Configuration

The CLI reads its target API from environment variables:

```bash
export MTGS_API_URL=https://api.mtgs.yourdomain.com   # default: http://localhost:8000
export MTGS_API_KEY=mtgs_live_xxxxxxxxxxxxxxxxxxxx
export MTGS_DEFAULT_ENV=prod   # optional default environment name
```

Or pass per-command with `--api-url` and `--api-key` flags.

---

## Command Groups

```
mtgs
├── tools
│   ├── check       Dry-run conflict check before registering
│   ├── register    Register a tool (with optional check)
│   ├── list        List tools in an environment
│   ├── get         Show a single tool's details and conflicts
│   ├── update      Update a tool definition
│   └── deprecate   Soft-delete a tool
│
├── conflicts
│   ├── list        List open conflicts
│   ├── get         Show conflict detail with evidence
│   ├── ack         Acknowledge a conflict
│   └── suppress    Suppress a conflict (requires APPROVER role)
│
├── analyze         Trigger a full environment analysis run
│
├── health          Show environment health score
│
├── servers
│   └── sync        Sync tool definitions from a live MCP server
│
├── probes
│   ├── list        List probe queries
│   ├── add         Add a manual probe query
│   └── generate    Auto-generate probe queries from current tools
│
└── auth
    ├── login       Get an access token (interactive)
    └── create-key  Generate a new API key
```

---

## `mtgs tools check`

Dry-run conflict check for a tool definition — does **not** register the tool.

```bash
mtgs tools check \
  --file tool.json \
  --env prod
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--file` | ✓ | — | Path to tool JSON file |
| `--env` | ✓ | — | Environment name (`dev`, `staging`, `prod`) |
| `--server` | — | — | Server name (overrides `server_id` in file) |
| `--output` | — | — | Write full report to JSON file |
| `--format` | — | `human` | `human` or `json` |
| `--no-simulation` | — | false | Skip Stage 4 (faster, no LLM calls) |
| `--probes` | — | 50 | Number of probe queries for simulation |

**Exit codes:**
- `0` — PASSED (no blocking conflicts)
- `1` — FAILED (blocking conflicts found per configured policy)

**Example output (human format):**
```
✓ PASSED  create_zendesk_ticket  (prod)

  ┌─────────────────────────────────────────────────┐
  │  Stage 1  Lexical     0ms     0 conflicts       │
  │  Stage 2  Schema      11ms    0 conflicts       │
  │  Stage 3  Semantic    1.4s    0 conflicts       │
  │  Stage 4  Simulation  18.2s   0 conflicts       │
  └─────────────────────────────────────────────────┘

  Impact: 0% routing shift (50 probes, 0 changed)

  Risk Score: 0 / 100
```

**Example output (FAILED):**
```
✗ FAILED  create_task  (prod)

  2 conflicts detected:

  ┌──────────────────────────────────────────────────────────────┐
  │  ✗ HIGH   SEMANTIC_OVERLAP                                   │
  │  create_task ↔ create_jira_issue  (similarity: 0.91)         │
  │                                                              │
  │  Recommendations:                                            │
  │  → DESCRIPTION_REWRITE: Narrow scope to specify Asana only  │
  │    Predicted score after: 42 (was: 91)                       │
  │  Run: mtgs conflicts get <conflict_id> --show-recs           │
  └──────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  ⚠ MEDIUM  SIMILAR_NAME                                      │
  │  create_task ↔ create_tasks  (edit distance: 1)              │
  └──────────────────────────────────────────────────────────────┘

  Impact: 34% routing shift (50 probes, 17 changed)
  At-risk tools: create_jira_issue, create_linear_task

  Risk Score: 48 / 100
  Analysis: https://mtgs.yourdomain.com/runs/run-abc
```

---

## `mtgs tools register`

Register a tool. Runs a sync check (Stages 1+2) before committing.

```bash
mtgs tools register \
  --file tool.json \
  --server jira-mcp \
  --env prod
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--file` | ✓ | — | Path to tool JSON file |
| `--env` | ✓ | — | Environment name |
| `--server` | ✓ | — | Server name or ID to associate the tool with |
| `--team` | — | — | Owner team name |
| `--skip-check` | — | false | Skip the pre-registration check (not recommended) |
| `--force` | — | false | Register even if MEDIUM conflicts found |
| `--format` | — | `human` | `human` or `json` |

```
✓ Registered  create_jira_issue  (tool_id: tool-abc-123)
  Full analysis running in background.
  Run ID: run-xyz456
  Dashboard: https://mtgs.yourdomain.com/runs/run-xyz456
```

---

## `mtgs tools list`

```bash
mtgs tools list --env prod
mtgs tools list --env prod --server jira-mcp --has-conflicts
```

| Flag | Description |
|---|---|
| `--env` | Environment name |
| `--server` | Filter by server name |
| `--status` | `active` \| `flagged` \| `deprecated` |
| `--has-conflicts` | Only tools with open conflicts |
| `--format` | `table` (default) or `json` |

```
Name                    Server       Status    Conflicts   Updated
─────────────────────── ──────────── ───────── ─────────── ──────────
create_jira_issue       jira-mcp     active    ⚠ 1 MEDIUM  3 days ago
create_task             asana-mcp    flagged   ✗ 1 HIGH    2 hours ago
send_slack_message      slack-mcp    active    ✓ none      1 week ago

142 tools  ·  7 open conflicts (2 HIGH, 5 MEDIUM)
```

---

## `mtgs tools get`

Show full detail for one tool including conflicts and version history.

```bash
mtgs tools get create_jira_issue --env prod
```

---

## `mtgs conflicts list`

```bash
mtgs conflicts list --env prod
mtgs conflicts list --env prod --severity HIGH,CRITICAL
mtgs conflicts list --env prod --status open --format json
```

| Flag | Description |
|---|---|
| `--env` | Environment name |
| `--severity` | Comma-separated severities to filter: `CRITICAL,HIGH` |
| `--status` | `open` \| `acknowledged` \| `resolved` \| `suppressed` |
| `--type` | Conflict type: `SEMANTIC_OVERLAP`, `EXACT_NAME`, etc. |
| `--format` | `table` or `json` |

```
ID          Type              Severity  Tools                            Age
─────────── ──────────────── ───────── ──────────────────────────────── ──────
abc-12...   SEMANTIC_OVERLAP  HIGH      create_task ↔ create_jira_issue  2h ago
def-34...   SEMANTIC_OVERLAP  HIGH      send_email ↔ send_notification   5h ago
ghi-56...   SCHEMA_COLLISION  MEDIUM    get_user ↔ get_user_profile      1d ago

3 open conflicts  (2 HIGH, 1 MEDIUM)
```

---

## `mtgs conflicts get`

Show full conflict evidence and recommendations.

```bash
mtgs conflicts get abc-12345 --show-recs
```

---

## `mtgs analyze`

Trigger a full environment analysis run (async).

```bash
mtgs analyze --env prod --probes 100
```

| Flag | Description |
|---|---|
| `--env` | Environment name |
| `--probes` | Number of probe queries (default: 50) |
| `--wait` | Wait for completion and print results |

```
Analysis started.
Run ID: run-abc123
Status: pending

Polling for completion...
✓ Completed in 43s

  47 tools analyzed  ·  50 probe queries
  3 conflicts found  ·  Risk score: 28.5
  Routing shift: 12.0%

  Dashboard: https://mtgs.yourdomain.com/runs/run-abc123
```

---

## `mtgs health`

Show the governance health score for an environment.

```bash
mtgs health --env prod
```

```
Environment: prod

  Health Score: 74 / 100  (↑ from 68)  Grade: B

  Active tools:    142
  Open conflicts:  21 (0 CRITICAL  ·  2 HIGH  ·  5 MEDIUM  ·  11 LOW  ·  3 INFO)
  Last analysis:   2025-05-26T09:00:00Z
  Probe coverage:  87.3%  (312 probes for 142 tools)
```

---

## `mtgs servers sync`

Sync tool definitions from a live MCP server's `tools/list` endpoint.

```bash
mtgs servers sync \
  --server-url http://my-mcp-server:8080 \
  --env dev \
  --server-name my-mcp
```

| Flag | Description |
|---|---|
| `--server-url` | URL of the live MCP server |
| `--env` | Environment to sync into |
| `--server-name` | Friendly name for this server in the registry |
| `--dry-run` | Preview what would be added/updated without committing |

```
Syncing from http://my-mcp-server:8080 → dev

  Found 12 tools on server.
  Comparing with registry...

  + create_ticket      (new)
  ~ update_ticket      (description changed)
  = get_ticket         (unchanged)
  + delete_ticket      (new)
  ... 8 more unchanged

  2 new tools, 1 updated, 9 unchanged.
  Conflict analysis will run in background for new/updated tools.

  Press Enter to commit, Ctrl+C to cancel: _
```

---

## `mtgs probes generate`

Auto-generate probe queries for all tools in an environment using Claude.

```bash
mtgs probes generate --env prod --count 50
```

---

## `mtgs auth create-key`

Generate a new API key (requires ADMIN role).

```bash
mtgs auth create-key --name "ci-prod" --role EDITOR
```

```
API Key created: mtgs_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
Role: EDITOR
Key ID: key-abc123

⚠  Store this key securely — it will not be shown again.
```

---

## GitHub Actions Integration

```yaml
# .github/workflows/mcp-tool-governance.yml
name: MCP Tool Governance Check

on:
  pull_request:
    paths:
      - 'tools/**/*.json'

jobs:
  governance-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install MTGS CLI
        run: pip install mtgs

      - name: Check tool definitions
        env:
          MTGS_API_KEY: ${{ secrets.MTGS_API_KEY }}
          MTGS_API_URL: ${{ secrets.MTGS_API_URL }}
        run: |
          for file in tools/**/*.json; do
            mtgs tools check --file "$file" --env prod --output report.json
          done

      - name: Upload reports
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: mtgs-conflict-reports
          path: report.json
```

Exit code `1` from `mtgs tools check` causes the CI step to fail. The report JSON artifact provides full context in the PR.
