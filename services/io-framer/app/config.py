from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """I/O Framer configuration. Reuses the shared INTERP_* / AWS_* env names so a
    single .env drives upload-api, the worker, and this sidecar."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    port: int = Field(default=8000, alias="IO_FRAMER_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    work_dir: str = Field(default="/tmp/io-framer", alias="IO_FRAMER_WORK_DIR")

    # AWS / S3 (MinIO locally)
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_video_bucket: str = Field(default="streamsre-raw-uploads", alias="S3_VIDEO_BUCKET")
    s3_segments_bucket: str = Field(
        default="streamsre-hls-segments", alias="S3_SEGMENTS_BUCKET"
    )

    # RIFE engine (rife-ncnn-vulkan binary + bundled model dirs)
    rife_bin: str = Field(default="/opt/rife/rife-ncnn-vulkan", alias="RIFE_BIN")
    rife_models_dir: str = Field(default="/opt/rife", alias="RIFE_MODELS_DIR")
    rife_model: str = Field(default="rife-v4.6", alias="RIFE_MODEL")
    # Vulkan device index. On a CPU-only host lavapipe is device 0, so the default
    # works for both the GPU and the software-fallback path.
    gpu_id: int = Field(default=0, alias="INTERP_GPU_ID")

    # Guardrails (mirror upload-api + worker; defence in depth)
    interp_max_target_fps: int = Field(default=60, alias="INTERP_MAX_TARGET_FPS")
    interp_max_height: int = Field(default=1080, alias="INTERP_MAX_HEIGHT")
    interp_max_source_fps: int = Field(default=40, alias="INTERP_MAX_SOURCE_FPS")
    interp_max_duration_seconds: int = Field(
        default=600, alias="INTERP_MAX_DURATION_SECONDS"
    )
    interp_timeout_seconds: int = Field(default=1800, alias="INTERP_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
