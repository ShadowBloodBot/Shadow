# ---- Base image
FROM python:3.11-slim

# ---- System deps: FFmpeg + Opus + Sodium for Discord voice
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libsodium23 \
 && rm -rf /var/lib/apt/lists/*

# ---- Make Python output unbuffered (better logs)
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ---- Workdir
WORKDIR /app

# ---- Install Python deps first (better layer caching)
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt

# ---- Copy the rest of your code
COPY . .

# ---- Start the bot
CMD ["python", "-u", "bot.py"]
