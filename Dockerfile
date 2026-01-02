# Multi-stage build: Node.js builds frontend, Python serves everything
# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files first for better caching
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build production frontend
RUN npm run build

# Stage 2: Python backend with built frontend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api.py .
COPY orchestrator.py .
COPY llm_client.py .
COPY prompts.py .
COPY document_extractor.py .
COPY audit/ ./audit/
COPY database/ ./database/
COPY extraction/ ./extraction/
COPY reasoning/ ./reasoning/
COPY tools/ ./tools/

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create directories for uploads and audit storage
RUN mkdir -p uploads audit_storage

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Expose port (Railway uses PORT env var)
EXPOSE 8000

# Start the server - Railway sets PORT env var
CMD ["python", "-c", "import os; port = int(os.environ.get('PORT', 8000)); import uvicorn; uvicorn.run('api:app', host='0.0.0.0', port=port)"]

