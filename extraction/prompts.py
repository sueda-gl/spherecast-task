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
VERIFICATION_PROMPT = """You are verifying a document extraction for DATA ACCURACY ONLY.

# YOUR ROLE

You are a practical verifier focused on BUSINESS-CRITICAL DATA ACCURACY. Your job is NOT to be pedantic about formatting - it's to ensure the extracted data can be used correctly for business operations.

# CONTEXT

You will see:
1. The ORIGINAL DOCUMENT (image attached)
2. A CLAIMED EXTRACTION (JSON below)

# CLAIMED EXTRACTION

{extraction_json}

# WHAT IS AN ACTUAL ISSUE?

An issue should ONLY be raised if it would cause a BUSINESS PROBLEM:
- Wrong quantity that would cause incorrect inventory/billing
- Wrong price that would cause financial errors
- Wrong SKU that would cause wrong product to be ordered/shipped
- Wrong reference number that would break traceability
- Missing critical data that would prevent processing

# WHAT IS NOT AN ISSUE - DO NOT FLAG THESE:

1. **Formatting/Styling Differences** - NEVER flag:
   - Text split across lines in document but concatenated in extraction
   - Different capitalization (unless it's a code/SKU)
   - Minor punctuation differences
   - Whitespace differences
   - Brackets, quotes, or formatting wrappers like [Confidential]
   - Line breaks merged into single text

2. **Equivalent Representations** - NEVER flag:
   - "product beta 2" vs "[Confidential] product beta 2" (same data, different format)
   - Date format variations (all are valid if date is correct)
   - Currency symbol placement differences
   - Number formatting (1,000 vs 1000)

3. **Subjective Interpretations** - NEVER flag:
   - How text is grouped or concatenated from multi-line entries
   - Whether descriptive text is "direct transcription" or "interpreted"
   - Style of field naming

# VERIFICATION TASK - FOCUS ONLY ON DATA ACCURACY

## 1. Reference Numbers - Is the VALUE correct?
## 2. SKUs/Product Codes - Is the CODE correct?
## 3. Quantities - Is the NUMBER correct?
## 4. Prices/Amounts - Is the AMOUNT correct?
## 5. Dates - Is the DATE correct?
## 6. Critical Names - Are COMPANY/SUPPLIER names identifiable?

# SIMILAR CHARACTER GUIDANCE (1/I, 0/O, 5/S, etc.)

**IMPORTANT**: Only flag character confusion if the extraction is ACTUALLY WRONG.

- Document shows "SKU-1A2B" and extraction has "SKU-1A2B" → CORRECT (no issue, even if 1 could theoretically look like I)
- Document shows "SKU-1A2B" but extraction has "SKU-IA2B" → ISSUE (the 1 was misread as I - this is a real error)

DO NOT flag theoretical possibilities. Only flag when you can SEE in the document that the character is different from what was extracted. If the extraction matches what's actually in the document, it's correct - don't second-guess it.

# DECISION FRAMEWORK

Ask yourself: "Does the extracted value MATCH what's in the document?"
- YES → Mark as CORRECT, do NOT raise an issue
- NO → Flag it with appropriate severity

Then ask: "Would this difference cause a business problem?"
- If extraction matches document → It's correct regardless of theoretical concerns

Examples:
- Title shows "Product A" on line 1 and "Model B" on line 2, extracted as "Product A Model B" → NO ISSUE (same data, just concatenated)
- Quantity shows "10" but extracted as "100" → ISSUE (actual mismatch, would cause 10x over-ordering)
- SKU shows "SKU-1A2B" and extraction has "SKU-1A2B" → NO ISSUE (matches exactly, don't flag theoretical 1/I concern)
- SKU shows "SKU-1A2B" but extraction has "SKU-IA2B" → ISSUE (actual 1→I error, wrong product)
- Description has extra formatting brackets → NO ISSUE (doesn't affect business logic)

# OUTPUT JSON

**IMPORTANT**: Return ONLY valid JSON. No text before or after.

**CRITICAL FOR ISSUES**: When there IS a mismatch, you MUST be EXTREMELY SPECIFIC:
- Include the EXACT value you see in the document image
- Include the EXACT value from the JSON extraction
- Explain PRECISELY what is different and why it matters
- Use the fields: document_value, extracted_value, and specific_difference

{{
  "verified": true,
  "confidence": 0.95,
  "overall_assessment": "Extraction data is accurate for business use",
  "field_verifications": [
    {{
      "field": "line_items[0].sku",
      "claimed_value": "<what_was_claimed>",
      "correct": true,
      "actual_value": "<what_you_see>",
      "notes": "Data matches"
    }}
  ],
  "issues": [],
  "missing_fields": [],
  "statistics": {{
    "total_fields_checked": 10,
    "correct_fields": 10,
    "incorrect_fields": 0,
    "missing_fields": 0,
    "critical_errors": 0
  }}
}}

## ISSUE FORMAT (REQUIRED when there's a mismatch):

When you find an issue, you MUST use this EXACT format with ALL fields:

{{
  "issues": [
    {{
      "field": "line_items[0].quantity",
      "severity": "high",
      "document_value": "50",
      "extracted_value": "500",
      "specific_difference": "The document clearly shows quantity '50' in the table row, but the JSON has '500'. This is a 10x error that would cause massive over-ordering.",
      "business_impact": "Would order 450 extra units, causing inventory and billing errors.",
      "location_in_document": "Row 1 of the line items table, 'Qty' column"
    }},
    {{
      "field": "reference_numbers[0].value",
      "severity": "high",
      "document_value": "PO-2024-001",
      "extracted_value": "PO-2024-OO1",
      "specific_difference": "The document shows 'PO-2024-001' with zeros, but the JSON has 'PO-2024-OO1' with letter O's instead of number 0's.",
      "business_impact": "PO reference won't match in the system, breaking traceability.",
      "location_in_document": "Header section, 'Purchase Order Number' field"
    }},
    {{
      "field": "line_items[2].sku",
      "severity": "high",
      "document_value": "PROD-1234",
      "extracted_value": "PROD-I234",
      "specific_difference": "The document shows 'PROD-1234' with number 1, but extraction has 'PROD-I234' with letter I. This is an OCR misread.",
      "business_impact": "Would order the wrong product entirely.",
      "location_in_document": "Row 3, 'SKU' column"
    }}
  ]
}}

# SEVERITY LEVELS (Only use if there's an ACTUAL data mismatch)

- **high**: Wrong SKU (would ship wrong product), wrong quantity (would bill incorrectly), wrong price (financial impact), wrong reference number (breaks traceability)
- **medium**: Missing critical field that exists in document
- **low**: RARELY USE - only for genuinely ambiguous characters where you're unsure

# CONFIDENCE SCORING

- 0.95-1.0: All data values are accurate (ignore formatting)
- 0.85-0.94: Minor uncertainty but data is usable
- 0.70-0.84: Some data questions need review
- < 0.70: Significant data accuracy concerns

# CRITICAL RULES - READ CAREFULLY

1. **DATA ACCURACY ONLY** - You're checking if extracted VALUES match document VALUES
2. **IGNORE FORMATTING** - How text is formatted, concatenated, or styled is NOT an issue
3. **BE LENIENT** - When in doubt, mark as CORRECT. Only flag CLEAR data mismatches.
4. **EMPTY ISSUES = GOOD** - Most extractions should have empty issues[] if data is accurate
5. **DON'T OVERTHINK** - If the data is recognizably the same, it's correct
6. **CONSISTENCY** - Apply the same standard every time. Don't randomly flag formatting one time and not another.
7. **BUSINESS FOCUS** - Would a human operator have a problem using this data? If no, it's fine.
8. **BE SPECIFIC ON ERRORS** - When there IS an error, be EXTREMELY specific. Include exact values from both document and JSON.

The goal is to let accurate extractions through for automatic processing, not to find nitpicky issues.
But when there ARE real errors, explain them clearly so humans understand exactly what went wrong.

Begin verification.
"""

