from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Platform, PublishAccount, PublishJob, PublishStatus, Reel


def upload_video_to_s3(local_video_path: str, key_prefix: str = "reels") -> str:
    if not settings.s3_bucket_output:
        return ""

    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        region_name=settings.aws_region,
    )

    local_path = Path(local_video_path)
    key = f"{key_prefix}/{local_path.name}"
    client.upload_file(str(local_path), settings.s3_bucket_output, key)
    return f"s3://{settings.s3_bucket_output}/{key}"


def _platform_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.platform_proxy_url:
        headers["X-Enterprise-Proxy"] = "configured"
    return headers


def queue_publish_jobs(db: Session, reel: Reel, start_at: datetime | None = None) -> list[PublishJob]:
    start_time = start_at or datetime.now(UTC)
    jobs: list[PublishJob] = []

    accounts = db.scalars(
        select(PublishAccount)
        .where(PublishAccount.is_active.is_(True), PublishAccount.health_score >= 0.65)
        .order_by(PublishAccount.last_posted_at.asc().nullsfirst())
    ).all()

    if not accounts:
        return jobs

    for index, account in enumerate(accounts):
        scheduled_time = start_time + timedelta(seconds=settings.posting_min_gap_seconds * index)
        jobs_today = db.scalar(
            select(func.count(PublishJob.id)).where(
                PublishJob.account_id == account.id,
                PublishJob.scheduled_for >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )
        if jobs_today and jobs_today >= min(account.daily_limit, settings.daily_post_limit_per_account):
            continue

        job = PublishJob(
            reel_id=reel.id,
            account_id=account.id,
            status=PublishStatus.QUEUED,
            scheduled_for=scheduled_time,
        )
        db.add(job)
        jobs.append(job)

    db.flush()
    return jobs


def _post_instagram(reel: Reel, account: PublishAccount) -> tuple[bool, str]:
    if not settings.meta_graph_access_token or not settings.meta_instagram_business_id:
        return False, "Meta credentials missing"

    create_resp = requests.post(
        f"https://graph.facebook.com/v20.0/{settings.meta_instagram_business_id}/media",
        headers=_platform_headers(),
        data={
            "media_type": "REELS",
            "video_url": reel.s3_video_uri,
            "caption": reel.script_text[:2100],
            "access_token": settings.meta_graph_access_token,
        },
        timeout=45,
    )
    if create_resp.status_code >= 300:
        return False, create_resp.text

    container_id = create_resp.json().get("id")
    if not container_id:
        return False, f"Missing container id: {create_resp.text}"

    publish_resp = requests.post(
        f"https://graph.facebook.com/v20.0/{settings.meta_instagram_business_id}/media_publish",
        headers=_platform_headers(),
        data={
            "creation_id": container_id,
            "access_token": settings.meta_graph_access_token,
        },
        timeout=45,
    )
    if publish_resp.status_code >= 300:
        return False, publish_resp.text

    return True, "published"


def _post_tiktok(reel: Reel, account: PublishAccount) -> tuple[bool, str]:
    if not settings.tiktok_access_token:
        return False, "TikTok credentials missing"

    # TikTok upload APIs vary by app scope. Keep a minimal official request flow placeholder.
    response = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={
            **_platform_headers(),
            "Authorization": f"Bearer {settings.tiktok_access_token}",
        },
        json={
            "post_info": {
                "title": reel.script_text[:150],
                "privacy_level": "SELF_ONLY",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": reel.s3_video_uri,
            },
        },
        timeout=45,
    )
    if response.status_code >= 300:
        return False, response.text
    return True, "queued"


def _post_youtube(reel: Reel, account: PublishAccount) -> tuple[bool, str]:
    if not settings.youtube_api_key or not settings.youtube_channel_id:
        return False, "YouTube credentials missing"

    # Minimal v3 metadata insert representation; production should use OAuth resumable upload.
    response = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={
            "part": "snippet,status",
            "key": settings.youtube_api_key,
            "uploadType": "resumable",
        },
        headers=_platform_headers(),
        json={
            "snippet": {
                "channelId": settings.youtube_channel_id,
                "title": reel.script_text[:100],
                "description": reel.script_text,
                "categoryId": "22",
            },
            "status": {"privacyStatus": "private"},
        },
        timeout=45,
    )
    if response.status_code >= 300:
        return False, response.text
    return True, "metadata-prepared"


def post_publish_job(db: Session, job: PublishJob) -> tuple[bool, str]:
    reel = db.get(Reel, job.reel_id)
    account = db.get(PublishAccount, job.account_id)
    if not reel or not account:
        return False, "Invalid reel/account"

    if account.platform == Platform.INSTAGRAM:
        return _post_instagram(reel, account)
    if account.platform == Platform.TIKTOK:
        return _post_tiktok(reel, account)
    if account.platform == Platform.YOUTUBE:
        return _post_youtube(reel, account)

    return False, f"Unsupported platform {account.platform.value}"
