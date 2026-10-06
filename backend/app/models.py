from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(min_length=8, max_length=80)
    project_description: str = Field(min_length=10, max_length=20_000)
    project_name: str | None = Field(default=None, max_length=200)

    @field_validator("project_description")
    @classmethod
    def description_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project_description cannot be blank")
        return value


class UploadedFileRecord(BaseModel):
    upload_id: str
    original_name: str
    stored_path: str
    sha256: str
    size_bytes: int
    uploaded_at: datetime


class ReferenceChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_file: str
    page_number: int
    chunk_number: int
    content: str


class SearchEvidence(ReferenceChunk):
    score: float | None = None


class ReasonedTask(BaseModel):
    """Schema the model must return. All values that drive the workbook are explicit."""

    model_config = ConfigDict(extra="forbid")

    job_task: str = Field(min_length=1, max_length=500)
    matched_reference_task: str | None
    rationale: str = Field(min_length=1, max_length=1500)
    quantity: float = Field(ge=0, le=1_000_000)
    unit: str = Field(min_length=1, max_length=80)
    unit_mandays: float = Field(ge=0, le=1_000_000)
    source_page: int | None = Field(ge=1)
    source_quote: str | None = Field(max_length=1200)
    confidence: float = Field(ge=0, le=1)
    review_required: bool


class ReasoningPlan(BaseModel):
    """Strict structured output produced by the Microsoft Agent Framework agent."""

    model_config = ConfigDict(extra="forbid")

    project_title: str = Field(min_length=1, max_length=200)
    project_summary: str = Field(min_length=1, max_length=3000)
    tasks: list[ReasonedTask] = Field(min_length=1, max_length=40)
    assumptions: list[str] = Field(max_length=30)
    warnings: list[str] = Field(max_length=30)


class CalculatedTask(ReasonedTask):
    calculated_total_mandays: float = Field(ge=0)


class ValidatedJobPlan(BaseModel):
    project_title: str
    project_summary: str
    tasks: list[CalculatedTask]
    assumptions: list[str]
    warnings: list[str]
    total_mandays: float = Field(ge=0)


class WorkflowResult(BaseModel):
    status: Literal["completed", "failed"]
    message: str
    output_file: str | None = None
    download_path: str | None = None
    task_count: int = 0
    total_mandays: float = 0
    warnings: list[str] = Field(default_factory=list)
