from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the transcode worker."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = Field(default="us-west-2", alias="AWS_REGION")

    s3_video_bucket: str = Field(default="streamsre-raw-uploads", alias="S3_VIDEO_BUCKET")
    s3_segments_bucket: str = Field(
        default="streamsre-hls-segments",
        alias="S3_SEGMENTS_BUCKET",
    )
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")

    # DynamoDB (catalog) — the worker flips a movie to "ready" on completion.
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    dynamodb_table: str = Field(default="streamsre-catalog", alias="DYNAMODB_TABLE")

    # DynamoDB-backed durable job queue (replaces the ephemeral SQS emulator). A
    # claimed job is leased for this many seconds; if the worker dies, the lease
    # expires and the job becomes claimable again (at-least-once, like SQS).
    queue_table: str = Field(default="streamsre-transcode-queue", alias="QUEUE_TABLE")
    queue_visibility_timeout_seconds: int = Field(
        default=1800, alias="QUEUE_VISIBILITY_TIMEOUT"
    )

    # Browser-facing origin base URL used to build playback manifest URLs.
    origin_base_url: str = Field(default="http://localhost:8080", alias="ORIGIN_BASE_URL")

    ffmpeg_threads: int = Field(default=0, alias="FFMPEG_THREADS")  # 0 = use all cores
    transcode_timeout_seconds: int = Field(default=900, alias="TRANSCODE_TIMEOUT_SECONDS")

    # Encoder: libx264 (CPU) by default; set USE_NVENC=1 once the container has
    # GPU access (nvidia-container-toolkit) to use h264_nvenc + CUDA decode.
    x264_preset: str = Field(default="veryfast", alias="X264_PRESET")
    use_nvenc: bool = Field(default=False, alias="USE_NVENC")
    nvenc_preset: str = Field(default="p4", alias="NVENC_PRESET")

    # --- I/O Framer (frame interpolation) — Phase 0 plumbing, OFF by default ---
    # The worker will (later phases) hand the decoded frames to the I/O Framer
    # sidecar over HTTP and mux the interpolated result back into the ladder.
    # For now these only describe where the sidecar lives and the safety caps;
    # no code path reads them yet.
    interp_enabled: bool = Field(default=False, alias="INTERP_ENABLED")
    interp_service_url: str = Field(
        default="http://io-framer:8000", alias="INTERP_SERVICE_URL"
    )
    interp_timeout_seconds: int = Field(default=1800, alias="INTERP_TIMEOUT_SECONDS")
    interp_max_target_fps: int = Field(default=60, alias="INTERP_MAX_TARGET_FPS")
    interp_max_height: int = Field(default=1080, alias="INTERP_MAX_HEIGHT")
    interp_max_source_fps: int = Field(default=40, alias="INTERP_MAX_SOURCE_FPS")
    interp_max_duration_seconds: int = Field(
        default=600, alias="INTERP_MAX_DURATION_SECONDS"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


