"""
FastAPI backend to expose SphereCast extraction functionality.

Provides REST endpoints for:
- Email (.eml) upload and processing
- Extraction status and results
- Review queue management
- Statistics and audit trail
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import shutil
import json
from typing import Optional
from datetime import datetime
import os
import email
from email import policy
from email.parser import BytesParser
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file
# Use explicit path to ensure it works with uv run
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from orchestrator import UniversalOrchestrator
from audit import UpdateAuditTracker
from database.models import get_engine, get_session, PurchaseOrder, Product, Supplier, PurchaseOrderLine, SupplierProduct
from sqlalchemy import desc

app = FastAPI(title="SphereCast API", version="0.1.0")

# Get environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Enable CORS for frontend
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

# Add production URL if set
if FRONTEND_URL and FRONTEND_URL not in allowed_origins:
    allowed_origins.append(FRONTEND_URL)

# In production, also allow same-origin requests
if ENVIRONMENT == "production":
    allowed_origins.append("*")  # Since frontend is served from same origin

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy initialization for orchestrator and update tracker
# This prevents crashes on startup if OPENAI_API_KEY is not set
_orchestrator = None
_update_tracker = None

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY environment variable is not set")
        _orchestrator = UniversalOrchestrator(
            api_key=api_key,
            audit_db="database/audit.db",
            model="gpt-4o",
            database_path="database/spherecast.db"
        )
    return _orchestrator

def get_update_tracker():
    global _update_tracker
    if _update_tracker is None:
        _update_tracker = UpdateAuditTracker(db_path="database/audit.db")
    return _update_tracker

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# =============================================================================
# AUTO-INITIALIZE DATABASE ON STARTUP (for deployments without persistent volumes)
# =============================================================================
def auto_init_database():
    """Automatically initialize database if tables don't exist."""
    try:
        from database.models import Base, get_engine, get_session, Product
        from database.setup import seed_data
        from pathlib import Path
        
        db_path = Path("database/spherecast.db")
        db_path.parent.mkdir(exist_ok=True)
        
        engine = get_engine(str(db_path))
        
        # Create tables (safe to call multiple times)
        Base.metadata.create_all(engine)
        
        # Check if data exists
        session = get_session(engine)
        existing_products = session.query(Product).count()
        
        if existing_products == 0:
            print("📦 Auto-initializing database with seed data...")
            seed_data(session)
            print("✅ Database initialized successfully!")
        else:
            print(f"✅ Database already has {existing_products} products")
        
        session.close()
        
        # Also initialize audit database
        from audit.update_tracker import Base as AuditBase
        audit_path = Path("database/audit.db")
        audit_engine = get_engine(str(audit_path))
        AuditBase.metadata.create_all(audit_engine)
        print("✅ Audit database ready")
        
    except Exception as e:
        print(f"⚠️ Database auto-init warning: {e}")

# Run on startup
auto_init_database()


@app.get("/api/health")
async def health_check():
    """API health check."""
    return {"status": "ok", "service": "SphereCast API", "version": "0.1.0"}


@app.get("/api/debug-db")
async def debug_database():
    """Debug endpoint to check database status."""
    from pathlib import Path
    from sqlalchemy import inspect
    
    db_path = Path("database/spherecast.db")
    audit_path = Path("database/audit.db")
    
    result = {
        "database_dir_exists": Path("database").exists(),
        "database_dir_contents": [],
        "spherecast_db": {
            "exists": db_path.exists(),
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "tables": []
        },
        "audit_db": {
            "exists": audit_path.exists(),
            "size_bytes": audit_path.stat().st_size if audit_path.exists() else 0,
            "tables": []
        }
    }
    
    # List directory contents
    if Path("database").exists():
        result["database_dir_contents"] = [f.name for f in Path("database").iterdir()]
    
    # Check spherecast.db tables
    if db_path.exists():
        try:
            from database.models import get_engine
            engine = get_engine(str(db_path))
            inspector = inspect(engine)
            result["spherecast_db"]["tables"] = inspector.get_table_names()
        except Exception as e:
            result["spherecast_db"]["error"] = str(e)
    
    # Check audit.db tables
    if audit_path.exists():
        try:
            from database.models import get_engine
            engine = get_engine(str(audit_path))
            inspector = inspect(engine)
            result["audit_db"]["tables"] = inspector.get_table_names()
        except Exception as e:
            result["audit_db"]["error"] = str(e)
    
    return result


@app.post("/api/init-database")
async def init_database(secret: str = ""):
    """
    Initialize the database with tables and seed data.
    Call this once after first deployment.
    
    To prevent accidental resets, requires secret=INIT_DB
    """
    if secret != "INIT_DB":
        raise HTTPException(status_code=403, detail="Invalid secret. Use ?secret=INIT_DB")
    
    try:
        from database.models import Base, get_engine, get_session, Product, Supplier
        from database.setup import seed_data
        from pathlib import Path
        
        db_path = Path("database/spherecast.db")
        
        # Get engine
        engine = get_engine(str(db_path))
        
        # FIRST: Create tables (this is safe to call multiple times - it won't drop existing data)
        Base.metadata.create_all(engine)
        
        # THEN: Check if database already has data
        session = get_session(engine)
        existing_products = session.query(Product).count()
        
        if existing_products > 0:
            session.close()
            return {
                "success": False,
                "message": f"Database already has {existing_products} products. Not reinitializing.",
                "hint": "Delete the database file manually if you want to reset."
            }
        
        # Seed data
        seed_data(session)
        session.close()
        
        # Also initialize audit database
        from audit.update_tracker import Base as AuditBase
        audit_engine = get_engine("database/audit.db")
        AuditBase.metadata.create_all(audit_engine)
        
        return {
            "success": True,
            "message": "Database initialized with tables and seed data!",
            "tables_created": ["product", "supplier", "supplier_product", "purchase_order", "purchase_order_line"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {str(e)}")


def process_in_background(extraction_id: int, email_body: str, extracted_data: dict, document_path: str):
    """
    Background task: Process with Master LLM.
    Runs asynchronously so frontend can show extraction immediately.
    """
    try:
        # Update status to "processing"
        get_orchestrator().audit.update_processing_status(extraction_id, "processing")
        
        # Run Master LLM reasoning
        result = get_orchestrator()._process_automatically(
            email_body=email_body,
            extracted_data=extracted_data,
            extraction_id=extraction_id,
            document_path=document_path,
            verbose=True  # Show in terminal
        )
        
        # Update with result
        get_orchestrator().audit.update_processing_result(extraction_id, {
            "status": "auto_processed",
            "result": result
        })
        get_orchestrator().audit.update_processing_status(extraction_id, "completed")
        
        print(f"\n✓ Background processing completed for extraction #{extraction_id}")
        
    except Exception as e:
        print(f"\n✗ Background processing failed for extraction #{extraction_id}: {e}")
        get_orchestrator().audit.update_processing_status(extraction_id, "failed")
        get_orchestrator().audit.update_processing_result(extraction_id, {
            "status": "failed",
            "error": str(e)
        })


@app.post("/api/process-email")
async def process_email_file(
    email_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Process an .eml file containing email body and document attachment.
    
    Args:
        email_file: .eml file with email and attachment
        
    Returns:
        Extraction result with status and confidence
    """
    
    try:
        # Read the .eml file
        eml_content = await email_file.read()
        
        # Parse the email
        msg = BytesParser(policy=policy.default).parsebytes(eml_content)
        
        # Extract email metadata
        email_id = msg.get('Message-ID', f"email-{uuid.uuid4().hex[:8]}")
        email_subject = msg.get('Subject', 'No Subject')
        email_from = msg.get('From', 'Unknown')
        
        # Extract email body
        email_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and not part.get_filename():
                    email_body = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            email_body = msg.get_payload(decode=True).decode(errors='ignore')
        
        # Find and extract the attachment (PO document)
        document_path = None
        for part in msg.walk():
            filename = part.get_filename()
            if filename and any(filename.lower().endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp']):
                # Save attachment
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_filename = f"{timestamp}_{filename}"
                file_path = UPLOAD_DIR / safe_filename
                
                with open(file_path, "wb") as f:
                    f.write(part.get_payload(decode=True))
                
                document_path = str(file_path)
                break
        
        if not document_path:
            raise HTTPException(
                status_code=400,
                detail="No document attachment found in email. Please ensure the email contains a PDF or image attachment."
            )
        
        # Extract and verify document (fast - returns immediately)
        full_email_body = f"From: {email_from}\nSubject: {email_subject}\n\n{email_body}"
        
        extraction_result = get_orchestrator().extractor.extract_with_verification(
            document_path=document_path,
            verbose=False
        )
        
        # Log to audit
        extraction_id = get_orchestrator().audit.log_extraction(
            email_id=email_id,
            document_path=document_path,
            extraction_result=extraction_result
        )
        
        confidence = extraction_result["confidence"]
        verified = extraction_result["verified"]
        
        # Determine if should auto-process
        should_auto_process = (
            confidence >= get_orchestrator().AUTO_PROCESS_THRESHOLD and verified
        )
        
        # Return immediately with extraction results
        response_data = {
            "success": True,
            "extraction_id": extraction_id,
            "confidence": confidence,
            "verified": verified,
            "status": "processing" if should_auto_process else "pending_review",
            "message": "Extraction complete. Master LLM processing in background..." if should_auto_process else "Extraction complete. Queued for review.",
            "email_info": {
                "from": email_from,
                "subject": email_subject,
                "message_id": email_id
            }
        }
        
        # Start Master LLM processing in background if high confidence
        if should_auto_process and background_tasks:
            background_tasks.add_task(
                process_in_background,
                extraction_id,
                full_email_body,
                extraction_result["data"],
                document_path
            )
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        # Log full error for debugging
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR processing email:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Failed to process email: {str(e)}")


@app.post("/api/process")
async def process_document(
    email_id: str = Form(...),
    email_body: str = Form(...),
    document: UploadFile = File(...)
):
    """
    Process an email with attached document (legacy endpoint).
    
    Args:
        email_id: Unique identifier for the email
        email_body: Email text content
        document: Attached document file (PDF/image)
        
    Returns:
        Extraction result with status and confidence
    """
    
    try:
        # Save uploaded document
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{document.filename}"
        file_path = UPLOAD_DIR / filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(document.file, buffer)
        
        # Process document
        result = get_orchestrator().process_email_with_document(
            email_id=email_id,
            email_body=email_body,
            document_path=str(file_path),
            verbose=False  # Don't print to console in API
        )
        
        return JSONResponse(content={
            "success": True,
            "result": result
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/extractions")
async def get_all_extractions(limit: int = 100):
    """
    Get all extractions from the audit database.
    
    Args:
        limit: Maximum number of extractions to return
        
    Returns:
        List of all extractions
    """
    
    try:
        extractions = get_orchestrator().audit.get_all_extractions(limit=limit)
        return {
            "success": True,
            "count": len(extractions),
            "extractions": extractions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/extraction/{extraction_id}")
async def get_extraction(extraction_id: int):
    """
    Get complete details of a specific extraction.
    
    Includes:
    - Extraction data
    - Verification report
    - Processing result with reasoning trail
    - Database updates made
    
    Args:
        extraction_id: Database ID of the extraction
        
    Returns:
        Complete extraction details for frontend display
    """
    
    try:
        extraction = get_orchestrator().audit.get_extraction(extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        
        # Get database updates for this extraction
        updates = get_update_tracker().get_updates_for_extraction(extraction_id)
        
        # Add database updates to response
        extraction['database_updates'] = [
            {
                "id": u.id,
                "table": u.table_name,
                "record_id": u.record_id,
                "operation": u.operation,
                "field": u.field_name,
                "old_value": u.old_value,
                "new_value": u.new_value,
                "confidence": u.confidence,
                "llm_reasoning": u.llm_reasoning,
                "requires_approval": u.requires_approval,
                "approved": u.approved
            }
            for u in updates
        ]
        
        return {
            "success": True,
            "extraction": extraction
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/review-queue")
async def get_review_queue(priority: Optional[str] = None):
    """
    Get items in the review queue.
    
    Args:
        priority: Optional filter by priority (high/medium/low)
        
    Returns:
        List of items awaiting review
    """
    
    try:
        queue = get_orchestrator().get_review_queue(priority=priority)
        return {
            "success": True,
            "count": len(queue),
            "items": queue
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/statistics")
async def get_statistics(days: int = 7):
    """
    Get processing statistics.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Statistics including success rates, confidence levels, etc.
    """
    
    try:
        stats = get_orchestrator().get_statistics(days=days)
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/approve/{extraction_id}")
async def approve_extraction(extraction_id: int):
    """
    Approve an extraction that was queued for review.
    
    Args:
        extraction_id: Database ID of the extraction
        
    Returns:
        Processing result
    """
    
    try:
        # TODO: Implement approval workflow
        return {
            "success": True,
            "extraction_id": extraction_id,
            "message": "Approval workflow to be implemented"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/document/{extraction_id}")
async def get_document(extraction_id: int):
    """
    Get the document image/PDF for preview.
    
    Args:
        extraction_id: Database ID of the extraction
        
    Returns:
        Document file
    """
    from fastapi.responses import FileResponse
    
    try:
        extraction = get_orchestrator().audit.get_extraction(extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        
        document_path = Path(extraction["document_path"])
        
        # Check if file exists
        if not document_path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")
        
        # Determine media type
        suffix = document_path.suffix.lower()
        media_type_map = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        media_type = media_type_map.get(suffix, 'application/octet-stream')
        
        return FileResponse(
            path=str(document_path),
            media_type=media_type,
            filename=document_path.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATABASE ENDPOINTS (Production Database)
# ============================================================================

@app.get("/api/database/purchase-orders")
async def get_purchase_orders(limit: int = 100):
    """
    Get all purchase orders from the production database.
    
    Args:
        limit: Maximum number of records to return
        
    Returns:
        List of purchase orders (raw data only, no joins)
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            purchase_orders = session.query(PurchaseOrder)\
                .order_by(PurchaseOrder.id)\
                .limit(limit)\
                .all()
            
            results = []
            for po in purchase_orders:
                results.append({
                    "id": po.id,
                    "reference_num": po.reference_num,
                    "supplier_id": po.supplier_id,
                    "delivery_date": po.delivery_date.isoformat() if po.delivery_date else None
                })
            
            return {
                "success": True,
                "count": len(results),
                "purchase_orders": results
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/purchase-orders/{po_id}")
async def get_purchase_order_details(po_id: int):
    """
    Get detailed purchase order with line items.
    
    Args:
        po_id: Purchase Order ID
        
    Returns:
        Purchase order with all line items (raw data only, no joins)
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            po = session.query(PurchaseOrder).get(po_id)
            
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            
            line_items = []
            for line in po.lines:
                line_items.append({
                    "id": line.id,
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                    "delivery_date": line.delivery_date.isoformat() if line.delivery_date else None,
                    "unit_price": line.unit_price,
                    "total_price": line.total_price,
                    "notes": line.notes
                })
            
            result = {
                "id": po.id,
                "reference_num": po.reference_num,
                "supplier_id": po.supplier_id,
                "delivery_date": po.delivery_date.isoformat() if po.delivery_date else None,
                "external_reference": po.external_reference,
                "terms": po.terms,
                "notes": po.notes,
                "line_items": line_items
            }
            
            return {
                "success": True,
                "purchase_order": result
            }
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/products")
async def get_products(limit: int = 100):
    """
    Get all products from the production database.
    
    Args:
        limit: Maximum number of records to return
        
    Returns:
        List of products
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            products = session.query(Product)\
                .order_by(Product.sku)\
                .limit(limit)\
                .all()
            
            results = []
            for product in products:
                results.append({
                    "id": product.id,
                    "sku": product.sku,
                    "title": product.title
                })
            
            return {
                "success": True,
                "count": len(results),
                "products": results
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/suppliers")
async def get_suppliers(limit: int = 100):
    """
    Get all suppliers from the production database.
    
    Args:
        limit: Maximum number of records to return
        
    Returns:
        List of suppliers
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            suppliers = session.query(Supplier)\
                .order_by(Supplier.name)\
                .limit(limit)\
                .all()
            
            results = []
            for supplier in suppliers:
                results.append({
                    "id": supplier.id,
                    "name": supplier.name,
                    "email": supplier.email
                })
            
            return {
                "success": True,
                "count": len(results),
                "suppliers": results
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/purchase-order-lines")
async def get_purchase_order_lines(limit: int = 100, po_id: Optional[int] = None):
    """
    Get all purchase order lines or filter by PO ID.
    
    Args:
        limit: Maximum number of records to return
        po_id: Optional filter by purchase order ID
        
    Returns:
        List of purchase order lines (raw data only, no joins)
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            query = session.query(PurchaseOrderLine)
            
            if po_id:
                query = query.filter(PurchaseOrderLine.purchase_order_id == po_id)
            
            lines = query.order_by(PurchaseOrderLine.id).limit(limit).all()
            
            results = []
            for line in lines:
                results.append({
                    "id": line.id,
                    "purchase_order_id": line.purchase_order_id,
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                    "delivery_date": line.delivery_date.isoformat() if line.delivery_date else None,
                    "unit_price": line.unit_price,
                    "total_price": line.total_price,
                    "notes": line.notes
                })
            
            return {
                "success": True,
                "count": len(results),
                "purchase_order_lines": results
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/supplier-products")
async def get_supplier_products(limit: int = 100, supplier_id: Optional[int] = None):
    """
    Get all supplier-product mappings or filter by supplier ID.
    
    Args:
        limit: Maximum number of records to return
        supplier_id: Optional filter by supplier ID
        
    Returns:
        List of supplier products
    """
    try:
        engine = get_engine("database/spherecast.db")
        session = get_session(engine)
        
        try:
            query = session.query(SupplierProduct)
            
            if supplier_id:
                query = query.filter(SupplierProduct.supplier_id == supplier_id)
            
            supplier_products = query.limit(limit).all()
            
            results = []
            for sp in supplier_products:
                results.append({
                    "supplier_id": sp.supplier_id,
                    "product_id": sp.product_id,
                    "supplier_sku": sp.supplier_sku,
                    "price_per_unit": sp.price_per_unit
                })
            
            return {
                "success": True,
                "count": len(results),
                "supplier_products": results
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UPDATE TRACKING ENDPOINTS (For UI Feature: View Source Document for Changes)
# ============================================================================

@app.get("/api/updates/extraction/{extraction_id}")
async def get_updates_for_extraction(extraction_id: int):
    """
    Get all database updates from a specific extraction.
    Shows what changes were made to which tables.
    
    Args:
        extraction_id: Extraction ID
        
    Returns:
        List of database updates with details
    """
    try:
        updates = get_update_tracker().get_updates_for_extraction(extraction_id)
        
        return {
            "success": True,
            "extraction_id": extraction_id,
            "total_updates": len(updates),
            "updates": [
                {
                    "id": u.id,
                    "table": u.table_name,
                    "record_id": u.record_id,
                    "operation": u.operation,
                    "field": u.field_name,
                    "old_value": u.old_value,
                    "new_value": u.new_value,
                    "confidence": u.confidence,
                    "timestamp": u.timestamp.isoformat(),
                    "requires_approval": u.requires_approval,
                    "approved": u.approved
                }
                for u in updates
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/update/{update_id}")
async def get_update_details(update_id: int):
    """
    Get detailed information about a specific database update.
    
    Includes:
    - What changed (table, field, old/new values)
    - Why it changed (LLM reasoning)
    - Source document info
    - Approval status
    
    This powers the UI feature where users click on updates to see source documents.
    
    Args:
        update_id: Update ID
        
    Returns:
        Complete update details
    """
    try:
        update = get_update_tracker().get_update_details(update_id)
        
        if not update:
            raise HTTPException(status_code=404, detail="Update not found")
        
        return {
            "success": True,
            "update": {
                "id": update.id,
                "extraction_id": update.extraction_id,
                "timestamp": update.timestamp.isoformat(),
                "table": update.table_name,
                "record_id": update.record_id,
                "operation": update.operation,
                "field": update.field_name,
                "old_value": update.old_value,
                "new_value": update.new_value,
                "source_document": update.source_document_path,
                "source_field": update.source_field,
                "source_value": update.source_value,
                "llm_reasoning": update.llm_reasoning,
                "confidence": update.confidence,
                "requires_approval": update.requires_approval,
                "approved": update.approved,
                "approved_by": update.approved_by,
                "approved_at": update.approved_at.isoformat() if update.approved_at else None,
                "review_notes": update.review_notes
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/updates/pending")
async def get_pending_approvals():
    """
    Get all updates awaiting approval.
    
    Returns:
        List of updates needing human review
    """
    try:
        updates = get_update_tracker().get_pending_approvals()
        
        return {
            "success": True,
            "total": len(updates),
            "updates": [
                {
                    "id": u.id,
                    "extraction_id": u.extraction_id,
                    "table": u.table_name,
                    "record_id": u.record_id,
                    "operation": u.operation,
                    "field": u.field_name,
                    "new_value": u.new_value,
                    "confidence": u.confidence,
                    "timestamp": u.timestamp.isoformat(),
                    "llm_reasoning": u.llm_reasoning
                }
                for u in updates
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update/{update_id}/approve")
async def approve_update(update_id: int, approver: str = Form(...), notes: str = Form(None)):
    """
    Approve a database update.
    
    Args:
        update_id: Update ID
        approver: Name/ID of approver
        notes: Optional approval notes
        
    Returns:
        Success confirmation
    """
    try:
        get_update_tracker().approve_update(update_id, approver, notes)
        
        return {
            "success": True,
            "update_id": update_id,
            "message": "Update approved"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update/{update_id}/reject")
async def reject_update(update_id: int, reviewer: str = Form(...), reason: str = Form(...)):
    """
    Reject a database update.
    
    Args:
        update_id: Update ID
        reviewer: Name/ID of reviewer
        reason: Reason for rejection
        
    Returns:
        Success confirmation
    """
    try:
        get_update_tracker().reject_update(update_id, reviewer, reason)
        
        return {
            "success": True,
            "update_id": update_id,
            "message": "Update rejected"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATABASE CHANGE TRACKING ENDPOINTS (For "View Change" Feature)
# ============================================================================

@app.get("/api/database/{table_name}/changes")
async def get_table_changes(table_name: str, limit: int = 100):
    """
    Get all recent changes for a specific database table.
    Returns changes grouped by record_id for easy display in UI.
    
    Args:
        table_name: Name of the table (purchase_order, product, supplier, etc.)
        limit: Maximum number of changes to return
        
    Returns:
        Dictionary mapping record_id to list of changes
    """
    try:
        from sqlalchemy import desc
        from sqlalchemy.orm import Session as SQLSession
        from audit.update_tracker import DatabaseUpdate, Base
        
        session = SQLSession(get_update_tracker().engine)
        
        try:
            # Get all updates for this table
            updates = session.query(DatabaseUpdate).filter(
                DatabaseUpdate.table_name == table_name
            ).order_by(desc(DatabaseUpdate.timestamp)).limit(limit).all()
            
            # Group by record_id
            changes_by_record = {}
            for u in updates:
                record_id = u.record_id
                if record_id not in changes_by_record:
                    changes_by_record[record_id] = []
                
                changes_by_record[record_id].append({
                    "id": u.id,
                    "extraction_id": u.extraction_id,
                    "timestamp": u.timestamp.isoformat() if u.timestamp else None,
                    "operation": u.operation,
                    "field": u.field_name,
                    "old_value": u.old_value,
                    "new_value": u.new_value,
                    "source_document": u.source_document_path,
                    "source_field": u.source_field,
                    "source_value": u.source_value,
                    "llm_reasoning": u.llm_reasoning,
                    "confidence": u.confidence,
                    "requires_approval": u.requires_approval,
                    "approved": u.approved
                })
            
            return {
                "success": True,
                "table": table_name,
                "total_records_with_changes": len(changes_by_record),
                "changes": changes_by_record
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/{table_name}/{record_id}/changes")
async def get_record_changes(table_name: str, record_id: str):
    """
    Get all changes for a specific record in a table.
    
    Args:
        table_name: Name of the table
        record_id: ID of the record
        
    Returns:
        List of all changes made to this record with source document info
    """
    try:
        from sqlalchemy import desc
        from sqlalchemy.orm import Session as SQLSession
        from audit.update_tracker import DatabaseUpdate
        
        session = SQLSession(get_update_tracker().engine)
        
        try:
            updates = session.query(DatabaseUpdate).filter(
                DatabaseUpdate.table_name == table_name,
                DatabaseUpdate.record_id == record_id
            ).order_by(desc(DatabaseUpdate.timestamp)).all()
            
            changes = []
            for u in updates:
                # Get extraction details if available
                extraction_data = None
                if u.extraction_id:
                    extraction = get_orchestrator().audit.get_extraction(u.extraction_id)
                    if extraction:
                        extraction_data = {
                            "id": extraction.get("id"),
                            "document_path": extraction.get("document_path"),
                            "confidence": extraction.get("confidence"),
                            "verified": extraction.get("verified"),
                            "extraction_result": extraction.get("extraction_result")
                        }
                
                changes.append({
                    "id": u.id,
                    "extraction_id": u.extraction_id,
                    "timestamp": u.timestamp.isoformat() if u.timestamp else None,
                    "operation": u.operation,
                    "field": u.field_name,
                    "old_value": u.old_value,
                    "new_value": u.new_value,
                    "source_document": u.source_document_path,
                    "source_field": u.source_field,
                    "source_value": u.source_value,
                    "llm_reasoning": u.llm_reasoning,
                    "confidence": u.confidence,
                    "requires_approval": u.requires_approval,
                    "approved": u.approved,
                    "extraction": extraction_data
                })
            
            return {
                "success": True,
                "table": table_name,
                "record_id": record_id,
                "total_changes": len(changes),
                "changes": changes
            }
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/document-by-path")
async def get_document_by_path(path: str):
    """
    Get a document file by its path.
    Used by the source document viewer.
    
    Args:
        path: Path to the document file
        
    Returns:
        Document file
    """
    from fastapi.responses import FileResponse
    
    try:
        document_path = Path(path)
        
        # Security check - only allow files in uploads or audit_storage
        allowed_dirs = [
            Path("uploads").resolve(),
            Path("audit_storage").resolve()
        ]
        
        doc_resolved = document_path.resolve()
        is_allowed = any(
            str(doc_resolved).startswith(str(allowed_dir)) 
            for allowed_dir in allowed_dirs
        )
        
        if not is_allowed:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not document_path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")
        
        # Determine media type
        suffix = document_path.suffix.lower()
        media_type_map = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        media_type = media_type_map.get(suffix, 'application/octet-stream')
        
        return FileResponse(
            path=str(document_path),
            media_type=media_type,
            filename=document_path.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STATIC FILE SERVING (Production - serve frontend from backend)
# ============================================================================

# Check if frontend build exists
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    
    # Serve index.html at root
    @app.get("/")
    async def serve_root():
        """Serve the React SPA at root."""
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
        return {"status": "ok", "service": "SphereCast API", "version": "0.1.0"}
    
    # Serve index.html for all non-API routes (SPA fallback)
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the React SPA for all non-API routes."""
        # Skip if it's an API route
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        # Serve index.html for SPA routing
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    # Fallback if frontend not built - show API health check
    @app.get("/")
    async def root_fallback():
        """API health check when frontend not available."""
        return {"status": "ok", "service": "SphereCast API", "version": "0.1.0", "note": "Frontend not built"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

