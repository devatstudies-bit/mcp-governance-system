"""Tool schemas — request, response, and internal transfer objects."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from mtgs.schemas.common import CamelModel, TimestampSchema


# ── Input schemas ─────────────────────────────────────────────────────────────

class ToolRegisterRequest(CamelModel):
    """Body for POST /environments/{env_id}/tools"""

    name: str = Field(min_length=1, max_length=255, description="MCP tool name (snake_case)")
    description: str = Field(min_length=10, description="Natural language description for LLM")
    input_schema: dict[str, Any] = Field(description="JSON Schema for tool parameters")
    server_id: uuid.UUID
    owner_team_id: uuid.UUID | None = None
    change_reason: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Tool name must contain only alphanumeric characters, underscores, or hyphens"
            )
        return v

    @field_validator("input_schema")
    @classmethod
    def validate_json_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "type" not in v and "properties" not in v:
            raise ValueError("input_schema must be a valid JSON Schema object")
        return v


class ToolUpdateRequest(CamelModel):
    """Body for PUT /environments/{env_id}/tools/{tool_id}"""

    description: str | None = Field(default=None, min_length=10)
    input_schema: dict[str, Any] | None = None
    status: str | None = None
    change_reason: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ToolUpdateRequest":
        if not any([self.description, self.input_schema, self.status]):
            raise ValueError("At least one of description, input_schema, or status must be provided")
        return self


class ToolCheckRequest(CamelModel):
    """Body for POST /environments/{env_id}/tools/check (dry-run / CI gate)"""

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=10)
    input_schema: dict[str, Any]
    server_id: uuid.UUID
    run_simulation: bool = Field(
        default=False,
        description="Run LLM impact simulation (slower, more thorough)"
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class ToolResponse(TimestampSchema):
    """Full tool representation returned from the registry."""

    id: uuid.UUID
    environment_id: uuid.UUID
    server_id: uuid.UUID
    owner_team_id: uuid.UUID | None
    name: str
    description: str
    input_schema: dict[str, Any]
    status: str
    version: int
    embedding_model: str | None
    conflict_count: int = 0  # populated by service layer


class ToolVersionResponse(TimestampSchema):
    """A single historical version of a tool."""

    id: uuid.UUID
    tool_id: uuid.UUID
    version: int
    name: str
    description: str
    input_schema: dict[str, Any]
    change_reason: str | None
    diff: dict[str, Any] | None


class ToolCheckResponse(CamelModel):
    """Response from the CI/CD gate dry-run check."""

    passed: bool
    blocking_severity: str | None = None  # highest blocking severity found
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    impact_summary: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    analysis_run_id: uuid.UUID | None = None
    dashboard_url: str | None = None


class ToolRegistrationResponse(CamelModel):
    """Response from POST /tools — returned immediately; analysis runs async."""

    tool_id: uuid.UUID
    status: str
    analysis_run_id: uuid.UUID | None = None
    message: str = "Tool registered. Conflict analysis running asynchronously."
