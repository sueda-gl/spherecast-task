# SphereCast Deployment Guide

## Current Architecture

- **Backend**: FastAPI (Python)
- **Frontend**: React + Vite
- **Databases**: SQLite (2 databases)
- **Storage**: Local filesystem

## Database Architecture

### 1. Main Database (`spherecast.db`)
- Products catalog
- Suppliers
- Purchase orders and line items
- Managed by SQLAlchemy ORM

### 2. Audit Database (`audit.db`)
- Complete extraction audit trail
- Document verification reports
- Review queue
- Processing status and metrics

## Deployment Options

### Option A: Simple Single-Server (Quick Start)

**Best for**: MVP, small teams, < 1000 documents/day

**Setup:**
1. Deploy to VPS (DigitalOcean, Linode, etc.)
2. Use SQLite databases as-is
3. Mount persistent volume for:
   - `/database/` 
   - `/uploads/`
   - `/audit_storage/`

**Pros:**
- Simple deployment
- No database server needed
- Works immediately
- Low cost

**Cons:**
- Single point of failure
- Can't scale horizontally
- Manual backups needed

**Example Docker Compose:**
```yaml
services:
  backend:
    build: .
    volumes:
      - ./database:/app/database
      - ./uploads:/app/uploads
      - ./audit_storage:/app/audit_storage
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
  
  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
```

### Option B: Cloud-Ready Production Setup

**Best for**: Production, scaling, high availability

**Changes Needed:**

#### 1. Database Migration
Replace SQLite with PostgreSQL:

```python
# config.py
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///database/spherecast.db"  # fallback for dev
)

AUDIT_DATABASE_URL = os.getenv(
    "AUDIT_DATABASE_URL", 
    "sqlite:///database/audit.db"  # fallback for dev
)
```

**Production values:**
```bash
DATABASE_URL=postgresql://user:pass@db.host:5432/spherecast
AUDIT_DATABASE_URL=postgresql://user:pass@db.host:5432/spherecast_audit
```

#### 2. File Storage Migration
Replace local storage with cloud storage (S3, GCS, etc.):

```python
# storage.py
import os
import boto3

class StorageBackend:
    def __init__(self):
        use_s3 = os.getenv("USE_S3_STORAGE", "false").lower() == "true"
        if use_s3:
            self.s3 = boto3.client('s3')
            self.bucket = os.getenv("S3_BUCKET")
        else:
            self.local_dir = Path("uploads")
    
    def save(self, file_data, filename):
        if hasattr(self, 's3'):
            self.s3.put_object(
                Bucket=self.bucket,
                Key=filename,
                Body=file_data
            )
            return f"s3://{self.bucket}/{filename}"
        else:
            path = self.local_dir / filename
            path.write_bytes(file_data)
            return str(path)
```

#### 3. Environment Configuration

Create `.env.production`:
```bash
# Database
DATABASE_URL=postgresql://...
AUDIT_DATABASE_URL=postgresql://...

# Storage
USE_S3_STORAGE=true
S3_BUCKET=spherecast-documents
AWS_REGION=us-east-1

# API Keys
OPENAI_API_KEY=sk-...

# App Config
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Option C: Hybrid Approach (Recommended)

**Best compromise for most teams:**

1. **Keep SQLite for development**
2. **Add PostgreSQL support** (don't force it)
3. **Keep local storage for development**
4. **Add S3 support** (optional in production)

**Benefits:**
- Easy local development
- Production-ready when needed
- Gradual migration path

## Migration Path

### Phase 1: Current (Works Now)
✅ SQLite databases
✅ Local file storage
✅ Single server deployment

**Deploy to:** Heroku, Railway, DigitalOcean App Platform

### Phase 2: Add Postgres Support
- Add database URL configuration
- Keep SQLite as fallback
- Update SQLAlchemy connection strings

**Deploy to:** AWS Elastic Beanstalk, GCP App Engine

### Phase 3: Add Cloud Storage
- Abstract storage layer
- Support both local and S3
- Migrate existing files

**Deploy to:** AWS ECS, Kubernetes

### Phase 4: Full Scale
- Multiple instances
- Load balancer
- CDN for documents
- Redis caching

**Deploy to:** AWS EKS, GCP GKE

## Immediate Action Items

1. **Add to .gitignore:**
   ```
   audit_storage/*
   !audit_storage/.gitkeep
   ```

2. **Create .gitkeep files:**
   ```bash
   touch uploads/.gitkeep
   touch audit_storage/.gitkeep
   ```

3. **Add database backup script:**
   ```bash
   #!/bin/bash
   # backup.sh
   DATE=$(date +%Y%m%d_%H%M%S)
   cp database/spherecast.db "backups/spherecast_${DATE}.db"
   cp database/audit.db "backups/audit_${DATE}.db"
   ```

4. **Document required volumes:**
   - `/database/` (persistent, frequent writes)
   - `/uploads/` (persistent, large files)
   - `/audit_storage/` (persistent, archival)

## Quick Deploy Commands

### Heroku (Simplest)
```bash
# Add Postgres addon
heroku addons:create heroku-postgresql:mini

# But you'll need to migrate from SQLite first
# Or keep SQLite on dyno filesystem (lost on restart)
```

### DigitalOcean App Platform
```yaml
# .do/app.yaml
services:
  - name: spherecast-api
    source_dir: /
    run_command: uvicorn api:app --host 0.0.0.0 --port 8000
    envs:
      - key: OPENAI_API_KEY
        scope: RUN_TIME
        type: SECRET
```

### Docker (Any provider)
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

# Create necessary directories
RUN mkdir -p database uploads audit_storage

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Database Backup Strategy

### Automated Backups
```python
# backup.py
import schedule
import shutil
from datetime import datetime
from pathlib import Path

def backup_databases():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    # Backup main database
    shutil.copy2(
        "database/spherecast.db",
        backup_dir / f"spherecast_{timestamp}.db"
    )
    
    # Backup audit database
    shutil.copy2(
        "database/audit.db", 
        backup_dir / f"audit_{timestamp}.db"
    )
    
    print(f"✓ Backup created: {timestamp}")

# Run daily at 2 AM
schedule.every().day.at("02:00").do(backup_databases)
```

## Monitoring

Key metrics to track:
- Extraction success rate
- Average confidence scores
- Review queue length
- API response times
- Database size growth

Use the `/api/statistics` endpoint for monitoring.

## Security Considerations

1. **API Keys**: Never commit `.env` files
2. **Database Access**: Use strong passwords, limit network access
3. **File Uploads**: Validate file types, scan for malware
4. **Rate Limiting**: Add rate limiting to API endpoints
5. **HTTPS**: Always use HTTPS in production

## Cost Estimates

### Small Scale (< 100 docs/day)
- **VPS**: $5-10/month (DigitalOcean, Linode)
- **Storage**: Included
- **Database**: SQLite (free)
- **Total**: ~$10/month

### Medium Scale (< 1000 docs/day)
- **Compute**: $20-50/month
- **Managed Postgres**: $15-25/month
- **S3 Storage**: $5-10/month
- **Total**: ~$50/month

### Large Scale (10K+ docs/day)
- **Load Balanced Compute**: $100-200/month
- **Database (RDS/CloudSQL)**: $50-100/month
- **Storage**: $20-50/month
- **CDN**: $20-50/month
- **Total**: ~$250/month

## Support & Scaling

Your current architecture will handle:
- ✅ Up to 1000 documents/day (single server)
- ✅ Up to 10GB of documents
- ✅ Up to 50 concurrent users

When to scale:
- [ ] > 1000 documents/day → Add Postgres
- [ ] > 10GB documents → Add S3/GCS
- [ ] > 100 concurrent users → Add load balancer
- [ ] > 10K documents/day → Add Redis caching

