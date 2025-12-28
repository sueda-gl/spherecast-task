"""
Update Audit Tracker - Tracks every database change with source traceability.

Enables the UI feature: click any update to see the source document section that caused it.
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, Session
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

Base = declarative_base()


class DatabaseUpdate(Base):
    """
    Tracks every database change made by the system.
    Links back to source document for complete traceability.
    """
    __tablename__ = 'database_updates'
    
    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer)  # Links to extraction_audit table
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # What changed
    table_name = Column(String, nullable=False, index=True)
    record_id = Column(Integer, nullable=False)
    operation = Column(String, nullable=False)  # 'create', 'update', 'delete'
    field_name = Column(String)  # Specific field for updates
    
    # Change details
    old_value = Column(Text)  # JSON
    new_value = Column(Text)  # JSON
    
    # Source traceability (KEY FEATURE)
    source_document_path = Column(Text)  # Original document
    source_field = Column(Text)  # Which field in extraction caused this
    source_value = Column(Text)  # Actual value from document
    
    # LLM decision context
    llm_reasoning = Column(Text)  # Why this change was made
    confidence = Column(Float)  # LLM confidence in this decision
    
    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approved = Column(Boolean)  # null=pending, True=approved, False=rejected
    approved_by = Column(String)
    approved_at = Column(DateTime)
    review_notes = Column(Text)


class UpdateAuditTracker:
    """
    Tracks and logs all database changes for audit trail and UI visualization.
    """
    
    def __init__(self, db_path: str = "database/audit.db"):
        """
        Initialize tracker.
        
        Args:
            db_path: Path to audit database
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
    
    def log_operation(
        self,
        extraction_id: int,
        operation_result: Dict[str, Any],
        source_document_path: str,
        llm_reasoning: str,
        confidence: float
    ) -> int:
        """
        Log a database operation to audit trail.
        
        Args:
            extraction_id: ID from extraction_audit
            operation_result: Result from database tool (create_record, update_record, etc.)
            source_document_path: Path to original document
            llm_reasoning: LLM's explanation for this change
            confidence: Confidence score
            
        Returns:
            update_id
        """
        
        if not operation_result.get("success"):
            return None  # Don't log failed operations
        
        table = operation_result.get("table")
        record_id = operation_result.get("record_id")
        operation = operation_result.get("operation")
        
        session = Session(self.engine)
        
        try:
            if operation == "create":
                # Log creation
                update = DatabaseUpdate(
                    extraction_id=extraction_id,
                    table_name=table,
                    record_id=record_id,
                    operation="create",
                    new_value=json.dumps(operation_result.get("record")),
                    source_document_path=source_document_path,
                    llm_reasoning=llm_reasoning,
                    confidence=confidence,
                    requires_approval=confidence < 0.9
                )
                session.add(update)
                session.commit()
                update_id = update.id
                
            elif operation == "update":
                # Log each field that changed
                changes = operation_result.get("changes", {})
                update_ids = []
                
                for field, change in changes.items():
                    update = DatabaseUpdate(
                        extraction_id=extraction_id,
                        table_name=table,
                        record_id=record_id,
                        operation="update",
                        field_name=field,
                        old_value=json.dumps(change.get("old")),
                        new_value=json.dumps(change.get("new")),
                        source_document_path=source_document_path,
                        source_field=field,
                        llm_reasoning=llm_reasoning,
                        confidence=confidence,
                        requires_approval=confidence < 0.9
                    )
                    session.add(update)
                    session.commit()
                    update_ids.append(update.id)
                
                update_id = update_ids[0] if update_ids else None
            
            else:
                update_id = None
            
            return update_id
            
        except Exception as e:
            session.rollback()
            print(f"Failed to log update: {e}")
            return None
        finally:
            session.close()
    
    def log_batch_operations(
        self,
        extraction_id: int,
        operations: List[Dict[str, Any]],
        source_document_path: str,
        overall_reasoning: str,
        confidence: float
    ) -> List[int]:
        """
        Log multiple operations from a single reasoning session.
        
        Args:
            extraction_id: ID from extraction_audit
            operations: List of operations from LLM
            source_document_path: Path to original document
            overall_reasoning: Overall LLM reasoning
            confidence: Overall confidence
            
        Returns:
            List of update IDs
        """
        update_ids = []
        
        for op in operations:
            # Handle multiple formats:
            # 1. From reasoning_trail: {"result": {...}, "tool": "create_record"}
            # 2. From final JSON: {"action": "updated", "table": "...", "record_id": ..., "updates": {...}}
            
            operation_result = None
            
            if op.get("result") and isinstance(op["result"], dict):
                # Format 1: From reasoning trail (with actual database operation results)
                operation_result = op["result"]
                
            elif op.get("action") and op.get("table"):
                # Format 2: From final JSON summary
                action = op.get("action")
                
                # Skip non-write operations (searched, retrieved, etc)
                if action not in ["created", "updated", "deleted"]:
                    continue
                
                # Convert to expected format
                operation_result = {
                    "success": True,
                    "table": op["table"],
                    "record_id": op.get("record_id"),
                    "operation": "update" if action == "updated" else "create" if action == "created" else "delete",
                    "record": op.get("data", {}),
                    "changes": op.get("changes", op.get("updates", {}))
                }
                
                # Ensure changes has proper format {field: {old: ..., new: ...}}
                if operation_result["operation"] == "update" and operation_result.get("changes"):
                    # If changes is simple dict like {"delivery_date": "2027-02-01"}
                    # Convert to {"delivery_date": {"old": null, "new": "2027-02-01"}}
                    formatted_changes = {}
                    for field, value in operation_result["changes"].items():
                        if isinstance(value, dict) and "old" in value:
                            formatted_changes[field] = value
                        else:
                            formatted_changes[field] = {"old": None, "new": value}
                    operation_result["changes"] = formatted_changes
            else:
                continue  # Skip invalid operations
            
            if not operation_result or not operation_result.get("success"):
                continue
            
            update_id = self.log_operation(
                extraction_id=extraction_id,
                operation_result=operation_result,
                source_document_path=source_document_path,
                llm_reasoning=f"{overall_reasoning}\n\nStep {op.get('step', '?')}: {op.get('action', 'unknown')} on {op.get('table', 'unknown')}",
                confidence=confidence
            )
            if update_id:
                update_ids.append(update_id)
        
        return update_ids
    
    def get_updates_for_extraction(self, extraction_id: int) -> List[DatabaseUpdate]:
        """
        Get all database updates from a specific extraction.
        
        Args:
            extraction_id: Extraction ID
            
        Returns:
            List of DatabaseUpdate records
        """
        session = Session(self.engine)
        try:
            updates = session.query(DatabaseUpdate).filter(
                DatabaseUpdate.extraction_id == extraction_id
            ).order_by(DatabaseUpdate.timestamp).all()
            return updates
        finally:
            session.close()
    
    def get_update_details(self, update_id: int) -> Optional[DatabaseUpdate]:
        """
        Get detailed information about a specific update.
        
        Args:
            update_id: Update ID
            
        Returns:
            DatabaseUpdate record
        """
        session = Session(self.engine)
        try:
            return session.query(DatabaseUpdate).get(update_id)
        finally:
            session.close()
    
    def approve_update(self, update_id: int, approver: str, notes: str = None):
        """
        Approve an update that required review.
        
        Args:
            update_id: Update ID
            approver: Who approved
            notes: Optional approval notes
        """
        session = Session(self.engine)
        try:
            update = session.query(DatabaseUpdate).get(update_id)
            if update:
                update.approved = True
                update.approved_by = approver
                update.approved_at = datetime.utcnow()
                update.review_notes = notes
                session.commit()
        finally:
            session.close()
    
    def reject_update(self, update_id: int, reviewer: str, reason: str):
        """
        Reject an update that required review.
        
        Args:
            update_id: Update ID
            reviewer: Who rejected
            reason: Why rejected
        """
        session = Session(self.engine)
        try:
            update = session.query(DatabaseUpdate).get(update_id)
            if update:
                update.approved = False
                update.approved_by = reviewer
                update.approved_at = datetime.utcnow()
                update.review_notes = reason
                session.commit()
        finally:
            session.close()
    
    def get_pending_approvals(self) -> List[DatabaseUpdate]:
        """Get all updates awaiting approval."""
        session = Session(self.engine)
        try:
            return session.query(DatabaseUpdate).filter(
                DatabaseUpdate.requires_approval == True,
                DatabaseUpdate.approved == None
            ).order_by(DatabaseUpdate.timestamp.desc()).all()
        finally:
            session.close()

