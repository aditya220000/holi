from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.dashboard import router as dashboard_router
from app.database import engine, get_db
from app.models import (
    Base,
    GenerationRun,
    Reel,
    ReelStatus,
    ReviewStatus,
)
from app.schemas import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    ReelOut,
    ReviewDecisionRequest,
    ScriptTestRequest,
    ScriptTestResponse,
    ScriptVariantOut,
)
from app.script_generator import MASTER_SCRIPT_PROMPT, generate_script_variants
from app.tasks import generate_batch_task
from app.uploader import queue_publish_jobs

app = FastAPI(title=settings.app_name)
app.include_router(dashboard_router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "time": datetime.now(UTC).isoformat()}


@app.post("/test_script", response_model=ScriptTestResponse)
def test_script(payload: ScriptTestRequest) -> ScriptTestResponse:
    topic, variants = generate_script_variants(topic=payload.topic, count=payload.count, fast_mode=True)
    return ScriptTestResponse(
        topic=topic,
        variants=[
            ScriptVariantOut(
                variant_index=v.variant_index,
                style_label=v.style_label,
                script_payload=v.script_payload,
                virality_score=v.virality_score,
            )
            for v in variants
        ],
    )


@app.post("/generate_batch", response_model=BatchGenerateResponse)
def generate_batch(payload: BatchGenerateRequest, db: Session = Depends(get_db)) -> BatchGenerateResponse:
    count = max(1, min(payload.count, settings.max_batch_size))
    run = GenerationRun(requested_count=count, created_count=0, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)

    task = generate_batch_task.delay(run.id, count, payload.force_topic.value if payload.force_topic else None)
    return BatchGenerateResponse(run_id=run.id, celery_task_id=task.id, requested_count=count)


@app.get("/reels", response_model=list[ReelOut])
def list_reels(limit: int = 50, db: Session = Depends(get_db)) -> list[ReelOut]:
    rows = db.scalars(select(Reel).order_by(Reel.created_at.desc()).limit(min(limit, 500))).all()
    return [
        ReelOut(
            id=row.id,
            topic=row.topic,
            status=row.status,
            video_path=row.video_path,
            virality_score=float(row.virality_score),
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.post("/review/{reel_id}/decision")
def review_decision(reel_id: UUID, payload: ReviewDecisionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    reel = db.get(Reel, reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    review = reel.review_item
    if review is None:
        raise HTTPException(status_code=400, detail="No review item for this reel")

    review.reviewer_notes = payload.reviewer_notes
    review.reviewed_at = datetime.now(UTC)

    if payload.approve:
        review.status = ReviewStatus.APPROVED
        reel.status = ReelStatus.APPROVED
        queue_publish_jobs(db, reel)
    else:
        review.status = ReviewStatus.REJECTED
        reel.status = ReelStatus.REJECTED

    db.commit()
    return {"reel_id": str(reel.id), "status": reel.status.value, "review": review.status.value}


@app.get("/prompt")
def prompt() -> dict[str, str]:
    return {"master_script_prompt": MASTER_SCRIPT_PROMPT}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)
