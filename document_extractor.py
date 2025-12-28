"""
Document extraction module for purchase orders.

Handles the extraction of structured data from PO documents using LLM.
"""

from pathlib import Path
from typing import Optional, Union
import json

from llm_client import LLMClient
from prompts import DOCUMENT_EXTRACTION_PROMPT, DOCUMENT_EXTRACTION_SCHEMA


class DocumentExtractor:
    """Handles extraction of purchase order data from documents."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5.2"):
        """
        Initialize document extractor.
        
        Args:
            api_key: OpenAI API key (defaults to env var)
            model: Model to use for extraction
        """
        self.llm_client = LLMClient(api_key=api_key, model=model, temperature=0.0)
    
    def extract_purchase_order(
        self,
        document_path: Union[str, Path],
        save_output: bool = False,
        output_dir: Optional[Path] = None
    ) -> dict:
        """
        Extract purchase order data from a document.
        
        Args:
            document_path: Path to the PO document (image or PDF)
            save_output: Whether to save the extracted JSON to file
            output_dir: Directory to save output (defaults to same as document)
        
        Returns:
            Dictionary with extracted purchase order data
        """
        document_path = Path(document_path)
        
        print(f"Extracting data from: {document_path.name}")
        
        # Extract using LLM - call with image
        extracted_data = self.llm_client.call_with_image(
            prompt=DOCUMENT_EXTRACTION_PROMPT,
            image_path=document_path,
            json_mode=True
        )
        
        # Display extraction summary
        self._print_extraction_summary(extracted_data)
        
        # Save output if requested
        if save_output:
            output_path = self._save_extraction(
                extracted_data,
                document_path,
                output_dir
            )
            print(f"\nExtracted data saved to: {output_path}")
        
        return extracted_data
    
    def _print_extraction_summary(self, data: dict) -> None:
        """Print a summary of the extraction."""
        metadata = data.get("extraction_metadata", {})
        po = data.get("purchase_order", {})
        line_items = data.get("line_items", [])
        
        print("\n" + "="*60)
        print("EXTRACTION SUMMARY")
        print("="*60)
        
        print(f"\nConfidence: {metadata.get('confidence', 'N/A')}")
        print(f"Document Quality: {metadata.get('document_quality', 'N/A')}")
        
        if metadata.get('warnings'):
            print(f"\nWarnings:")
            for warning in metadata['warnings']:
                print(f"  - {warning}")
        
        if metadata.get('low_confidence_fields'):
            print(f"\nLow Confidence Fields:")
            for field in metadata['low_confidence_fields']:
                print(f"  - {field}")
        
        print(f"\nPurchase Order:")
        print(f"  Reference: {po.get('reference_number', 'N/A')}")
        print(f"  Supplier: {po.get('supplier_name', 'N/A')}")
        print(f"  Delivery Date: {po.get('delivery_date', 'N/A')}")
        
        print(f"\nLine Items: {len(line_items)}")
        for i, item in enumerate(line_items, 1):
            print(f"  {i}. SKU: {item.get('sku')} | Qty: {item.get('quantity')}")
            if item.get('sku_alternatives'):
                print(f"     Alternatives: {', '.join(item['sku_alternatives'])}")
        
        print("="*60 + "\n")
    
    def _save_extraction(
        self,
        data: dict,
        document_path: Path,
        output_dir: Optional[Path]
    ) -> Path:
        """Save extracted data to JSON file."""
        if output_dir is None:
            output_dir = document_path.parent
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_filename = f"{document_path.stem}_extracted.json"
        output_path = output_dir / output_filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return output_path


# Example usage
if __name__ == "__main__":
    # Example: Extract from a document
    extractor = DocumentExtractor()
    
    # Path to your test document
    test_doc = Path("path/to/your/purchase_order.pdf")
    
    if test_doc.exists():
        result = extractor.extract_purchase_order(
            document_path=test_doc,
            save_output=True
        )
        
        print("\nFull extracted data:")
        print(json.dumps(result, indent=2))
    else:
        print(f"Test document not found: {test_doc}")
        print("\nTo use this extractor:")
        print("  extractor = DocumentExtractor()")
        print("  result = extractor.extract_purchase_order('path/to/document.pdf')")

