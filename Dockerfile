FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data directories and non-root user for security
RUN groupadd -r agent && useradd -r -g agent agent && \
    mkdir -p agent_data/crm agent_data/scheduling agent_data/smart_demo logs config && \
    chown -R agent:agent /app

# Drop to non-root user
USER agent

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/status || exit 1

# Run the main API server — listen on $PORT for Cloud Run
CMD uvicorn smart_agent_server:app --host 0.0.0.0 --port ${PORT}
