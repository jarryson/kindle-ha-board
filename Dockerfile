# --- Stage 1: Build environment (Builder) ---
# Use the platform flag to ensure the correct architecture is used during build
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# Install build dependencies for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
COPY requirements.txt .

# Install dependencies into a local user directory
# pip will automatically handle architecture-specific compilation
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime environment (Runner) ---
FROM python:3.11-slim

WORKDIR /app

# 1. Install runtime shared libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# 3. Copy application code
COPY . .

# 4. Set environment variables
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Expose Flask port
EXPOSE 8135

CMD ["python", "main.py"]