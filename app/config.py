from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="ReelEmpire-CoD-Pro")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    database_url: str = Field(default="postgresql+psycopg2://reel_empire:reel_empire@localhost:5432/reel_empire")
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672//")
    redis_url: str = Field(default="redis://localhost:6379/0")

    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_region: str = Field(default="us-east-1")
    s3_bucket_raw_cod: str = Field(default="")
    s3_bucket_output: str = Field(default="")

    anthropic_api_key: str = Field(default="")
    grok_api_key: str = Field(default="")
    grok_base_url: str = Field(default="https://api.x.ai/v1")
    ollama_base_url: str = Field(default="http://localhost:11434")
    script_model_primary: str = Field(default="claude-sonnet-4-20250514")
    script_model_fallback: str = Field(default="grok-2-latest")
    script_model_local: str = Field(default="llama3.1:405b")

    elevenlabs_api_key: str = Field(default="")
    elevenlabs_voice_finance: str = Field(default="")
    elevenlabs_voice_relationships: str = Field(default="")
    elevenlabs_voice_health: str = Field(default="")
    elevenlabs_voice_culture: str = Field(default="")

    meta_graph_access_token: str = Field(default="")
    meta_instagram_business_id: str = Field(default="")
    tiktok_access_token: str = Field(default="")
    youtube_api_key: str = Field(default="")
    youtube_channel_id: str = Field(default="")

    local_clips_dir: str = Field(default="/data/clips")
    local_music_dir: str = Field(default="/data/music")
    local_output_dir: str = Field(default="/data/output")

    default_batch_size: int = Field(default=50)
    max_batch_size: int = Field(default=2000)
    cod_usage_target_ratio: float = Field(default=0.8)

    enable_scheduler: bool = Field(default=True)
    schedule_cron: str = Field(default="0 */2 * * *")
    review_required: bool = Field(default=True)

    account_rotation_enabled: bool = Field(default=True)
    posting_min_gap_seconds: int = Field(default=1200)
    daily_post_limit_per_account: int = Field(default=20)
    platform_proxy_url: str = Field(default="")
    pexels_api_key: str = Field(default="")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
