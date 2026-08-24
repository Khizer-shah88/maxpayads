FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer — copy requirements first)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create directories
RUN mkdir -p app/ml/models

# Make entrypoint executable
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["bash", "docker/entrypoint.sh"]
