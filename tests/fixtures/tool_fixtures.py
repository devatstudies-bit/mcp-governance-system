"""
Reusable tool definition fixtures for tests.

All fixtures are plain dataclasses — no DB or framework dependency.
ToolDef is imported from mtgs.core.tool_def (canonical location).
"""

from __future__ import annotations

# Re-export ToolDef from canonical location so all test imports work
from mtgs.core.tool_def import ToolDef  # noqa: F401


# ── Identical / near-identical name pairs ─────────────────────────────────────

TOOL_SEND_MESSAGE_SLACK = ToolDef(
    name="send_message",
    description="Send a message to a Slack channel or user via the Slack API.",
    input_schema={
        "type": "object",
        "properties": {
            "channel": {"type": "string", "description": "Slack channel ID"},
            "text": {"type": "string", "description": "Message text"},
        },
        "required": ["channel", "text"],
    },
    server_name="slack-mcp",
)

TOOL_SEND_MESSAGE_EMAIL = ToolDef(
    name="send_message",  # EXACT NAME COLLISION with above
    description="Send an email message to one or more recipients.",
    input_schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    server_name="email-mcp",
)

TOOL_SEND_MSG = ToolDef(
    name="send_msg",  # SIMILAR name (edit distance 1 from send_message)
    description="Send a direct message to a user on Teams.",
    input_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["user_id", "content"],
    },
    server_name="teams-mcp",
)

# ── Semantic overlap pair ─────────────────────────────────────────────────────

TOOL_CREATE_TASK = ToolDef(
    name="create_task",
    description=(
        "Creates a new task in the project management system. "
        "Assigns it to a team member with a due date and priority."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "assignee": {"type": "string"},
            "due_date": {"type": "string", "format": "date"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["title"],
    },
    server_name="project-mcp",
)

TOOL_ADD_TODO = ToolDef(
    name="add_todo",
    description=(
        "Add a new to-do item to the task list. "
        "Specify assignee and deadline."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task_name": {"type": "string"},
            "assigned_to": {"type": "string"},
            "deadline": {"type": "string", "format": "date"},
        },
        "required": ["task_name"],
    },
    server_name="todo-mcp",
)

# ── Schema collision pair (same param name, different types) ──────────────────

TOOL_GET_USER_A = ToolDef(
    name="get_user",
    description="Retrieve user profile from the HR system by user ID.",
    input_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "integer", "description": "Numeric HR system ID"},
        },
        "required": ["user_id"],
    },
    server_name="hr-mcp",
)

TOOL_GET_USER_B = ToolDef(
    name="fetch_user",
    description="Fetch user account details from the authentication service.",
    input_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "UUID string from auth service"},
        },
        "required": ["user_id"],
    },
    server_name="auth-mcp",
)

# ── Completely distinct tools (no conflict expected) ──────────────────────────

TOOL_QUERY_DATABASE = ToolDef(
    name="query_database",
    description="Execute a read-only SQL SELECT query against the analytics warehouse.",
    input_schema={
        "type": "object",
        "properties": {
            "sql": {"type": "string"},
            "timeout_ms": {"type": "integer", "default": 5000},
        },
        "required": ["sql"],
    },
    server_name="analytics-mcp",
)

TOOL_GENERATE_INVOICE = ToolDef(
    name="generate_invoice",
    description=(
        "Generate a PDF invoice for a completed order and send it to the billing address."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "send_email": {"type": "boolean", "default": True},
        },
        "required": ["order_id"],
    },
    server_name="billing-mcp",
)

TOOL_SCHEDULE_MEETING = ToolDef(
    name="schedule_meeting",
    description="Schedule a calendar meeting and send invitations to all participants.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "participants": {"type": "array", "items": {"type": "string"}},
            "start_time": {"type": "string", "format": "date-time"},
            "duration_minutes": {"type": "integer"},
        },
        "required": ["title", "participants", "start_time"],
    },
    server_name="calendar-mcp",
)
