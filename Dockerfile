# ---- Base image
FROM python:3.11-slim

# ---- System deps: FFmpeg + Opus + Sodium + Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libsodium23 \
    git \
 && rm -rf /var/lib/apt/lists/*

# ---- Make Python output unbuffered
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ---- Workdir
WORKDIR /app

# ---- Install Python deps
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt

# ---- Copy the rest of your code
COPY . .

RUN chmod +x docker-entrypoint.sh

# ---- Sync suburbs on start, then run bot
ENTRYPOINT ["./docker-entrypoint.sh"]
