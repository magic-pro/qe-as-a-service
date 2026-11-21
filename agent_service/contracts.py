"""Shared request and result envelopes for QE agent service callers."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=32000)
    run_id: UUID = Field(default_factory=uuid4)
    parent_run_id: UUID | None = None

    @field_validator("task")
    @classmethod
    def task_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task must not be blank")
        return value


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    run_id: UUID
    parent_run_id: UUID | None = None
    agent: str
    status: Literal["completed", "failed"]
    mode: Literal["live", "mock"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def result_matches_status(self):
        if self.status == "completed" and (not self.output or self.error is not None):
            raise ValueError("Completed results require output and no error")
        if self.status == "failed" and (not self.error or self.output is not None):
            raise ValueError("Failed results require an error and no output")
        return self
