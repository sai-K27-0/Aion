# Aion Backend Dockerfile
# =======================
# Multi-stage build for production deployment

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies (including audio/voice libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    portaudio19-dev \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (audio, voice, PostgreSQL client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ffmpeg \
    libportaudio2 \
    libsndfile1 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash aion

# Create data directory and set permissions
RUN mkdir -p /app/data && chown -R aion:aion /app

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER aion

# Copy wheels and requirements, install from wheels
COPY --from=builder /app/wheels /wheels
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --user --find-links=/wheels -r /app/requirements.txt

# Copy application code
COPY --chown=aion:aion . .

# Set PATH for user-installed packages
ENV PATH="/home/aion/.local/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run the application
ENTRYPOINT ["/app/entrypoint.sh"]
