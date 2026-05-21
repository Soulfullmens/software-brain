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
RUN groupadd -r agent && useradd -r -g agent agent && \\
    mkdir -p agent_data/crm agent_data/scheduling logs config && \\
    chown -R agent:agent /app

# Drop to non-root user
USER agent

# Expose dashboard port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

# Run dashboard
CMD ["uvicorn", "src.business.dashboard:app", "--host", "0.0.0.0", "--port", "8000"]
