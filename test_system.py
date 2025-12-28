"""
Test script for end-to-end system testing.

Tests the complete flow:
1. Extract document
2. Verify extraction
3. Master LLM reasons and executes
4. View audit trail
"""

from pathlib import Path
from orchestrator import UniversalOrchestrator
import json


def test_with_example():
    """
    Test with the example from the task description.
    
    Email: "Push back ETA for SKU-1-3 to 02/01/2027"
    Document: Should contain purchase order data
    """
    
    print("\n" + "="*70)
    print("SPHERECAST END-TO-END TEST")
    print("="*70)
    
    # Initialize
    orchestrator = UniversalOrchestrator(
        audit_db="database/audit.db",
        database_path="database/spherecast.db"
    )
    
    # Test data
    email_id = "test_email_001"
    email_body = """
    Hey there,
    
    Please see attached scanned purchase order.
    
    Important note: we had to push back the eta for SKU-1-3 even 
    further back to 02/01/2027.
    """
    
    # Path to your test document
    document_path = "path/to/test_document.jpg"  # UPDATE THIS
    
    if not Path(document_path).exists():
        print(f"\n⚠️  Test document not found: {document_path}")
        print("\nPlease update the document_path variable with your test document.")
        print("\nExpected document: Purchase order image with SKU information")
        return
    
    print(f"\nTest document: {document_path}")
    print(f"Email ID: {email_id}")
    print("\nStarting processing...\n")
    
    # Process
    result = orchestrator.process_email_with_document(
        email_id=email_id,
        email_body=email_body,
        document_path=document_path,
        verbose=True  # Full debugging output
    )
    
    # Print results
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)
    
    print(f"\nExtraction ID: {result['extraction_id']}")
    print(f"Status: {result['status']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Verified: {result['verified']}")
    
    if result.get('result'):
        print(f"\nProcessing Result:")
        print(json.dumps(result['result'], indent=2))
    
    # Show reasoning trail if available
    if result.get('result', {}).get('reasoning_trail'):
        print(f"\n" + "="*70)
        print("FULL REASONING TRAIL (Saved for Debugging)")
        print("="*70)
        print(f"Total steps: {len(result['result']['reasoning_trail'])}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_with_example()

