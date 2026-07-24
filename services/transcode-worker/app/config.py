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

    sqs_transcode_queue_url: str = Field(
        default="",
        alias="SQS_TRANSCODE_QUEUE_URL",
    )
    sqs_dlq_url: str = Field(default="", alias="SQS_DLQ_URL")
    sqs_endpoint_url: str | None = Field(default=None, alias="SQS_ENDPOINT_URL")

    # DynamoDB (catalog) — the worker flips a movie to "ready" on completion.
    dynamodb_endpoint_url: str | None = Field(default=None, alias="DYNAMODB_ENDPOINT_URL")
    dynamodb_table: str = Field(default="streamsre-catalog", alias="DYNAMODB_TABLE")

    # Browser-facing origin base URL used to build playback manifest URLs.
    origin_base_url: str = Field(default="http://localhost:8080", alias="ORIGIN_BASE_URL")

    ffmpeg_threads: int = Field(default=0, alias="FFMPEG_THREADS")  # 0 = use all cores
    transcode_timeout_seconds: int = Field(default=900, alias="TRANSCODE_TIMEOUT_SECONDS")

    # Encoder: libx264 (CPU) by default; set USE_NVENC=1 once the container has
    # GPU access (nvidia-container-toolkit) to use h264_nvenc + CUDA decode.
    x264_preset: str = Field(default="veryfast", alias="X264_PRESET")
    use_nvenc: bool = Field(default=False, alias="USE_NVENC")
    nvenc_preset: str = Field(default="p4", alias="NVENC_PRESET")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


