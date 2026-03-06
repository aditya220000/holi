"""initial schema

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260306_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


topic_enum = sa.Enum("relationships", "finance", "health", "left_vs_right", name="topic_enum")
reel_status_enum = sa.Enum(
    "generating",
    "review_pending",
    "approved",
    "rejected",
    "published",
    "failed",
    name="reel_status_enum",
)
review_status_enum = sa.Enum("pending", "approved", "rejected", name="review_status_enum")
platform_enum = sa.Enum("instagram", "tiktok", "youtube", name="platform_enum")
publish_status_enum = sa.Enum("queued", "posting", "posted", "failed", name="publish_status_enum")
metric_platform_enum = sa.Enum("instagram", "tiktok", "youtube", name="metric_platform_enum")


def upgrade() -> None:
    topic_enum.create(op.get_bind(), checkfirst=True)
    reel_status_enum.create(op.get_bind(), checkfirst=True)
    review_status_enum.create(op.get_bind(), checkfirst=True)
    platform_enum.create(op.get_bind(), checkfirst=True)
    publish_status_enum.create(op.get_bind(), checkfirst=True)
    metric_platform_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "raw_clips",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_uri", sa.String(length=1024), nullable=False, unique=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("is_cod", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic", topic_enum, nullable=False),
        sa.Column("status", reel_status_enum, nullable=False, server_default="generating"),
        sa.Column("raw_clip_id", sa.Integer(), sa.ForeignKey("raw_clips.id"), nullable=True),
        sa.Column("broll_start_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("broll_end_seconds", sa.Float(), nullable=False, server_default="30"),
        sa.Column("script_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("chosen_variant_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voice_provider", sa.String(length=64), nullable=False, server_default="elevenlabs"),
        sa.Column("voice_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("voiceover_path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("video_path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("s3_video_uri", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("virality_score", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "script_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reels.id"), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column("style_label", sa.String(length=64), nullable=False),
        sa.Column("script_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("virality_score", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reel_id", "variant_index", name="uq_reel_variant_idx"),
    )

    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reels.id"), nullable=False, unique=True),
        sa.Column("status", review_status_enum, nullable=False, server_default="pending"),
        sa.Column("reviewer_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "publish_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", platform_enum, nullable=False),
        sa.Column("handle", sa.String(length=128), nullable=False),
        sa.Column("credential_ref", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_score", sa.Numeric(3, 2), nullable=False, server_default="1.0"),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="America/Los_Angeles"),
        sa.Column("last_posted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reels.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("publish_accounts.id"), nullable=False),
        sa.Column("status", publish_status_enum, nullable=False, server_default="queued"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "reel_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reels.id"), nullable=False),
        sa.Column("platform", metric_platform_enum, nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watch_time_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reel_metrics")
    op.drop_table("publish_jobs")
    op.drop_table("publish_accounts")
    op.drop_table("review_items")
    op.drop_table("script_variants")
    op.drop_table("reels")
    op.drop_table("raw_clips")
    op.drop_table("generation_runs")

    metric_platform_enum.drop(op.get_bind(), checkfirst=True)
    publish_status_enum.drop(op.get_bind(), checkfirst=True)
    platform_enum.drop(op.get_bind(), checkfirst=True)
    review_status_enum.drop(op.get_bind(), checkfirst=True)
    reel_status_enum.drop(op.get_bind(), checkfirst=True)
    topic_enum.drop(op.get_bind(), checkfirst=True)
