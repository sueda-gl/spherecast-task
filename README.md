# SphereCast - Purchase Order Extraction System

An LLM-based system for extracting structured data from purchase order documents.

## Architecture Overview

### Phase 1: Document Extraction (Current)

```
Document (PDF/Image) → LLM (Vision) → Structured JSON → Database
```

**Key Components:**

1. **`llm_client.py`** - LLM API client with vision support
   - Handles document encoding and API calls
   - Supports structured JSON output
   - Configurable model and temperature

2. **`prompts.py`** - Prompt definitions and output schemas
   - Document extraction prompt with detailed instructions
   - JSON schema for structured output
   - Email interpretation prompt (for future use)

3. **`document_extractor.py`** - High-level extraction interface
   - Simple API for extracting PO data
   - Extraction summary and confidence reporting
   - JSON output saving

### Extracted Data Structure

```json
{
  "purchase_order": {
    "reference_number": "PO-12",
    "supplier_name": "Big Supplier",
    "delivery_date": "2027-01-15",
    "external_reference": null,
    "terms": "Net 30",
    "notes": null
  },
  "line_items": [
    {
      "sku": "SKU-1-3",
      "sku_alternatives": ["SKU13", "SKU-13"],
      "description": "PRODUCT ONE | GLOBAL VERSION updated v3",
      "quantity": 15000,
      "delivery_date": "2027-02-01",
      "notes": null
    }
  ],
  "extraction_metadata": {
    "confidence": 0.92,
    "low_confidence_fields": ["line_items[0].sku"],
    "warnings": [],
    "document_quality": "good"
  }
}
```

### Phase 2: Email Interpretation (Future)

Email body processing will be handled separately as an agentic/interpretive task:
- LLM reads email text and decides what actions are needed
- Can modify extracted data based on email notes
- Not forced into JSON schema - interprets freely

## Usage

### Setup

```bash
# Install dependencies
uv sync

# Set API key
export OPENAI_API_KEY="your-api-key"
```

### Basic Extraction

```python
from document_extractor import DocumentExtractor

# Initialize extractor
extractor = DocumentExtractor()

# Extract from document
result = extractor.extract_purchase_order(
    document_path="path/to/purchase_order.pdf",
    save_output=True
)

# Access extracted data
po_ref = result["purchase_order"]["reference_number"]
supplier = result["purchase_order"]["supplier_name"]
line_items = result["line_items"]

# Check confidence
confidence = result["extraction_metadata"]["confidence"]
warnings = result["extraction_metadata"]["warnings"]
```

### Custom Configuration

```python
from llm_client import LLMClient
from prompts import DOCUMENT_EXTRACTION_PROMPT

# Use a different model or settings
client = LLMClient(
    model="gpt-5.2",  # or another vision-capable model
    temperature=0.0   # deterministic extraction
)

# Extract with custom settings
data = client.extract_from_document(
    document_path="path/to/doc.pdf",
    prompt=DOCUMENT_EXTRACTION_PROMPT
)
```

## Key Design Decisions

### 1. Structured Document Extraction
- PO attachments are formal documents → extract to structured JSON
- Fixed schema maps directly to database fields
- Confidence scores for reliability assessment

### 2. Separate Email Processing
- Email body is natural language → interpret freely, don't force into schema
- LLM reads and decides what actions are needed
- Handled separately from document extraction

### 3. SKU Ambiguity Handling
- LLM provides `sku_alternatives` for ambiguous SKUs
- Common OCR errors considered (1/I, 0/O, etc.)
- Fuzzy matching layer (to be implemented) will resolve to internal product IDs

### 4. Confidence-Based Quality Control
- Overall confidence score (0.0 to 1.0)
- Field-level confidence flags
- Document quality assessment
- Warnings for missing/ambiguous data

### 5. Vision-First Approach
- Uses vision-capable LLM (GPT-5.2/Claude with vision)
- Handles both scanned and digital documents uniformly
- Better understanding of layout and spatial relationships
- Single-step processing (no separate OCR needed)

## Database Schema

See `database/models.py` for the complete schema:

- **Product** - Internal product catalog (SKU, title)
- **Supplier** - Vendor information
- **SupplierProduct** - Maps supplier SKUs to internal products
- **PurchaseOrder** - Order header (reference, dates, terms)
- **PurchaseOrderLine** - Line items (product, quantity, pricing)

## Web UI

A modern web interface is now available for easy document processing:

```bash
# Start backend
python -m uvicorn api:app --reload --port 8000

# Start frontend (in another terminal)
cd frontend && npm run dev
```

Then open `http://localhost:5173` and upload `.eml` files directly!

See `SETUP.md` for detailed instructions.

## Next Steps

1. **SKU Resolution** - Fuzzy matching from extracted SKU to internal product_id
2. **Database Integration** - Insert extracted data into database
3. **Validation Layer** - Verify data consistency and completeness
4. **Email Body Processing** - Interpret modifications/notes from email
5. **Confidence Routing** - Auto-process high confidence, queue low confidence for review

## Testing

```bash
# Run tests (when implemented)
pytest tests/

# Lint code
ruff check .
```

## Dependencies

- **OpenAI** - LLM API for document extraction
- **SQLAlchemy** - Database ORM
- **Pydantic** - Data validation (future use)
- **Pillow** - Image processing support
- **python-dotenv** - Environment variable management

