from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import ReelStatus, Topic


class ScriptTestRequest(BaseModel):
    topic: Topic | None = None
    count: int = Field(default=10, ge=1, le=50)


class ScriptVariantOut(BaseModel):
    variant_index: int
    style_label: str
    script_payload: dict[str, Any]
    virality_score: float


class ScriptTestResponse(BaseModel):
    topic: Topic
    variants: list[ScriptVariantOut]


class BatchGenerateRequest(BaseModel):
    count: int = Field(default=50, ge=1, le=2000)
    force_topic: Topic | None = None


class BatchGenerateResponse(BaseModel):
    run_id: int
    celery_task_id: str
    requested_count: int


class ReelOut(BaseModel):
    id: UUID
    topic: Topic
    status: ReelStatus
    video_path: str
    virality_score: float
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewDecisionRequest(BaseModel):
    approve: bool
    reviewer_notes: str = ""
