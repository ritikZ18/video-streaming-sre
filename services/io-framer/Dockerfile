# I/O Framer — frames in, interpolated frames out.
# RIFE (intermediate-flow) FPS boost via Vulkan, wrapped by FastAPI.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RIFE_BIN=/opt/rife/rife-ncnn-vulkan \
    RIFE_MODELS_DIR=/opt/rife \
    RIFE_MODEL=rife-v4.6

# System deps:
#  - ffmpeg               : decode → PNG frames, re-encode the mezzanine
#  - libvulkan1           : the Vulkan loader the rife binary links against
#  - mesa-vulkan-drivers  : lavapipe software ICD → the CPU fallback path
#  - vulkan-tools         : vulkaninfo, for backend detection in /healthz
#  - libgomp1             : OpenMP runtime the prebuilt rife binary needs
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libvulkan1 mesa-vulkan-drivers vulkan-tools \
      libgomp1 \
      wget unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Prebuilt rife-ncnn-vulkan (binary + bundled model dirs). Pinned release.
ARG RIFE_VER=20221029
RUN mkdir -p /opt/rife && cd /tmp \
    && wget -q "https://github.com/nihui/rife-ncnn-vulkan/releases/download/${RIFE_VER}/rife-ncnn-vulkan-${RIFE_VER}-ubuntu.zip" -O rife.zip \
    && unzip -q rife.zip \
    && cp -r rife-ncnn-vulkan-${RIFE_VER}-ubuntu/* /opt/rife/ \
    && chmod +x /opt/rife/rife-ncnn-vulkan \
    && rm -rf /tmp/rife.zip "/tmp/rife-ncnn-vulkan-${RIFE_VER}-ubuntu"

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
