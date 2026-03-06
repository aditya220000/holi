import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Topic(str, enum.Enum):
    RELATIONSHIPS = "relationships"
    FINANCE = "finance"
    HEALTH = "health"
    CULTURE = "left_vs_right"


class ReelStatus(str, enum.Enum):
    GENERATING = "generating"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublishStatus(str, enum.Enum):
    QUEUED = "queued"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RawClip(Base):
    __tablename__ = "raw_clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_uri: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    is_cod: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    reels: Mapped[list["Reel"]] = relationship(back_populates="raw_clip")


class Reel(Base):
    __tablename__ = "reels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic: Mapped[Topic] = mapped_column(Enum(Topic, name="topic_enum"), nullable=False)
    status: Mapped[ReelStatus] = mapped_column(Enum(ReelStatus, name="reel_status_enum"), nullable=False, default=ReelStatus.GENERATING)
    raw_clip_id: Mapped[int | None] = mapped_column(ForeignKey("raw_clips.id"), nullable=True)
    broll_start_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    broll_end_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    script_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chosen_variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voice_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="elevenlabs")
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    voiceover_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    video_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    s3_video_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    virality_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    raw_clip: Mapped[RawClip | None] = relationship(back_populates="reels")
    script_variants: Mapped[list["ScriptVariant"]] = relationship(back_populates="reel", cascade="all, delete-orphan")
    review_item: Mapped["ReviewItem | None"] = relationship(back_populates="reel", uselist=False, cascade="all, delete-orphan")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="reel", cascade="all, delete-orphan")
    metrics: Mapped[list["ReelMetric"]] = relationship(back_populates="reel", cascade="all, delete-orphan")


class ScriptVariant(Base):
    __tablename__ = "script_variants"
    __table_args__ = (UniqueConstraint("reel_id", "variant_index", name="uq_reel_variant_idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reels.id"), nullable=False)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False)
    style_label: Mapped[str] = mapped_column(String(64), nullable=False)
    script_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    virality_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    reel: Mapped[Reel] = relationship(back_populates="script_variants")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reels.id"), nullable=False, unique=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status_enum"), nullable=False, default=ReviewStatus.PENDING)
    reviewer_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reel: Mapped[Reel] = relationship(back_populates="review_item")


class PublishAccount(Base):
    __tablename__ = "publish_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform_enum"), nullable=False)
    handle: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_score: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Los_Angeles")
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="account")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reels.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("publish_accounts.id"), nullable=False)
    status: Mapped[PublishStatus] = mapped_column(Enum(PublishStatus, name="publish_status_enum"), nullable=False, default=PublishStatus.QUEUED)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    reel: Mapped[Reel] = relationship(back_populates="publish_jobs")
    account: Mapped[PublishAccount] = relationship(back_populates="publish_jobs")


class ReelMetric(Base):
    __tablename__ = "reel_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reels.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="metric_platform_enum"), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_time_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    saves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    reel: Mapped[Reel] = relationship(back_populates="metrics")
