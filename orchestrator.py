"""
Universal Orchestrator - Main entry point for email + document processing.

Handles the complete flow:
1. Extract document with verification
2. Log to audit trail
3. Route based on confidence (auto-process vs human review)
4. Process high-confidence items automatically

Architecture:
- ChainPlanner: Multi-step LLM chain for entity resolution and operation planning
- OperationExecutor: Deterministic SQL executor
"""

from pathlib import Path
from typing import Dict, Any, Optional

from extraction import ExtractAndVerify
from extraction.audit import ExtractionAudit
from reasoning import ChainPlanner, OperationExecutor
from audit import UpdateAuditTracker
from database.models import get_engine


class UniversalOrchestrator:
    """
    Main orchestrator for document processing with confidence-based routing.
    
    Flow:
    1. Extract + verify document
    2. Log to audit
    3. Route based on confidence:
       - High confidence (>0.90): Auto-process
       - Medium confidence (0.75-0.90): Queue for review
       - Low confidence (<0.75): Require manual review
    """
    
    # Confidence thresholds for routing
    AUTO_PROCESS_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.75
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        audit_db: str = "audit.db",
        model: str = "gpt-5.2",
        database_path: str = "database/spherecast.db"
    ):
        """
        Initialize orchestrator.
        
        Args:
            api_key: OpenAI API key
            audit_db: Path to audit database
            model: LLM model to use
            database_path: Path to main database
        """
        self.extractor = ExtractAndVerify(api_key=api_key, model=model)
        self.audit = ExtractionAudit(db_path=audit_db)
        
        # Initialize database engine
        self.db_engine = get_engine(database_path)
        
        # Initialize processing components
        self.planner = ChainPlanner(
            engine=self.db_engine,
            api_key=api_key,
            model=model
        )
        self.executor = OperationExecutor(engine=self.db_engine)
        
        self.update_tracker = UpdateAuditTracker(db_path=audit_db)
    
    def process_email_with_document(
        self,
        email_id: str,
        email_body: str,
        document_path: str,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Main entry point: process email with attached document.
        
        Args:
            email_id: Unique email identifier
            email_body: Email text content
            document_path: Path to attached document
            verbose: Print progress messages
            
        Returns:
            {
                "extraction_id": 123,
                "status": "auto_processed" | "pending_review" | "requires_manual",
                "confidence": 0.95,
                "verified": true/false,
                "result": {...},  # Processing result (if auto-processed)
                "extracted_data": {...}  # Full extraction (if confidence >= threshold)
            }
        """
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"PROCESSING EMAIL: {email_id}")
            print(f"{'='*70}")
            print(f"Document: {Path(document_path).name}")
            print(f"Email preview: {email_body[:100]}...")
        
        # Step 1: Extract and verify document
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 1: DOCUMENT EXTRACTION & VERIFICATION")
            print(f"{'─'*70}")
        
        extraction_result = self.extractor.extract_with_verification(
            document_path=document_path,
            verbose=verbose
        )
        
        confidence = extraction_result["confidence"]
        verified = extraction_result["verified"]
        
        # Step 2: Log to audit
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 2: AUDIT LOGGING")
            print(f"{'─'*70}")
        
        extraction_id = self.audit.log_extraction(
            email_id=email_id,
            document_path=document_path,
            extraction_result=extraction_result
        )
        
        if verbose:
            print(f"✓ Logged to audit database (ID: {extraction_id})")
        
        # Step 3: Confidence-based routing
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 3: ROUTING DECISION")
            print(f"{'─'*70}")
            print(f"Confidence: {confidence:.2%}")
            print(f"Verified: {verified}")
        
        if confidence >= self.AUTO_PROCESS_THRESHOLD and verified:
            # High confidence - process automatically
            if verbose:
                print(f"✓ HIGH CONFIDENCE → Auto-processing")
            
            result = self._process_automatically(
                email_body=email_body,
                extracted_data=extraction_result["data"],
                extraction_id=extraction_id,
                document_path=document_path,
                verbose=verbose
            )
            status = "auto_processed"
            
        elif confidence >= self.REVIEW_THRESHOLD:
            # Medium confidence - queue for review then process
            if verbose:
                print(f"⚠ MEDIUM CONFIDENCE → Queued for review")
            
            result = {
                "message": "Extraction queued for review",
                "reason": "Medium confidence or verification issues",
                "issues": extraction_result.get("issues", [])
            }
            status = "pending_review"
            
        else:
            # Low confidence - require manual review
            if verbose:
                print(f"✗ LOW CONFIDENCE → Requires manual review")
            
            result = {
                "message": "Requires manual review",
                "reason": "Low confidence extraction",
                "issues": extraction_result.get("issues", [])
            }
            status = "requires_manual"
        
        # Update audit with processing result
        self.audit.update_processing_result(extraction_id, {
            "status": status,
            "result": result
        })
        
        # Final output
        output = {
            "extraction_id": extraction_id,
            "status": status,
            "confidence": confidence,
            "verified": verified,
            "result": result
        }
        
        # Include extracted data if confidence is high enough
        if confidence >= self.REVIEW_THRESHOLD:
            output["extracted_data"] = extraction_result["data"]
        
        if verbose:
            self._print_final_summary(output)
        
        return output
    
    def _process_automatically(
        self,
        email_body: str,
        extracted_data: dict,
        extraction_id: int,
        document_path: str,
        verbose: bool
    ) -> dict:
        """
        Automatic processing for high-confidence extractions.
        
        Uses ChainPlanner for multi-step entity resolution and planning,
        then OperationExecutor for deterministic SQL execution.
        
        Args:
            email_body: Email content
            extracted_data: Verified extraction
            extraction_id: Extraction audit ID
            document_path: Path to source document
            verbose: Print progress
            
        Returns:
            Processing result with operations performed
        """
        
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 4: DATABASE PROCESSING")
            print(f"{'─'*70}")
        
        # Phase 1: Planning (multi-step LLM chain)
        if verbose:
            print("\n[CHAIN] Phase 1: Planning...")
        
        plan_result = self.planner.plan(
            email_body=email_body,
            extracted_data=extracted_data,
            verbose=verbose
        )
        
        if not plan_result.get("success"):
            return {
                "success": False,
                "error": plan_result.get("error", "Planning failed"),
                "phase": "planning"
            }
        
        plan = plan_result["plan"]
        
        # Phase 2: Execution (deterministic Python)
        if verbose:
            print("\n[CHAIN] Phase 2: Execution...")
        
        exec_result = self.executor.execute(
            plan=plan,
            extraction_id=extraction_id,
            source_document_path=document_path,
            verbose=verbose
        )
        
        # Build final result
        result = {
            "success": exec_result.get("success", False),
            "plan": plan,
            "execution": exec_result,
            "records_created": exec_result.get("records_created", []),
            "records_updated": exec_result.get("records_updated", []),
            "tables_affected": list(set(
                [r["table"] for r in exec_result.get("records_created", [])] +
                [r["table"] for r in exec_result.get("records_updated", [])]
            )),
            "confidence": plan.get("confidence", 0.85),
            "summary": self._build_summary(plan, exec_result)
        }
        
        # Log operations to audit trail
        operations = self._build_operations_list(plan, exec_result)
        if operations:
            update_ids = self.update_tracker.log_batch_operations(
                extraction_id=extraction_id,
                operations=operations,
                source_document_path=document_path,
                overall_reasoning=result["summary"],
                confidence=result["confidence"]
            )
            result["update_ids"] = update_ids
            
            if verbose:
                print(f"✓ Logged {len(update_ids)} database updates to audit trail")
        
        return result
    
    def _build_summary(self, plan: dict, exec_result: dict) -> str:
        """Build detailed human-readable summary from plan and execution result."""
        parts = []
        
        # PO info
        analysis = plan.get("analysis", {})
        po_ref = analysis.get("po_reference", {})
        if po_ref.get("is_new"):
            parts.append(f"Created new purchase order '{po_ref.get('raw_value')}'")
        else:
            parts.append(f"Updated existing purchase order '{po_ref.get('matched_reference')}' (ID {po_ref.get('matched_po_id')})")
        
        # Detailed operation descriptions
        for rec in exec_result.get("records_created", []):
            table = rec.get("table", "record")
            values = rec.get("values", {})
            
            if table == "product":
                sku = values.get("sku", "unknown")
                title = values.get("title", "")
                parts.append(f"Created new product: SKU='{sku}', Title='{title}'")
            elif table == "purchase_order_line":
                product_id = values.get("product_id", "?")
                qty = values.get("quantity", "?")
                date = values.get("delivery_date", "?")
                parts.append(f"Created PO line: product_id={product_id}, quantity={qty}, delivery_date={date}")
            elif table == "supplier_product":
                supplier_sku = values.get("supplier_sku", "")
                parts.append(f"Created supplier-product mapping: vendor_sku='{supplier_sku}'")
            else:
                parts.append(f"Created {table} record (ID: {rec.get('id', '?')})")
        
        for rec in exec_result.get("records_updated", []):
            table = rec.get("table", "record")
            record_id = rec.get("id", "?")
            changes = rec.get("changes", {})
            
            if changes:
                change_details = []
                for field, change in changes.items():
                    old_val = change.get("old", "null")
                    new_val = change.get("new", "null")
                    change_details.append(f"{field}: '{old_val}' → '{new_val}'")
                
                parts.append(f"Updated {table} (ID {record_id}): {', '.join(change_details)}")
            else:
                parts.append(f"Updated {table} (ID {record_id})")
        
        # Email overrides
        overrides = plan.get("email_overrides", [])
        if overrides:
            override_details = [f"'{o.get('field', '?')}' overridden from email" for o in overrides[:3]]
            parts.append(f"Applied email overrides: {', '.join(override_details)}")
        
        # Context instructions from chain results
        context_instructions = plan.get("context_instructions", [])
        if context_instructions and isinstance(context_instructions, list) and len(context_instructions) > 0:
            parts.append(f"Context instructions applied: {'; '.join(context_instructions[:3])}")
        
        return "\n\n".join(parts) if parts else "No operations performed."
    
    def _build_operations_list(self, plan: dict, exec_result: dict) -> list:
        """Build operations list for audit logging."""
        operations = []
        
        # From created records - NOTE: use "created" not "create" to match update_tracker expectations
        for rec in exec_result.get("records_created", []):
            operations.append({
                "action": "created",
                "table": rec.get("table"),
                "record_id": rec.get("id"),
                "data": rec.get("values", rec)
            })
        
        # From updated records - NOTE: use "updated" not "update" to match update_tracker expectations
        for rec in exec_result.get("records_updated", []):
            # Only log if there were actual changes
            changes = rec.get("changes", {})
            if changes:
                operations.append({
                    "action": "updated",
                    "table": rec.get("table"),
                    "record_id": rec.get("id"),
                    "changes": changes
                })
        
        return operations
    
    def _print_final_summary(self, output: dict):
        """Print final processing summary."""
        
        print(f"\n{'='*70}")
        print("FINAL RESULT")
        print(f"{'='*70}")
        
        status = output["status"]
        confidence = output["confidence"]
        
        if status == "auto_processed":
            print(f"✓ STATUS: Automatically processed")
            print(f"  Confidence: {confidence:.2%}")
        elif status == "pending_review":
            print(f"⚠ STATUS: Queued for review")
            print(f"  Confidence: {confidence:.2%}")
            print(f"  Reason: Medium confidence, review before processing")
        else:
            print(f"✗ STATUS: Requires manual review")
            print(f"  Confidence: {confidence:.2%}")
            print(f"  Reason: Low confidence extraction")
        
        print(f"\nExtraction ID: {output['extraction_id']}")
        print(f"{'='*70}\n")
    
    def get_review_queue(self, priority: Optional[str] = None) -> list:
        """
        Get items waiting for human review.
        
        Args:
            priority: Filter by priority ('high', 'medium', 'low')
            
        Returns:
            List of items needing review
        """
        return self.audit.get_review_queue(priority=priority)
    
    def get_statistics(self, days: int = 7) -> dict:
        """
        Get processing statistics.
        
        Args:
            days: Look back this many days
            
        Returns:
            Statistics dict
        """
        return self.audit.get_statistics(days=days)

