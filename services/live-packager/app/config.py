from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Live packager configuration. Shares the AWS_*/S3_*/USE_NVENC env names with
    the rest of the stack so a single .env drives everything."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = Field(default=8000, alias="LIVE_PACKAGER_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # Rolling HLS output root (shared read-only with the origin container).
    segments_dir: str = Field(default="/live_segments", alias="LIVE_SEGMENTS_DIR")

    # AWS / S3 (MinIO locally) — the playout source lives in the uploads bucket.
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_video_bucket: str = Field(default="streamsre-raw-uploads", alias="S3_VIDEO_BUCKET")
    # Where a harvested live recording lands as a permanent VOD (served via /hls/).
    s3_segments_bucket: str = Field(
        default="streamsre-hls-segments", alias="S3_SEGMENTS_BUCKET"
    )

    # Ingest server (MediaMTX) as seen from INSIDE the compose network. Whatever
    # protocol the encoder pushed with, MediaMTX republishes it on this one RTMP
    # path, so the packager always pulls RTMP.
    ingest_rtmp_host: str = Field(default="live-ingest:1935", alias="LIVE_INGEST_INTERNAL_HOST")
    ingest_api_host: str = Field(default="live-ingest:9997", alias="LIVE_INGEST_API_HOST")

    # Encode
    use_nvenc: bool = Field(default=False, alias="USE_NVENC")
    x264_preset: str = Field(default="veryfast", alias="LIVE_X264_PRESET")
    nvenc_preset: str = Field(default="p4", alias="LIVE_NVENC_PRESET")
    hls_time: int = Field(default=4, alias="LIVE_HLS_TIME")
    hls_list_size: int = Field(default=6, alias="LIVE_HLS_LIST_SIZE")

    # One channel at a time keeps the GTX 1650 comfortably above realtime.
    max_channels: int = Field(default=1, alias="LIVE_MAX_CHANNELS")
    max_height: int = Field(default=1080, alias="LIVE_MAX_HEIGHT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
