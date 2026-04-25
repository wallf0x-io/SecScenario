FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for any wheel that doesn't ship a manylinux build (lxml fallback).
# Kept in a single layer so apt cache is purged from the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Persisted runtime data lives on bind-mounts; ensure dirs exist in the image too.
RUN mkdir -p uploads challenges instance

# Main UI port (mapped to host 6000 by compose) + the challenge port range
# used in container mode (CHALLENGE_PORT_BASE..END, default 6100-6500).
EXPOSE 5000
EXPOSE 6100-6500

# Sensible defaults for container mode. Override via -e or compose env.
ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    FLASK_DEBUG=0 \
    CHALLENGE_HOST=0.0.0.0

CMD ["python", "app.py"]
