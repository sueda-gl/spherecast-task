"""
Audit system for tracking extractions and verifications.

Stores complete audit trail for every document processed.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, Text
from sqlalchemy.orm import declarative_base, Session
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import hashlib
import shutil

Base = declarative_base()


class ExtractionLog(Base):
    """Audit log for document extractions."""
    __tablename__ = 'extraction_audit'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Document information
    email_id = Column(String, nullable=False, index=True)
    document_path = Column(Text, nullable=False)
    document_hash = Column(String(64))  # SHA256 for integrity verification
    
    # Extraction results (JSON)
    raw_extraction = Column(Text)  # Full extraction JSON
    verification_report = Column(Text)  # Full verification JSON
    
    # Key metrics
    verified = Column(Boolean)
    confidence = Column(Float)
    issues_count = Column(Integer, default=0)
    
    # Processing status
    requires_review = Column(Boolean, default=False)
    review_priority = Column(String(20))  # 'high', 'medium', 'low'
    processing_status = Column(String(20), default="extracted")  # 'extracted', 'processing', 'completed', 'failed'
    processed = Column(Boolean, default=False)
    processing_result = Column(Text)  # JSON - what happened after extraction
    processing_timestamp = Column(DateTime)
    
    # Review tracking (for human-in-the-loop)
    reviewed_by = Column(String(100))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)


class ExtractionAudit:
    """
    Simple audit system for extraction tracking.
    
    Logs every extraction with full details for:
    - Debugging extraction issues
    - Compliance/audit trail
    - Performance monitoring
    - Training data collection
    """
    
    def __init__(self, db_path: str = "audit.db", storage_dir: str = "./audit_storage"):
        """
        Initialize audit system.
        
        Args:
            db_path: Path to SQLite database
            storage_dir: Directory to store original documents
        """
        # Ensure the database path is absolute and the directory exists
        db_path = Path(db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create engine with proper SQLite connection parameters
        self.engine = create_engine(
            f"sqlite:///{db_path}", 
            echo=False,
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def log_extraction(
        self,
        email_id: str,
        document_path: str,
        extraction_result: Dict[str, Any]
    ) -> int:
        """
        Log extraction result to audit database.
        
        Args:
            email_id: Unique email identifier
            document_path: Path to original document
            extraction_result: Full result from ExtractAndVerify
            
        Returns:
            extraction_id for reference
        """
        
        # Store original document
        stored_path = self._store_document(document_path, email_id)
        
        # Calculate metrics
        confidence = extraction_result.get("confidence", 0.0)
        verified = extraction_result.get("verified", False)
        issues = extraction_result.get("issues", [])
        
        # Determine if review is needed
        requires_review = not verified or confidence < 0.85
        
        # Calculate priority
        if confidence < 0.5 or len(issues) > 3:
            priority = "high"
        elif confidence < 0.75 or len(issues) > 0:
            priority = "medium"
        else:
            priority = "low"
        
        # Create log entry
        log_entry = ExtractionLog(
            email_id=email_id,
            document_path=stored_path,
            document_hash=self._hash_file(document_path),
            raw_extraction=json.dumps(extraction_result.get("raw_extraction", {})),
            verification_report=json.dumps(extraction_result.get("verification_report", {})),
            verified=verified,
            confidence=confidence,
            issues_count=len(issues),
            requires_review=requires_review,
            review_priority=priority if requires_review else None
        )
        
        # Save to database
        session = Session(self.engine)
        try:
            session.add(log_entry)
            session.commit()
            extraction_id = log_entry.id
            return extraction_id
        finally:
            session.close()
    
    def update_processing_status(
        self,
        extraction_id: int,
        status: str
    ):
        """
        Update processing status.
        
        Args:
            extraction_id: ID from log_extraction
            status: New status ('extracted', 'processing', 'completed', 'failed')
        """
        session = Session(self.engine)
        try:
            log_entry = session.query(ExtractionLog).get(extraction_id)
            if log_entry:
                log_entry.processing_status = status
                session.commit()
        finally:
            session.close()
    
    def update_processing_result(
        self, 
        extraction_id: int, 
        result: Dict[str, Any]
    ):
        """
        Update extraction record with processing result.
        
        Args:
            extraction_id: ID from log_extraction
            result: Processing result (what was done with the extraction)
        """
        session = Session(self.engine)
        try:
            log_entry = session.query(ExtractionLog).get(extraction_id)
            if log_entry:
                log_entry.processed = True
                log_entry.processing_status = "completed" if result.get("status") == "auto_processed" else log_entry.processing_status
                log_entry.processing_result = json.dumps(result)
                log_entry.processing_timestamp = datetime.utcnow()
                session.commit()
        finally:
            session.close()
    
    def get_review_queue(
        self, 
        priority: Optional[str] = None,
        limit: int = 50
    ) -> List[ExtractionLog]:
        """
        Get items that need human review.
        
        Args:
            priority: Filter by priority ('high', 'medium', 'low')
            limit: Max items to return
            
        Returns:
            List of ExtractionLog entries needing review
        """
        session = Session(self.engine)
        try:
            query = session.query(ExtractionLog).filter(
                ExtractionLog.requires_review == True,
                ExtractionLog.processed == False,
                ExtractionLog.reviewed_by == None
            )
            
            if priority:
                query = query.filter(ExtractionLog.review_priority == priority)
            
            results = query.order_by(
                ExtractionLog.review_priority.desc(),
                ExtractionLog.timestamp.desc()
            ).limit(limit).all()
            
            return results
        finally:
            session.close()
    
    def mark_reviewed(
        self,
        extraction_id: int,
        reviewer: str,
        notes: Optional[str] = None
    ):
        """
        Mark an extraction as reviewed by human.
        
        Args:
            extraction_id: ID of extraction
            reviewer: Name/ID of reviewer
            notes: Optional review notes
        """
        session = Session(self.engine)
        try:
            log_entry = session.query(ExtractionLog).get(extraction_id)
            if log_entry:
                log_entry.reviewed_by = reviewer
                log_entry.reviewed_at = datetime.utcnow()
                log_entry.review_notes = notes
                session.commit()
        finally:
            session.close()
    
    def get_all_extractions(self, limit: int = 100) -> list:
        """
        Get all extractions from the database.
        
        Args:
            limit: Maximum number of extractions to return
            
        Returns:
            List of extraction records
        """
        
        session = Session(self.engine)
        try:
            logs = session.query(ExtractionLog).order_by(
                ExtractionLog.timestamp.desc()
            ).limit(limit).all()
            
            extractions = []
            for log in logs:
                # Combine extraction and verification into a complete result
                extraction_data = json.loads(log.raw_extraction) if log.raw_extraction else {}
                verification_data = json.loads(log.verification_report) if log.verification_report else {}
                
                extraction = {
                    "id": log.id,
                    "email_id": log.email_id,
                    "document_path": log.document_path,
                    "confidence": log.confidence,
                    "verified": log.verified,
                    "status": "auto_processed" if log.processed else ("pending_review" if log.requires_review else "requires_manual"),
                    "created_at": log.timestamp.isoformat() if log.timestamp else None,
                    "extraction_result": extraction_data,
                    "verification_report": verification_data,
                    "processing_result": json.loads(log.processing_result) if log.processing_result else None,
                    # Audit trail specific fields
                    "document_hash": log.document_hash,
                    "issues_count": log.issues_count,
                    "review_priority": log.review_priority,
                    "reviewed_by": log.reviewed_by,
                    "reviewed_at": log.reviewed_at.isoformat() if log.reviewed_at else None,
                }
                extractions.append(extraction)
            
            return extractions
        finally:
            session.close()
    
    def get_extraction(self, extraction_id: int) -> dict:
        """
        Get a specific extraction by ID.
        
        Args:
            extraction_id: The extraction ID
            
        Returns:
            Extraction record or None if not found
        """
        
        session = Session(self.engine)
        try:
            log = session.query(ExtractionLog).get(extraction_id)
            if not log:
                return None
            
            # Combine extraction and verification into a complete result
            extraction_data = json.loads(log.raw_extraction) if log.raw_extraction else {}
            verification_data = json.loads(log.verification_report) if log.verification_report else {}
            
            return {
                "id": log.id,
                "email_id": log.email_id,
                "document_path": log.document_path,
                "confidence": log.confidence,
                "verified": log.verified,
                "status": "auto_processed" if log.processed else ("pending_review" if log.requires_review else "requires_manual"),
                "processing_status": log.processing_status,  # 'extracted', 'processing', 'completed', 'failed'
                "created_at": log.timestamp.isoformat() if log.timestamp else None,
                "extraction_result": extraction_data,
                "verification_report": verification_data,
                "processing_result": json.loads(log.processing_result) if log.processing_result else None,
                # Audit trail specific fields
                "document_hash": log.document_hash,
                "issues_count": log.issues_count,
                "review_priority": log.review_priority,
                "reviewed_by": log.reviewed_by,
                "reviewed_at": log.reviewed_at.isoformat() if log.reviewed_at else None,
                "review_notes": log.review_notes,
            }
        finally:
            session.close()
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get extraction statistics for monitoring.
        
        Args:
            days: Look back this many days
            
        Returns:
            Statistics dict
        """
        from sqlalchemy import func
        from datetime import timedelta
        
        session = Session(self.engine)
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            query = session.query(ExtractionLog).filter(
                ExtractionLog.timestamp >= cutoff
            )
            
            total = query.count()
            verified = query.filter(ExtractionLog.verified == True).count()
            needs_review = query.filter(ExtractionLog.requires_review == True).count()
            processed = query.filter(ExtractionLog.processed == True).count()
            
            avg_confidence = session.query(
                func.avg(ExtractionLog.confidence)
            ).filter(
                ExtractionLog.timestamp >= cutoff
            ).scalar() or 0.0
            
            return {
                "period_days": days,
                "total_extractions": total,
                "verified_count": verified,
                "verification_rate": verified / total if total > 0 else 0,
                "needs_review": needs_review,
                "processed": processed,
                "average_confidence": float(avg_confidence),
                "pending_review": needs_review - processed
            }
        finally:
            session.close()
    
    def _store_document(self, document_path: str, email_id: str) -> str:
        """
        Store document in permanent audit storage.
        
        Args:
            document_path: Original document path
            email_id: Email ID for organization
            
        Returns:
            Path to stored document
        """
        doc_path = Path(document_path)
        if not doc_path.exists():
            return document_path  # Return original path if file doesn't exist
        
        # Create timestamped filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        stored_filename = f"{email_id}_{timestamp}_{doc_path.name}"
        stored_path = self.storage_dir / stored_filename
        
        # Copy file to audit storage
        shutil.copy2(doc_path, stored_path)
        
        return str(stored_path)
    
    def _hash_file(self, file_path: str) -> str:
        """
        Calculate SHA256 hash of file for integrity verification.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex digest of SHA256 hash
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return ""
        
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks for large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest()

