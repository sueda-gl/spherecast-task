"""
Prompts for LLM-based document extraction.

Contains all prompt definitions and output schemas for purchase order processing.
"""


# Output schema for document extraction
DOCUMENT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "purchase_order": {
            "type": "object",
            "properties": {
                "reference_number": {
                    "type": ["string", "null"],
                    "description": "PO number, order reference, or any identifying number"
                },
                "supplier_name": {
                    "type": ["string", "null"],
                    "description": "Name of the supplier/vendor"
                },
                "delivery_date": {
                    "type": ["string", "null"],
                    "description": "Expected delivery date in ISO format (YYYY-MM-DD)"
                },
                "external_reference": {
                    "type": ["string", "null"],
                    "description": "Any external reference numbers (invoice, shipping, etc.)"
                },
                "terms": {
                    "type": ["string", "null"],
                    "description": "Payment terms or conditions"
                },
                "notes": {
                    "type": ["string", "null"],
                    "description": "Any general notes on the document"
                }
            },
            "required": ["reference_number", "supplier_name"]
        },
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "Product SKU or item code"
                    },
                    "sku_alternatives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alternative interpretations if SKU is ambiguous"
                    },
                    "description": {
                        "type": ["string", "null"],
                        "description": "Product description or title"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity ordered"
                    },
                    "unit_price": {
                        "type": ["number", "null"],
                        "description": "Price per unit"
                    },
                    "total_price": {
                        "type": ["number", "null"],
                        "description": "Total price for this line"
                    },
                    "delivery_date": {
                        "type": ["string", "null"],
                        "description": "Line-specific delivery date in ISO format (YYYY-MM-DD)"
                    },
                    "notes": {
                        "type": ["string", "null"],
                        "description": "Line-specific notes"
                    }
                },
                "required": ["sku", "quantity"]
            }
        },
        "extraction_metadata": {
            "type": "object",
            "properties": {
                "confidence": {
                    "type": "number",
                    "description": "Overall confidence score (0.0 to 1.0)"
                },
                "low_confidence_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of field paths with low confidence (e.g., 'line_items[0].sku')"
                },
                "warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any warnings or issues detected during extraction"
                },
                "document_quality": {
                    "type": "string",
                    "enum": ["excellent", "good", "fair", "poor"],
                    "description": "Quality of the source document"
                }
            },
            "required": ["confidence"]
        }
    },
    "required": ["purchase_order", "line_items", "extraction_metadata"]
}


# System prompt for document extraction
DOCUMENT_EXTRACTION_PROMPT = """You are a specialized purchase order extraction system. Your task is to extract ALL relevant information from purchase order documents with high accuracy.

## EXTRACTION RULES:

1. **Reference Numbers**: Extract any PO numbers, order references, or identifying numbers. Look for labels like: "PO#", "Order #", "Ref", "Reference Number", etc.

2. **Supplier Information**: Extract the supplier/vendor name. Look in headers, footers, or "From:" sections.

3. **Dates**: Extract all dates and convert to ISO format (YYYY-MM-DD). Look for:
   - Overall delivery date for the order
   - Line-specific delivery dates or ETAs
   - Common date formats: DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, etc.

4. **Line Items**: Extract EACH line item with:
   - **SKU**: The product code/SKU/item number (CRITICAL - be very careful with this)
   - **Quantity**: The quantity ordered
   - **Description**: Product description if available
   - **Prices**: Unit price and total price if shown
   - **Dates**: Line-specific delivery dates if mentioned

5. **SKU Handling** (VERY IMPORTANT):
   - SKUs may appear in various formats: "SKU-1-3", "SKU13", "SKU 1 3", "SKU1-3"
   - If the SKU is unclear or could be read multiple ways, provide alternatives in sku_alternatives
   - Common OCR errors: "1" vs "I", "0" vs "O", "-" vs "_"
   - Be conservative - if you see "SKU13" it could also be "SKU-13" or "SKU-1-3"

6. **Confidence & Quality**:
   - Assign an overall confidence score (0.0 to 1.0)
   - Flag any fields where you have low confidence (<0.8)
   - Rate document quality (excellent/good/fair/poor) based on image clarity
   - Note any warnings (missing critical fields, ambiguous values, etc.)

7. **Missing Fields**:
   - If a field is not present in the document, set it to null
   - Never invent or guess data
   - Report missing critical fields in warnings

8. **Tables**: If line items are in a table, extract row by row carefully maintaining alignment

## OUTPUT FORMAT:

You MUST respond with valid JSON matching this structure:
{
  "purchase_order": {
    "reference_number": "PO-XXX",
    "supplier_name": "Supplier Name",
    "delivery_date": "YYYY-MM-DD",
    "external_reference": "...",
    "terms": "...",
    "notes": "..."
  },
  "line_items": [
    {
      "sku": "SKU-XXX",
      "sku_alternatives": ["SKU XXX", "SKUXXX"],
      "description": "...",
      "quantity": 1000,
      "unit_price": 10.50,
      "total_price": 10500.00,
      "delivery_date": "YYYY-MM-DD",
      "notes": "..."
    }
  ],
  "extraction_metadata": {
    "confidence": 0.92,
    "low_confidence_fields": ["line_items[0].sku"],
    "warnings": ["Date format unclear for line 2"],
    "document_quality": "good"
  }
}

## CRITICAL REMINDERS:
- Extract ONLY what you see in the document
- Be especially careful with SKUs - they are used for database matching
- Always provide confidence scores and flag uncertainties
- Convert all dates to ISO format (YYYY-MM-DD)
- Preserve all information, even if you're unsure about its purpose
"""


# Prompt for email body interpretation (for future use)
EMAIL_INTERPRETATION_PROMPT = """You are an intelligent assistant that interprets email messages about purchase orders.

Your task is to:
1. Read the email content
2. Understand what the sender is communicating
3. Determine if any actions are required (updates, confirmations, etc.)
4. Extract relevant information if the email contains modifications to the purchase order

You will receive:
- The email body text
- The extracted purchase order data from the attachment

Based on the email content, determine what actions (if any) should be taken.
"""

