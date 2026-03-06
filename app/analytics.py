from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Reel, ReelMetric, Topic


def metric_quality_score(metric: ReelMetric) -> float:
    score = 0.0
    score += min(4.0, metric.watch_time_pct / 25.0)
    score += min(2.0, metric.saves / 100.0)
    score += min(2.0, metric.shares / 100.0)
    score += min(1.0, metric.comments / 100.0)
    score += min(1.0, metric.likes / 500.0)
    return round(min(10.0, score), 2)


def aggregate_topic_performance(db: Session) -> dict[str, float]:
    rows = db.execute(
        select(Reel.topic, func.avg(ReelMetric.watch_time_pct))
        .join(ReelMetric, ReelMetric.reel_id == Reel.id)
        .group_by(Reel.topic)
    ).all()

    result = {topic.value: 0.0 for topic in Topic}
    for topic, avg_watch in rows:
        result[topic.value] = round(float(avg_watch or 0.0), 2)
    return result


def latest_metric_for_reel(db: Session, reel_id: UUID) -> ReelMetric | None:
    return db.scalar(
        select(ReelMetric)
        .where(ReelMetric.reel_id == reel_id)
        .order_by(ReelMetric.collected_at.desc())
        .limit(1)
    )


def should_regenerate(reel: Reel, latest_metric: ReelMetric | None) -> bool:
    if latest_metric is None:
        return False

    weak_retention = latest_metric.watch_time_pct < 35.0
    weak_distribution = (latest_metric.saves + latest_metric.shares) < 20
    return weak_retention and weak_distribution


def ingest_metric(
    db: Session,
    reel_id: UUID,
    platform,
    views: int,
    watch_time_pct: float,
    saves: int,
    shares: int,
    comments: int,
    likes: int,
) -> ReelMetric:
    metric = ReelMetric(
        reel_id=reel_id,
        platform=platform,
        views=views,
        watch_time_pct=watch_time_pct,
        saves=saves,
        shares=shares,
        comments=comments,
        likes=likes,
        collected_at=datetime.now(UTC),
    )
    db.add(metric)
    db.flush()
    return metric
