"""
Universal Orchestrator - Main entry point for email + document processing.

Handles the complete flow:
1. Extract document with verification
2. Log to audit trail
3. Route based on confidence (auto-process vs human review)
4. Process high-confidence items automatically

Architecture Options:
- "chain" (default): Multi-step LLM chain + deterministic executor (recommended)
- "hybrid": Single-call PlanningLLM + deterministic executor
- "agent": Single agent with tool calling (legacy)
"""

from pathlib import Path
from typing import Dict, Any, Optional

from extraction import ExtractAndVerify
from extraction.audit import ExtractionAudit
from reasoning import PlanningLLM, ChainPlanner, OperationExecutor, MasterReasoningOrchestrator
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
    
    Processing Modes:
    - "chain": Multi-step LLM chain (default, most reliable)
    - "hybrid": Single-call PlanningLLM
    - "agent": Single LLM with tool calling (legacy)
    """
    
    # Confidence thresholds for routing
    AUTO_PROCESS_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.75
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        audit_db: str = "audit.db",
        model: str = "gpt-5.2",
        database_path: str = "database/spherecast.db",
        mode: str = "chain"
    ):
        """
        Initialize orchestrator.
        
        Args:
            api_key: OpenAI API key
            audit_db: Path to audit database
            model: LLM model to use
            database_path: Path to main database
            mode: "chain" (recommended), "hybrid", or "agent" (legacy)
        """
        self.mode = mode
        self.extractor = ExtractAndVerify(api_key=api_key, model=model)
        self.audit = ExtractionAudit(db_path=audit_db)
        
        # Initialize database engine
        self.db_engine = get_engine(database_path)
        
        # Initialize processing components based on mode
        if mode == "chain":
            # Multi-step chain: 4 focused LLM calls + Deterministic Executor
            self.planner = ChainPlanner(
                engine=self.db_engine,
                api_key=api_key,
                model=model
            )
            self.executor = OperationExecutor(engine=self.db_engine)
            self.reasoning_agent = None
        elif mode == "hybrid":
            # Single-call: PlanningLLM + Deterministic Executor
            self.planner = PlanningLLM(
                engine=self.db_engine,
                api_key=api_key,
                model=model
            )
            self.executor = OperationExecutor(engine=self.db_engine)
            self.reasoning_agent = None
        else:
            # Legacy architecture: Single agent with tool calling
            self.reasoning_agent = MasterReasoningOrchestrator(
                engine=self.db_engine,
                api_key=api_key,
                model=model
            )
            self.planner = None
            self.executor = None
        
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
        
        Two modes:
        - "hybrid": PlanningLLM generates plan, OperationExecutor runs it
        - "agent": Single LLM with tool calling (legacy)
        
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
            print(f"STEP 4: DATABASE PROCESSING (mode: {self.mode})")
            print(f"{'─'*70}")
        
        if self.mode in ("chain", "hybrid"):
            return self._process_hybrid(
                email_body=email_body,
                extracted_data=extracted_data,
                extraction_id=extraction_id,
                document_path=document_path,
                verbose=verbose
            )
        else:  # "agent" mode
            return self._process_agent(
                email_body=email_body,
                extracted_data=extracted_data,
                extraction_id=extraction_id,
                document_path=document_path,
                verbose=verbose
            )
    
    def _process_hybrid(
        self,
        email_body: str,
        extracted_data: dict,
        extraction_id: int,
        document_path: str,
        verbose: bool
    ) -> dict:
        """
        Hybrid/Chain processing: LLM plans, Python executes.
        
        Works for both "chain" mode (multi-step) and "hybrid" mode (single-call).
        """
        
        mode_name = "CHAIN" if self.mode == "chain" else "HYBRID"
        
        # Step 1: Planning
        if verbose:
            print(f"\n[{mode_name} MODE] Phase 1: Planning...")
        
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
        
        # Step 2: Execution (deterministic Python)
        if verbose:
            print(f"\n[{mode_name} MODE] Phase 2: Execution...")
        
        exec_result = self.executor.execute(
            plan=plan,
            extraction_id=extraction_id,
            source_document_path=document_path,
            verbose=verbose
        )
        
        # Build final result
        result = {
            "success": exec_result.get("success", False),
            "mode": self.mode,
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
    
    def _process_agent(
        self,
        email_body: str,
        extracted_data: dict,
        extraction_id: int,
        document_path: str,
        verbose: bool
    ) -> dict:
        """
        Legacy agent processing: Single LLM with tool calling.
        """
        
        # Let the reasoning agent process (with full debugging visibility)
        result = self.reasoning_agent.process(
            email_body=email_body,
            extracted_data=extracted_data,
            verbose=verbose
        )
        
        if verbose:
            print(f"✓ Reasoning complete in {result.get('iterations', 0)} iterations")
            print(f"  Tables affected: {', '.join(result.get('tables_affected', []))}")
            print(f"  Operations: {len(result.get('operations', []))}")
        
        # Log all database operations to update tracker
        operations = result.get("operations", [])
        reasoning_trail = result.get("reasoning_trail", [])
        
        # If no operations in final result, extract from reasoning trail
        if not operations and reasoning_trail:
            operations = []
            for step in reasoning_trail:
                if step.get("tool") in ["create_record", "update_record"] and step.get("result", {}).get("success"):
                    operations.append({
                        "step": step.get("iteration"),
                        "action": step["tool"].replace("_record", "d"),
                        "table": step["result"]["table"],
                        "record_id": step["result"].get("record_id"),
                        "data": step["result"].get("record"),
                        "changes": step["result"].get("changes"),
                        "result": step["result"]
                    })
            
            if operations and verbose:
                print(f"⚠ Extracted {len(operations)} operations from reasoning trail")
        
        if operations:
            update_ids = self.update_tracker.log_batch_operations(
                extraction_id=extraction_id,
                operations=operations,
                source_document_path=document_path,
                overall_reasoning=result.get("reasoning", result.get("summary", "Operation completed")),
                confidence=result.get("confidence", 0.85)
            )
            result["update_ids"] = update_ids
            
            if verbose:
                print(f"✓ Logged {len(update_ids)} database updates to audit trail")
        
        return result
    
    def _build_summary(self, plan: dict, exec_result: dict) -> str:
        """Build human-readable summary from plan and execution result."""
        parts = []
        
        # PO info
        analysis = plan.get("analysis", {})
        po_ref = analysis.get("po_reference", {})
        if po_ref.get("is_new"):
            parts.append(f"Created new purchase order '{po_ref.get('raw_value')}'")
        else:
            parts.append(f"Updated existing purchase order '{po_ref.get('matched_reference')}' (ID {po_ref.get('matched_po_id')})")
        
        # Operations
        created = len(exec_result.get("records_created", []))
        updated = len(exec_result.get("records_updated", []))
        
        if created:
            parts.append(f"Created {created} record(s)")
        if updated:
            parts.append(f"Updated {updated} record(s)")
        
        # Email overrides
        overrides = plan.get("email_overrides", [])
        if overrides:
            parts.append(f"Applied {len(overrides)} email override(s)")
        
        return ". ".join(parts) + "."
    
    def _build_operations_list(self, plan: dict, exec_result: dict) -> list:
        """Build operations list for audit logging."""
        operations = []
        
        # From created records
        for rec in exec_result.get("records_created", []):
            operations.append({
                "action": "create",
                "table": rec.get("table"),
                "record_id": rec.get("id"),
                "data": rec
            })
        
        # From updated records
        for rec in exec_result.get("records_updated", []):
            operations.append({
                "action": "update",
                "table": rec.get("table"),
                "record_id": rec.get("id"),
                "changes": rec.get("changes")
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

