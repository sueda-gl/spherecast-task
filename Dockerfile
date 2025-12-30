# Multi-stage build for SphereCast

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend with frontend static files
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY *.py ./
COPY database/ ./database/
COPY extraction/ ./extraction/
COPY reasoning/ ./reasoning/
COPY audit/ ./audit/

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create necessary directories
RUN mkdir -p uploads audit_storage

# Expose port (Railway uses PORT env var)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/ || exit 1

# Start server using shell script
CMD ["./start.sh"]
