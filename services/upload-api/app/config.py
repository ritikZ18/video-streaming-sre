from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the upload API service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")

    # AWS / region
    aws_region: str = Field(default="us-west-2", alias="AWS_REGION")

    # S3 buckets
    s3_video_bucket: str = Field(default="streamsre-raw-uploads", alias="S3_VIDEO_BUCKET")
    s3_segments_bucket: str = Field(
        default="streamsre-hls-segments",
        alias="S3_SEGMENTS_BUCKET",
    )
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")

    # DynamoDB (catalog)
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    dynamodb_table: str = Field(default="streamsre-catalog", alias="DYNAMODB_TABLE")

    # DynamoDB-backed durable job queue (replaces the ephemeral SQS emulator).
    queue_table: str = Field(default="streamsre-transcode-queue", alias="QUEUE_TABLE")

    # Admin auth (gates the write endpoints: upload + create movie)
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")

    # Upload behaviour
    upload_api_port: int = Field(default=8000, alias="UPLOAD_API_PORT")
    max_upload_size_mb: int = Field(default=5000, alias="MAX_UPLOAD_SIZE_MB")
    allowed_extensions: str = Field(default="mp4,mov,mkv,webm", alias="ALLOWED_EXTENSIONS")
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")

    # Origin / playback
    origin_port: int = Field(default=8080, alias="ORIGIN_PORT")

    # --- I/O Framer (frame interpolation) — Phase 0 plumbing, OFF by default ---
    # Frames in, interpolated frames out. RIFE (intermediate-flow) FPS boost via
    # Vulkan, run as a sidecar. These flags gate whether the upload API will even
    # accept an interpolation request; nothing acts on them yet.
    interp_enabled: bool = Field(default=False, alias="INTERP_ENABLED")
    interp_default_target_fps: int = Field(default=60, alias="INTERP_DEFAULT_TARGET_FPS")
    interp_max_target_fps: int = Field(default=60, alias="INTERP_MAX_TARGET_FPS")
    interp_max_height: int = Field(default=1080, alias="INTERP_MAX_HEIGHT")
    interp_max_source_fps: int = Field(default=40, alias="INTERP_MAX_SOURCE_FPS")
    interp_max_duration_seconds: int = Field(
        default=600, alias="INTERP_MAX_DURATION_SECONDS"
    )

    @property
    def origin_base_url(self) -> str:
        """Base URL used to construct playback URLs."""
        return f"http://localhost:{self.origin_port}"

    @property
    def allowed_extension_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.allowed_extensions.split(",") if ext.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]


