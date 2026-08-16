# Live packager — turns a live source (an uploaded title re-streamed in real
# time, or an encoder feed pulled from the ingest server) into a rolling HLS
# ladder on the shared live_segments volume. FastAPI control plane + ffmpeg.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg does all the live encoding/packaging. (NVENC uses the host driver via
# nvidia-container-toolkit; this ffmpeg build includes the nvenc encoders.)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

# Where the rolling live HLS is written (shared read-only with the origin).
RUN mkdir -p /live_segments
VOLUME ["/live_segments"]

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
