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

    ffmpeg_threads: int = Field(default=2, alias="FFMPEG_THREADS")
    transcode_timeout_seconds: int = Field(default=900, alias="TRANSCODE_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


