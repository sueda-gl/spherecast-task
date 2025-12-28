"""
Extract and Verify - Two-phase document extraction with verification.

1. Extractor LLM reads document and extracts data
2. Verifier LLM checks extraction against original document

No formatting confusion, clear error reporting.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import json

from llm_client import LLMClient
from .prompts import EXTRACTION_PROMPT, VERIFICATION_PROMPT


class ExtractAndVerify:
    """
    Two-phase extraction: Extract → Verify
    
    Advantages over dual extraction:
    - No formatting comparison issues
    - Verifier explicitly identifies errors
    - Cheaper (fewer tokens)
    - Easier to debug (verifier explains issues)
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """
        Initialize extractor and verifier.
        
        Args:
            api_key: OpenAI API key (defaults to env var)
            model: Model to use for both extraction and verification
        """
        self.extractor = LLMClient(api_key=api_key, model=model, temperature=0.0)
        self.verifier = LLMClient(api_key=api_key, model=model, temperature=0.0)
    
    def extract_with_verification(
        self, 
        document_path: str,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Extract from document and verify the extraction.
        
        Args:
            document_path: Path to document image
            verbose: Print progress messages
            
        Returns:
            {
                "data": {...},              # Extracted data
                "verified": true/false,     # Did verification pass?
                "confidence": 0.95,         # Overall confidence score
                "issues": [...],            # List of issues found
                "statistics": {...},        # Verification statistics
                "raw_extraction": {...},    # Original extraction
                "verification_report": {...} # Full verification details
            }
        """
        
        document_path = Path(document_path)
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"EXTRACTING: {document_path.name}")
            print(f"{'='*60}")
        
        # Phase 1: Extract
        if verbose:
            print("\n[1/2] Extracting data from document...")
        
        extraction = self.extractor.call_with_image(
            prompt=EXTRACTION_PROMPT,
            image_path=document_path,
            json_mode=True
        )
        
        extraction_confidence = extraction.get("extraction_metadata", {}).get("confidence", 0.5)
        doc_type = extraction.get("document_classification", {}).get("primary_type", "unknown")
        
        if verbose:
            print(f"  ✓ Document type: {doc_type}")
            print(f"  ✓ Extraction confidence: {extraction_confidence:.2%}")
            
            line_items = extraction.get("extracted_entities", {}).get("line_items", [])
            if line_items:
                print(f"  ✓ Line items extracted: {len(line_items)}")
        
        # Phase 2: Verify
        if verbose:
            print("\n[2/2] Verifying extraction against original...")
        
        verification = self._verify_extraction(document_path, extraction, verbose)
        
        # Combine results
        result = {
            "data": extraction,
            "verified": verification.get("verified", False),
            "confidence": verification.get("confidence", 0.0),
            "issues": verification.get("issues", []),
            "missing_fields": verification.get("missing_fields", []),
            "statistics": verification.get("statistics", {}),
            "raw_extraction": extraction,
            "verification_report": verification
        }
        
        if verbose:
            self._print_summary(result)
        
        return result
    
    def _verify_extraction(
        self, 
        document_path: Path, 
        extraction: dict,
        verbose: bool
    ) -> dict:
        """
        Verify extraction against original document.
        
        Args:
            document_path: Path to original document
            extraction: The extraction to verify
            verbose: Print progress
            
        Returns:
            Verification report with issues found
        """
        
        # Build verification prompt with extraction embedded
        verification_prompt = VERIFICATION_PROMPT.format(
            extraction_json=json.dumps(extraction, indent=2)
        )
        
        try:
            verification_result = self.verifier.call_with_image(
                prompt=verification_prompt,
                image_path=document_path,
                json_mode=True
            )
            
            return verification_result
            
        except Exception as e:
            # If verification fails, return low confidence
            if verbose:
                print(f"  ⚠ Verification failed: {e}")
            
            return {
                "verified": False,
                "confidence": 0.5,
                "overall_assessment": f"Verification error: {str(e)}",
                "issues": [{"description": "Verification process failed", "severity": "high"}],
                "statistics": {}
            }
    
    def _print_summary(self, result: dict):
        """Print extraction and verification summary."""
        
        print(f"\n{'='*60}")
        print("EXTRACTION SUMMARY")
        print(f"{'='*60}")
        
        verified = result["verified"]
        confidence = result["confidence"]
        
        status_icon = "✓" if verified and confidence > 0.9 else "⚠" if confidence > 0.7 else "✗"
        status_text = "VERIFIED" if verified else "ISSUES FOUND"
        
        print(f"\n{status_icon} Status: {status_text}")
        print(f"  Confidence: {confidence:.2%}")
        
        # Statistics
        stats = result.get("statistics", {})
        if stats:
            print(f"\n  Fields checked: {stats.get('total_fields_checked', 0)}")
            print(f"  Correct: {stats.get('correct_fields', 0)}")
            print(f"  Incorrect: {stats.get('incorrect_fields', 0)}")
            print(f"  Missing: {stats.get('missing_fields', 0)}")
        
        # Issues
        issues = result.get("issues", [])
        if issues:
            print(f"\n⚠ Issues Found: {len(issues)}")
            for issue in issues[:3]:  # Show first 3
                severity = issue.get("severity", "unknown").upper()
                field = issue.get("field", "unknown")
                desc = issue.get("description", "")
                print(f"  [{severity}] {field}: {desc}")
            
            if len(issues) > 3:
                print(f"  ... and {len(issues) - 3} more")
        
        # Missing fields
        missing = result.get("missing_fields", [])
        if missing:
            print(f"\n⚠ Missing Fields: {len(missing)}")
            for miss in missing[:3]:
                field = miss.get("field", "unknown")
                desc = miss.get("description", "")
                print(f"  - {field}: {desc}")
        
        # Recommendation
        print(f"\n{'='*60}")
        if verified and confidence > 0.9:
            print("✓ RECOMMENDATION: Safe for automatic processing")
        elif confidence > 0.75:
            print("⚠ RECOMMENDATION: Review issues, then process")
        else:
            print("✗ RECOMMENDATION: Requires human review")
        print(f"{'='*60}\n")

