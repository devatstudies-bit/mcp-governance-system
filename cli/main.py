"""
MTGS CLI — `mtgs` command.

Commands:
  mtgs tools check    --file tool.json --env prod
  mtgs tools register --file tool.json --env prod --server my-mcp
  mtgs conflicts list --env prod --severity HIGH,CRITICAL
  mtgs analyze        --env prod --probes 50
  mtgs health         --env prod
  mtgs servers sync   --server-url http://mcp-server:8080 --env dev
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="mtgs",
    help="MCP Tool Governance System CLI",
    no_args_is_help=True,
)
tools_app = typer.Typer(help="Tool registry commands")
conflicts_app = typer.Typer(help="Conflict management commands")
servers_app = typer.Typer(help="MCP server commands")

app.add_typer(tools_app, name="tools")
app.add_typer(conflicts_app, name="conflicts")
app.add_typer(servers_app, name="servers")

console = Console()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> httpx.Client:
    api_url = os.environ.get("MTGS_API_URL", "http://localhost:8000")
    api_key = os.environ.get("MTGS_API_KEY", "")
    return httpx.Client(
        base_url=api_url,
        headers={"X-API-Key": api_key},
        timeout=60.0,
    )


def _load_tool_file(file: Path) -> dict:
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)
    try:
        return json.loads(file.read_text())
    except json.JSONDecodeError as e:
        rprint(f"[red]Error:[/red] Invalid JSON in {file}: {e}")
        raise typer.Exit(1)


# ── mtgs tools check ──────────────────────────────────────────────────────────

@tools_app.command("check")
def check_tool(
    file: Path = typer.Option(..., "--file", "-f", help="Path to tool definition JSON/YAML"),
    env: str = typer.Option(..., "--env", "-e", help="Environment name (dev/staging/prod)"),
    fail_on: str = typer.Option("HIGH", "--fail-on", help="Minimum severity to fail: CRITICAL|HIGH|MEDIUM"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save report to JSON file"),
    server_id: Optional[str] = typer.Option(None, "--server-id", help="Server UUID override"),
):
    """
    Dry-run conflict check for a tool definition — does NOT register it.
    Exit code 0 = passed, 1 = conflicts found above threshold.
    """
    tool_def = _load_tool_file(file)

    # Inject server_id if provided
    if server_id:
        tool_def["server_id"] = server_id

    rprint(f"[blue]Checking tool:[/blue] {tool_def.get('name', '?')} against env=[bold]{env}[/bold]")

    with _get_client() as client:
        # Get environments to find env_id
        resp = client.get(f"/v1/environments?name={env}")
        if resp.status_code != 200:
            rprint(f"[red]API error:[/red] {resp.text}")
            raise typer.Exit(2)

        envs = resp.json().get("items", [])
        if not envs:
            rprint(f"[red]Environment '{env}' not found.[/red]")
            raise typer.Exit(2)
        env_id = envs[0]["id"]

        resp = client.post(f"/v1/environments/{env_id}/tools/check", json=tool_def)
        if resp.status_code not in (200, 201):
            rprint(f"[red]API error {resp.status_code}:[/red] {resp.text}")
            raise typer.Exit(2)

        result = resp.json()

    # Print results
    passed = result.get("passed", False)
    conflicts = result.get("conflicts", [])
    warnings = result.get("warnings", [])

    if passed:
        rprint(f"[green]✅ PASSED[/green] — No blocking conflicts found.")
    else:
        rprint(f"[red]❌ FAILED[/red] — {len(conflicts)} blocking conflict(s) found.")

    if conflicts:
        table = Table(title="Blocking Conflicts", show_header=True)
        table.add_column("Type", style="red")
        table.add_column("Severity", style="bold")
        table.add_column("Conflicting Tool")
        table.add_column("Score")
        for c in conflicts:
            table.add_row(c["type"], c["severity"], c.get("conflicting_tool", "?"), str(c.get("score", "")))
        console.print(table)

    if warnings:
        rprint(f"\n[yellow]⚠ {len(warnings)} warning(s) (below fail threshold)[/yellow]")

    # Save report
    if output:
        output.write_text(json.dumps(result, indent=2))
        rprint(f"\nReport saved to [blue]{output}[/blue]")

    raise typer.Exit(0 if passed else 1)


# ── mtgs tools register ───────────────────────────────────────────────────────

@tools_app.command("register")
def register_tool(
    file: Path = typer.Option(..., "--file", "-f"),
    env: str = typer.Option(..., "--env", "-e"),
    server: str = typer.Option(..., "--server", "-s", help="Server name or UUID"),
):
    """Register a new tool in the registry."""
    tool_def = _load_tool_file(file)
    tool_def["server_name"] = server  # resolved by API

    rprint(f"[blue]Registering:[/blue] {tool_def.get('name')}")
    with _get_client() as client:
        resp = client.get(f"/v1/environments?name={env}")
        envs = resp.json().get("items", [])
        if not envs:
            rprint(f"[red]Environment '{env}' not found[/red]")
            raise typer.Exit(1)
        env_id = envs[0]["id"]

        resp = client.post(f"/v1/environments/{env_id}/tools", json=tool_def)
        if resp.status_code == 201:
            data = resp.json()
            rprint(f"[green]✅ Registered[/green] tool_id={data['tool_id']}")
            rprint(f"   Analysis running: run_id={data.get('analysis_run_id')}")
        else:
            rprint(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            raise typer.Exit(1)


# ── mtgs conflicts list ───────────────────────────────────────────────────────

@conflicts_app.command("list")
def list_conflicts(
    env: str = typer.Option(..., "--env", "-e"),
    severity: Optional[str] = typer.Option(None, "--severity", help="Comma-separated: HIGH,CRITICAL"),
):
    """List open conflicts in an environment."""
    with _get_client() as client:
        resp = client.get(f"/v1/environments?name={env}")
        envs = resp.json().get("items", [])
        if not envs:
            rprint(f"[red]Environment '{env}' not found[/red]")
            raise typer.Exit(1)
        env_id = envs[0]["id"]

        params = {"status": "open"}
        if severity:
            params["severity"] = severity

        resp = client.get(f"/v1/environments/{env_id}/conflicts", params=params)
        data = resp.json()

    conflicts = data.get("items", [])
    total = data.get("total", 0)

    if not conflicts:
        rprint("[green]No open conflicts found.[/green]")
        return

    table = Table(title=f"Open Conflicts — {env} ({total} total)", show_header=True)
    table.add_column("ID", style="dim", no_wrap=True, max_width=12)
    table.add_column("Type")
    table.add_column("Severity", style="bold")
    table.add_column("Tools Involved")
    table.add_column("Score")
    table.add_column("Detected")

    for c in conflicts:
        sev = c["severity"]
        color = {"CRITICAL": "red", "HIGH": "orange3", "MEDIUM": "yellow", "LOW": "cyan"}.get(sev, "white")
        table.add_row(
            c["id"][:8] + "...",
            c["conflict_type"],
            f"[{color}]{sev}[/{color}]",
            str(len(c.get("tool_ids", []))),
            str(c.get("conflict_score", "")),
            c.get("detected_at", "")[:10],
        )
    console.print(table)


# ── mtgs health ───────────────────────────────────────────────────────────────

@app.command()
def health(env: str = typer.Option(..., "--env", "-e")):
    """Show governance health score for an environment."""
    with _get_client() as client:
        resp = client.get(f"/v1/environments?name={env}")
        envs = resp.json().get("items", [])
        if not envs:
            rprint(f"[red]Environment '{env}' not found[/red]")
            raise typer.Exit(1)
        env_id = envs[0]["id"]

        resp = client.get(f"/v1/environments/{env_id}/health")
        data = resp.json()

    score = data.get("score", 0)
    color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    rprint(f"\n[bold]Environment:[/bold] {env}")
    rprint(f"[bold]Health Score:[/bold] [{color}]{score}/100[/{color}]  (trend: {data.get('trend', '?')})")
    rprint(f"[bold]Active Tools:[/bold] {data.get('active_tools', 0)}")

    oc = data.get("open_conflicts", {})
    rprint(f"[bold]Open Conflicts:[/bold] CRITICAL={oc.get('CRITICAL',0)} HIGH={oc.get('HIGH',0)} MEDIUM={oc.get('MEDIUM',0)} LOW={oc.get('LOW',0)}")


# ── mtgs analyze ─────────────────────────────────────────────────────────────

@app.command()
def analyze(
    env: str = typer.Option(..., "--env", "-e"),
    probes: int = typer.Option(50, "--probes", "-p"),
):
    """Trigger a full environment analysis run."""
    with _get_client() as client:
        resp = client.get(f"/v1/environments?name={env}")
        envs = resp.json().get("items", [])
        if not envs:
            rprint(f"[red]Environment '{env}' not found[/red]")
            raise typer.Exit(1)
        env_id = envs[0]["id"]

        resp = client.post(f"/v1/environments/{env_id}/analyze", json={"probe_count": probes})
        if resp.status_code == 202:
            data = resp.json()
            rprint(f"[green]✅ Analysis started:[/green] run_id={data.get('analysis_run_id')}")
        else:
            rprint(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
