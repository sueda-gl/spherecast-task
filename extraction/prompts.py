"""
Prompts for document extraction and verification.

Note: Examples use generic placeholders to avoid confusion with real data.
"""

# Adaptive extraction prompt - works with any document type
EXTRACTION_PROMPT = """You are analyzing a business document. Extract ALL information without assuming document type.

# TASK

1. **Classify Document Type**
   - Identify: purchase_order, invoice, shipping_notice, price_list, general_letter, other
   - Provide confidence in classification

2. **Extract All Structured Data**
   - Reference numbers (PO numbers, invoice numbers, tracking numbers, etc.)
   - Company names (supplier, customer, vendor)
   - Line items: For tables, READ the column headers from the document and use them as field names
     * If the table shows columns: "sku", "title", "quantity", "date", "total price"
     * Then use those EXACT names: {{"sku": "...", "title": "...", "quantity": ..., "date": "...", "total_price": "..."}}
     * Extract ALL columns present in the table
     * DO NOT invent or standardize column names - use what you see
   - Amounts and totals
   - Terms, conditions, notes

3. **Flag Ambiguities ONLY When Present**
   - Include ambiguities ONLY if there is actual uncertainty or multiple possible interpretations
   - If everything is clearly identified, leave the ambiguities array empty: []
   - When present, list alternative interpretations for unclear fields
   - Note potential OCR issues (1 vs I, 0 vs O, 5 vs S, etc.) only when genuinely ambiguous

# OUTPUT JSON STRUCTURE

**IMPORTANT**: Return ONLY valid JSON. Do not include any text, explanations, or markdown code blocks before or after the JSON object.

**CRITICAL for line_items**: 
- Look at the table in the document and identify the column headers
- Use those EXACT column names (with spaces converted to underscores) as keys in "extracted_fields"
- Each document may have different columns - adapt to what you see
- Example: Document table with columns [sku | title | quantity | date | total price]
  → extracted_fields: {{"sku": "...", "title": "...", "quantity": ..., "date": "...", "total_price": ...}}

{{
  "document_classification": {{
    "primary_type": "purchase_order",
    "confidence": 0.95,
    "description": "Brief description of document"
  }},
  "extracted_entities": {{
    "reference_numbers": [
      {{"type": "po_number", "value": "<reference_value>"}}
    ],
    "companies": [
      {{"role": "supplier", "name": "<company_name>"}}
    ],
    "line_items": [
      {{
        "row_number": 1,
        "extracted_fields": {{
          // USE ACTUAL COLUMN NAMES FROM THE TABLE HEADER
          // Example: if table shows [sku | title | quantity | date | total price]
          // Then use: {{"sku": "...", "title": "...", "quantity": ..., "date": "...", "total_price": "..."}}
        }}
      }}
    ],
    "totals": [
      {{"type": "subtotal", "value": 9999.00, "currency": "USD"}}
    ],
    "notes": "<any_special_instructions>"
  }},
  "ambiguities": [],
  
  // NOTE: Only populate ambiguities if there is genuine uncertainty. Examples of when to add:
  // [
  //   {{
  //     "field": "line_items[0].sku",
  //     "extracted": "SKU-I23",
  //     "alternatives": ["SKU-123", "SKU-I23"],
  //     "reason": "Character could be letter 'I' or number '1' due to image quality"
  //   }}
  // ]
  // If everything is clearly identified, keep ambiguities as empty array []
  
  "extraction_metadata": {{
    "confidence": 0.92,
    "document_quality": "good",
    "warnings": ["List any extraction concerns"]
  }}
}}

# CRITICAL RULES

1. **Extract exactly what you see** - Don't interpret or normalize
2. **Preserve formatting** - If document shows "PROD-ABC", extract "PROD-ABC" not "PROD ABC"
3. **READ column headers from the table** - Each document may have different column names:
   - Look at the table header row in the document
   - Use those EXACT column names as your field names in extracted_fields
   - Convert spaces to underscores (e.g., "total price" → "total_price")
   - Do NOT use generic names like "field1, field2" or invent your own names
   - Example: If table has columns [sku, title, quantity, date, total price], your JSON should have those exact fields
4. **Ambiguities only when needed** - Leave ambiguities array empty [] if everything is clearly identified
5. **All dates in ISO format** - Convert to YYYY-MM-DD in extracted value
6. **Complete line items** - Extract every field present in tables with their exact column names
7. **Flag OCR risks** - Characters that look similar (1/I, 0/O, S/5) only when genuinely ambiguous

# DATA TYPES

- Product codes/SKUs: Always extract as strings
- Quantities: Extract as integers
- Prices/amounts: Extract as floats
- Dates: ISO format strings (YYYY-MM-DD)
- Text fields: Preserve original formatting

Begin extraction.
"""


# Verification prompt - checks extraction against document
VERIFICATION_PROMPT = """You are verifying a document extraction for accuracy.

# CONTEXT

You will see:
1. The ORIGINAL DOCUMENT (image attached)
2. A CLAIMED EXTRACTION (JSON below)

Your job is to verify if the extraction matches what's actually in the document.

# CLAIMED EXTRACTION

{extraction_json}

# VERIFICATION TASK

Compare the claimed extraction against the original document image.

**KEY PRINCIPLE**: Only flag issues when there's a MISMATCH between document and extraction.
- If a field is missing from BOTH document and extraction → That's CORRECT, not an error
- Only flag missing_fields when data EXISTS in document but wasn't extracted
- Only flag issues when extracted value DIFFERS from document value

## 1. Document Classification
- Is the document type correct?

## 2. Reference Numbers
- Are all reference numbers accurately extracted?
- Any missing or incorrect?

## 3. Company Names
- Are company/supplier names correct?
- Spelling accurate?

## 4. Dates
- Are dates correctly read from document?
- Properly formatted?

## 5. Line Items (CRITICAL - Most Error-Prone)
For EACH line item, verify:
- **Product codes/SKUs**: Exactly as shown? Watch for:
  * 1 vs I (one vs letter i)
  * 0 vs O (zero vs letter o)
  * 5 vs S (five vs letter s)
  * Hyphens, spaces, underscores preserved correctly
- **Quantities**: Correct numbers?
- **Prices**: Accurate amounts?
- **All visible fields**: Match document?
- **Missing fields**: Any data VISIBLE in document but not extracted?
  * IMPORTANT: Only flag as missing if the field EXISTS in the document
  * If a field doesn't exist in the document AND wasn't extracted, that's CORRECT - don't flag it

## 6. Amounts/Totals
- Are totals and subtotals correct?

## 7. Notes/Terms
- Any important information missed?

# OUTPUT JSON

**IMPORTANT**: Return ONLY valid JSON. Do not include any text, explanations, or markdown before or after the JSON object.

{{
  "verified": true,
  "confidence": 0.95,
  "overall_assessment": "Extraction is accurate and complete",
  "field_verifications": [
    {{
      "field": "line_items[0].sku",
      "claimed_value": "<what_was_claimed>",
      "correct": true,
      "actual_value": "<what_you_see>",
      "notes": "Verified correct"
    }},
    {{
      "field": "line_items[1].quantity",
      "claimed_value": 999,
      "correct": false,
      "actual_value": 888,
      "notes": "Document shows 888, not 999 - likely OCR error"
    }}
  ],
  "issues": [],
  
  // NOTE: Only populate issues if there's a MISMATCH between document and extraction
  // Example of when to add:
  // [
  //   {{
  //     "field": "line_items[0].quantity",
  //     "severity": "high",
  //     "claimed": "100",
  //     "actual": "10",
  //     "description": "Document shows quantity '10' but extraction has '100'"
  //   }}
  // ]
  // If extraction matches document perfectly, leave issues as empty array []
  "missing_fields": [],
  
  // NOTE: Only populate missing_fields if data EXISTS in document but wasn't extracted
  // Example of when to add:
  // [
  //   {{
  //     "field": "line_items[2].delivery_date",
  //     "description": "Document shows delivery date '2024-01-15' in the table but wasn't extracted"
  //   }}
  // ]
  // If a field doesn't exist in the document, leave missing_fields as empty array []
  "statistics": {{
    "total_fields_checked": 10,
    "correct_fields": 9,
    "incorrect_fields": 1,
    "missing_fields": 0,
    "critical_errors": 0
  }}
}}

# SEVERITY LEVELS

- **high**: Wrong SKU, quantity, price, or critical reference number
- **medium**: Wrong date, description, or missing optional field
- **low**: Minor formatting issues that don't affect meaning

# CONFIDENCE SCORING

- 1.0: Perfect extraction, all fields verified correct
- 0.9-0.99: Excellent, minor issues only
- 0.8-0.89: Good, some errors but usable
- 0.7-0.79: Fair, multiple errors found
- < 0.7: Poor, significant errors, needs human review

# CRITICAL RULES

1. **Compare against the IMAGE** - Not your interpretation, the actual pixels
2. **Only flag ACTUAL mismatches** - If the extraction matches the document, it's correct:
   - If field is NOT in document AND NOT in extraction → CORRECT (no issue)
   - If field IS in document AND correctly extracted → CORRECT (no issue)
   - If field IS in document BUT NOT extracted → FLAG as missing_field
   - If field IS in document BUT extracted INCORRECTLY → FLAG as issue
3. **Don't invent issues** - Empty issues[] and missing_fields[] arrays mean perfect extraction
4. **Be strict on mismatches** - Any actual mismatch = flag it
5. **Don't hallucinate** - If you can't read something in the image, say so
6. **Pay attention to similar characters** - 1/I, 0/O, S/5 confusion is common
7. **Check completeness** - Did extraction miss any visible data in the document?

If the extraction matches the document: verified=true, confidence > 0.9, empty issues/missing_fields
If you found actual errors: verified=false, list ALL issues with details

Begin verification.
"""

