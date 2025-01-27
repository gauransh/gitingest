# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install build dependencies and Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --timeout 1000 -r requirements.txt \
    && rm -rf /var/lib/apt/lists/*

# Runtime stage
FROM python:3.12-slim

# Set Python environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=9900

# Install git and clean up in one layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Copy Python packages and source code
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY src/ ./

# Copy entrypoint script and set permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Change ownership of the application files
RUN chown -R appuser:appuser /app /entrypoint.sh

# Switch to non-root user
USER appuser

# Expose the correct port
EXPOSE ${PORT}

ENTRYPOINT ["/entrypoint.sh"]
