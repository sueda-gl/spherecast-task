"""
FastAPI backend to expose SphereCast extraction functionality.

Provides REST endpoints for:
- Email (.eml) upload and processing
- Extraction status and results
- Review queue management
- Statistics and audit trail
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite and common dev ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator and update tracker
orchestrator = UniversalOrchestrator(
    api_key=os.getenv("OPENAI_API_KEY"),
    audit_db="database/audit.db",
    model="gpt-4o",
    database_path="database/spherecast.db"
)

# Initialize update tracker for API queries
update_tracker = UpdateAuditTracker(db_path="database/audit.db")

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/")
async def root():
    """API health check."""
    return {"status": "ok", "service": "SphereCast API", "version": "0.1.0"}


def process_in_background(extraction_id: int, email_body: str, extracted_data: dict, document_path: str):
    """
    Background task: Process with Master LLM.
    Runs asynchronously so frontend can show extraction immediately.
    """
    try:
        # Update status to "processing"
        orchestrator.audit.update_processing_status(extraction_id, "processing")
        
        # Run Master LLM reasoning
        result = orchestrator._process_automatically(
            email_body=email_body,
            extracted_data=extracted_data,
            extraction_id=extraction_id,
            document_path=document_path,
            verbose=True  # Show in terminal
        )
        
        # Update with result
        orchestrator.audit.update_processing_result(extraction_id, {
            "status": "auto_processed",
            "result": result
        })
        orchestrator.audit.update_processing_status(extraction_id, "completed")
        
        print(f"\n✓ Background processing completed for extraction #{extraction_id}")
        
    except Exception as e:
        print(f"\n✗ Background processing failed for extraction #{extraction_id}: {e}")
        orchestrator.audit.update_processing_status(extraction_id, "failed")
        orchestrator.audit.update_processing_result(extraction_id, {
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
        
        extraction_result = orchestrator.extractor.extract_with_verification(
            document_path=document_path,
            verbose=False
        )
        
        # Log to audit
        extraction_id = orchestrator.audit.log_extraction(
            email_id=email_id,
            document_path=document_path,
            extraction_result=extraction_result
        )
        
        confidence = extraction_result["confidence"]
        verified = extraction_result["verified"]
        
        # Determine if should auto-process
        should_auto_process = (
            confidence >= orchestrator.AUTO_PROCESS_THRESHOLD and verified
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
        result = orchestrator.process_email_with_document(
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
        extractions = orchestrator.audit.get_all_extractions(limit=limit)
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
        extraction = orchestrator.audit.get_extraction(extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        
        # Get database updates for this extraction
        updates = update_tracker.get_updates_for_extraction(extraction_id)
        
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
        queue = orchestrator.get_review_queue(priority=priority)
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
        stats = orchestrator.get_statistics(days=days)
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
        extraction = orchestrator.audit.get_extraction(extraction_id)
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
        updates = update_tracker.get_updates_for_extraction(extraction_id)
        
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
        update = update_tracker.get_update_details(update_id)
        
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
        updates = update_tracker.get_pending_approvals()
        
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
        update_tracker.approve_update(update_id, approver, notes)
        
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
        update_tracker.reject_update(update_id, reviewer, reason)
        
        return {
            "success": True,
            "update_id": update_id,
            "message": "Update rejected"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

