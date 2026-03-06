import random
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.analytics import latest_metric_for_reel, should_regenerate
from app.config import settings
from app.database import SessionLocal
from app.models import (
    GenerationRun,
    PublishJob,
    PublishStatus,
    RawClip,
    Reel,
    ReelStatus,
    ReviewItem,
    ReviewStatus,
    ScriptVariant,
    Topic,
)
from app.script_generator import generate_script_variants
from app.uploader import post_publish_job, queue_publish_jobs, upload_video_to_s3
from app.video_editor import (
    choose_random_music,
    choose_segment,
    download_pexels_fallback_clip,
    discover_cod_clips,
    probe_duration_seconds,
    render_reel,
)
from app.voiceover import synthesize_voiceover
from app.workers import celery_app


def _sync_cod_clips(db) -> None:
    existing_paths = set(db.scalars(select(RawClip.source_uri)).all())

    for clip_path in discover_cod_clips():
        if clip_path in existing_paths:
            continue
        try:
            duration = probe_duration_seconds(clip_path)
        except Exception:
            continue

        db.add(
            RawClip(
                source_uri=clip_path,
                duration_seconds=duration,
                is_cod=True,
                is_active=True,
            )
        )

    db.flush()


def _pick_cod_clip(db) -> RawClip:
    _sync_cod_clips(db)
    cod_clips = db.scalars(
        select(RawClip).where(RawClip.is_cod.is_(True), RawClip.is_active.is_(True))
    ).all()
    fallback_clips = db.scalars(
        select(RawClip).where(RawClip.is_cod.is_(False), RawClip.is_active.is_(True))
    ).all()

    if not cod_clips:
        pexels_path = download_pexels_fallback_clip()
        if pexels_path:
            known = db.scalar(select(RawClip).where(RawClip.source_uri == pexels_path))
            if known:
                return known
            duration = probe_duration_seconds(pexels_path)
            fallback = RawClip(
                source_uri=pexels_path,
                duration_seconds=duration,
                is_cod=False,
                is_active=True,
            )
            db.add(fallback)
            db.commit()
            db.refresh(fallback)
            return fallback
        raise RuntimeError(
            "No active CoD clips available. Add self-recorded clips to LOCAL_CLIPS_DIR first."
        )

    use_cod = True
    if fallback_clips and random.random() > settings.cod_usage_target_ratio:
        use_cod = False

    return random.choice(cod_clips if use_cod else fallback_clips)


def _create_reel_shell(db, topic: Topic, variants, force_clip: RawClip | None = None) -> Reel:
    chosen = variants[0]
    clip = force_clip or _pick_cod_clip(db)
    start_sec, segment_duration = choose_segment(clip.duration_seconds)

    reel = Reel(
        topic=topic,
        status=ReelStatus.GENERATING,
        raw_clip_id=clip.id,
        broll_start_seconds=start_sec,
        broll_end_seconds=round(start_sec + segment_duration, 2),
        script_text=chosen.script_payload["full_text"],
        chosen_variant_index=chosen.variant_index,
        virality_score=chosen.virality_score,
    )
    db.add(reel)
    db.flush()

    for variant in variants:
        db.add(
            ScriptVariant(
                reel_id=reel.id,
                variant_index=variant.variant_index,
                style_label=variant.style_label,
                script_payload=variant.script_payload,
                virality_score=variant.virality_score,
            )
        )

    db.commit()
    db.refresh(reel)
    return reel


def _finalize_reel_assets(db, reel: Reel, script_payload: dict, topic: Topic) -> Reel:
    clip = db.get(RawClip, reel.raw_clip_id)
    if not clip:
        raise RuntimeError("Assigned CoD clip not found")

    voice_path, voice_id = synthesize_voiceover(script_payload, topic, str(reel.id))

    output_path = f"{settings.local_output_dir.rstrip('/')}/{reel.id}.mp4"
    segment_duration = max(15.0, reel.broll_end_seconds - reel.broll_start_seconds)
    music_path = choose_random_music()

    render_reel(
        clip_path=clip.source_uri,
        voice_path=voice_path,
        script_payload=script_payload,
        output_path=output_path,
        start_seconds=reel.broll_start_seconds,
        duration_seconds=segment_duration,
        music_path=music_path,
    )

    reel.voice_id = voice_id
    reel.voiceover_path = voice_path
    reel.video_path = output_path
    reel.s3_video_uri = upload_video_to_s3(output_path)

    if settings.review_required:
        reel.status = ReelStatus.REVIEW_PENDING
        if reel.review_item:
            reel.review_item.status = ReviewStatus.PENDING
            reel.review_item.reviewer_notes = "Regenerated, waiting for human QA."
            reel.review_item.reviewed_at = None
        else:
            db.add(
                ReviewItem(
                    reel_id=reel.id,
                    status=ReviewStatus.PENDING,
                    reviewer_notes="Auto-created, waiting for human QA.",
                )
            )
    else:
        reel.status = ReelStatus.APPROVED
        queue_publish_jobs(db, reel)

    db.commit()
    db.refresh(reel)
    return reel


@celery_app.task(name="app.tasks.generate_single_reel_task")
def generate_single_reel_task(force_topic: str | None = None) -> str:
    db = SessionLocal()
    try:
        topic_arg = Topic(force_topic) if force_topic else None
        topic, variants = generate_script_variants(topic_arg, count=3)
        reel = _create_reel_shell(db, topic, variants)

        try:
            _finalize_reel_assets(db, reel, variants[0].script_payload, topic)
        except Exception as exc:
            reel.status = ReelStatus.FAILED
            reel.error_message = str(exc)
            db.commit()

        return str(reel.id)
    finally:
        db.close()


@celery_app.task(name="app.tasks.generate_batch_task")
def generate_batch_task(run_id: int, count: int, force_topic: str | None = None) -> dict:
    db = SessionLocal()
    created = 0
    failed = 0

    try:
        run = db.get(GenerationRun, run_id)
        if run:
            run.status = "running"
            db.commit()

        topic_arg = Topic(force_topic) if force_topic else None

        for _ in range(count):
            reel = None
            try:
                topic, variants = generate_script_variants(topic_arg, count=3)
                reel = _create_reel_shell(db, topic, variants)
                _finalize_reel_assets(db, reel, variants[0].script_payload, topic)
                created += 1
            except Exception as exc:
                if reel is not None:
                    reel.status = ReelStatus.FAILED
                    reel.error_message = str(exc)
                    db.commit()
                else:
                    db.rollback()
                failed += 1

        if run:
            run.created_count = created
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            db.commit()

        return {"run_id": run_id, "created": created, "failed": failed}
    finally:
        db.close()


@celery_app.task(name="app.tasks.create_and_generate_batch_task")
def create_and_generate_batch_task(count: int, force_topic: str | None = None) -> dict:
    db = SessionLocal()
    try:
        requested = max(1, min(count, settings.max_batch_size))
        run = GenerationRun(requested_count=requested, created_count=0, status="queued")
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()

    return generate_batch_task(run_id=run_id, count=requested, force_topic=force_topic)


@celery_app.task(name="app.tasks.regenerate_reel_task")
def regenerate_reel_task(reel_id: str) -> str:
    db = SessionLocal()
    try:
        reel = db.get(Reel, UUID(reel_id))
        if not reel:
            return "reel not found"

        latest_metric = latest_metric_for_reel(db, reel.id)
        if latest_metric and not should_regenerate(reel, latest_metric):
            return "metrics healthy; no regen needed"

        topic, variants = generate_script_variants(reel.topic, count=3)
        best = variants[0]

        reel.script_text = best.script_payload["full_text"]
        reel.chosen_variant_index = best.variant_index
        reel.virality_score = best.virality_score
        reel.status = ReelStatus.GENERATING

        db.query(ScriptVariant).filter(ScriptVariant.reel_id == reel.id).delete()
        for variant in variants:
            db.add(
                ScriptVariant(
                    reel_id=reel.id,
                    variant_index=variant.variant_index,
                    style_label=variant.style_label,
                    script_payload=variant.script_payload,
                    virality_score=variant.virality_score,
                )
            )
        db.commit()

        try:
            _finalize_reel_assets(db, reel, best.script_payload, topic)
            return "regenerated"
        except Exception as exc:
            reel.status = ReelStatus.FAILED
            reel.error_message = str(exc)
            db.commit()
            return "regen failed"
    finally:
        db.close()


@celery_app.task(name="app.tasks.process_publish_queue_task")
def process_publish_queue_task() -> dict:
    db = SessionLocal()
    processed = 0
    failed = 0

    try:
        jobs = (
            db.query(PublishJob)
            .filter(
                PublishJob.status == PublishStatus.QUEUED,
                PublishJob.scheduled_for <= datetime.now(UTC),
            )
            .limit(50)
            .all()
        )

        for job in jobs:
            job.status = PublishStatus.POSTING
            job.attempts += 1
            db.commit()

            try:
                ok, message = post_publish_job(db, job)
            except Exception as exc:
                ok, message = False, str(exc)
            if ok:
                job.status = PublishStatus.POSTED
                job.posted_at = datetime.now(UTC)
                reel = db.get(Reel, job.reel_id)
                if reel:
                    reel.status = ReelStatus.PUBLISHED
                account = job.account
                if account:
                    account.last_posted_at = datetime.now(UTC)
                processed += 1
            else:
                job.status = PublishStatus.FAILED
                job.error_message = message
                failed += 1

            db.commit()

        return {"processed": processed, "failed": failed}
    finally:
        db.close()
