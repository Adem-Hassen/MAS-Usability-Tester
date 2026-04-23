# backend/schemas.py
"""
Pydantic v2 schemas for all API request/response models and SSE event payloads.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    QUEUED   = "queued"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"


class SSEEventType(str, Enum):
    """All SSE event types emitted by the pipeline."""
    PIPELINE_START       = "pipeline_start"
    SUPERVISOR_ANALYSIS  = "supervisor_analysis"
    PERSONA_START        = "persona_start"
    PERSONA_ACTION       = "persona_action"
    PERSONA_COMPLETE     = "persona_complete"
    CLUSTERING_START     = "clustering_start"
    CLUSTERING_COMPLETE  = "clustering_complete"
    RECOMMENDER_START    = "recommender_start"
    RECOMMENDER_PATCH    = "recommender_patch"
    CONFLICT_DETECTED    = "conflict_detected"
    CONFLICT_RESOLVED    = "conflict_resolved"
    PATCH_APPLIED        = "patch_applied"
    PIPELINE_COMPLETE    = "pipeline_complete"
    ERROR                = "error"

    # Legacy event types (kept for backward compatibility with existing frontend)
    LOG                  = "log"
    PROGRESS             = "progress"
    STEP                 = "step"
    ISSUE                = "issue"
    PATCH                = "patch"
    DONE                 = "done"


class StageState(str, Enum):
    PENDING  = "pending"
    ACTIVE   = "active"
    COMPLETE = "complete"
    ERROR    = "error"


# ---------------------------------------------------------------------------
# API Request/Response Models
# ---------------------------------------------------------------------------

class EvaluateResponse(BaseModel):
    job_id: str
    file_count: int
    status: str = "queued"


class HealthResponse(BaseModel):
    status: str = "ok"
    model: str = ""
    tokens_remaining: int = 0


class IssueCluster(BaseModel):
    cluster_id: str
    severity: str
    selector: str = ""
    description: str = ""
    personas: list[str] = Field(default_factory=list)
    patch_applied: bool = False


class IssuesResponse(BaseModel):
    clusters: list[IssueCluster] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SSE Event Payload Models
# ---------------------------------------------------------------------------

class PipelineStartEvent(BaseModel):
    event: str = SSEEventType.PIPELINE_START
    job_id: str
    file_count: int
    model: str = ""
    tokens_remaining: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SupervisorAnalysisEvent(BaseModel):
    event: str = SSEEventType.SUPERVISOR_ANALYSIS
    summary: str = ""
    structural_issues_found: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PersonaStartEvent(BaseModel):
    event: str = SSEEventType.PERSONA_START
    persona_id: str
    persona_name: str = ""
    persona_type: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PersonaActionEvent(BaseModel):
    event: str = SSEEventType.PERSONA_ACTION
    persona_id: str
    action_type: str
    selector: Optional[str] = None
    value: Optional[str] = None
    result: str = ""  # "pass" or "fail"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PersonaCompleteEvent(BaseModel):
    event: str = SSEEventType.PERSONA_COMPLETE
    persona_id: str
    issues_found: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ClusteringStartEvent(BaseModel):
    event: str = SSEEventType.CLUSTERING_START
    raw_issue_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ClusteringCompleteEvent(BaseModel):
    event: str = SSEEventType.CLUSTERING_COMPLETE
    cluster_count: int = 0
    duplicate_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class RecommenderStartEvent(BaseModel):
    event: str = SSEEventType.RECOMMENDER_START
    recommender_id: str
    cluster_ids: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class RecommenderPatchEvent(BaseModel):
    event: str = SSEEventType.RECOMMENDER_PATCH
    recommender_id: str
    component: str = ""
    patch_type: str = ""
    before_snippet: str = ""
    after_snippet: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ConflictDetectedEvent(BaseModel):
    event: str = SSEEventType.CONFLICT_DETECTED
    components_affected: list[str] = Field(default_factory=list)
    strategy: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ConflictResolvedEvent(BaseModel):
    event: str = SSEEventType.CONFLICT_RESOLVED
    resolution_strategy: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PatchAppliedEvent(BaseModel):
    event: str = SSEEventType.PATCH_APPLIED
    file_name: str
    patch_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class PipelineCompleteEvent(BaseModel):
    event: str = SSEEventType.PIPELINE_COMPLETE
    job_id: str
    issues_found: int = 0
    patches_applied: int = 0
    duplicates_removed: int = 0
    report_url: str = ""
    download_url: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ErrorEvent(BaseModel):
    event: str = SSEEventType.ERROR
    stage: str = ""
    message: str = ""
    traceback: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
