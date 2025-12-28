"""
Chain Planner - Multi-step LLM architecture for reliable database operations.

Instead of one big LLM call that juggles many concerns, this breaks planning
into focused steps:

1. Entity Resolution - Match input entities to database records
2. Existence Analysis - Decide INSERT vs UPDATE for each record
3. Relationship Check - Identify junction table inserts needed
4. Operation Generation - Generate final SQL operations

Each step validates the previous step's output before proceeding.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from llm_client import LLMClient
from reasoning.schema_builder import RichSchemaBuilder


# ============================================================================
# STEP 1: ENTITY RESOLUTION
# ============================================================================

ENTITY_RESOLUTION_PROMPT = """You are an entity resolution specialist. Match entities from the input to existing database records.

## DATABASE CURRENT STATE

{db_snapshot}

## INPUT DATA

Context (email):
{email_body}

Extracted data:
{extracted_data}

## YOUR TASK

For each identifier in the input (SKUs, reference numbers, etc.), find the matching database record.

Resolution methods:
- **exact**: Direct match (e.g., "SKU-1" matches product.sku = "SKU-1")
- **normalized**: Match after normalization (e.g., "12" matches "PO-12", "SKU13" matches "SKU-1-3")
- **contextual**: Match using context (e.g., supplier_product mapping for vendor SKUs)
- **unresolved**: No match found - this is a NEW entity

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "supplier": {{
    "identified_from": "<how you identified the supplier - email domain, document header, etc.>",
    "supplier_id": <int or null if not found>,
    "supplier_name": "<name>",
    "is_new": <true if supplier not in database, false if found>
  }},
  "purchase_order": {{
    "input_reference": "<reference from document>",
    "matched_po_id": <int or null>,
    "matched_reference": "<reference in DB>",
    "match_method": "<exact/normalized/unresolved>",
    "is_new": <true/false>
  }},
  "products": {{
    "<input_sku>": {{
      "product_id": <int or null>,
      "internal_sku": "<sku in product table or null>",
      "match_method": "<exact/normalized/contextual/unresolved>",
      "is_new": <true/false>,
      "title_from_input": "<product title if available>"
    }}
  }},
  "context_instructions": [
    "<any special instructions from email that override document values>"
  ]
}}
"""


# ============================================================================
# STEP 2: EXISTENCE ANALYSIS
# ============================================================================

EXISTENCE_ANALYSIS_PROMPT = """You are a database analyst. Determine what operations are needed for each entity.

## SCHEMA IDENTITY RULES

{identity_rules}

## CURRENT DATA

{current_data}

## RESOLVED ENTITIES (from previous step)

{resolved_entities}

## YOUR TASK

For each entity, check if a corresponding record EXISTS in the database.
- If EXISTS → operation is UPDATE
- If NOT EXISTS → operation is INSERT

Key rules:
- For purchase_order_line: identity is (purchase_order_id, product_id)
- For supplier_product: identity is (supplier_id, product_id)
- Check the CURRENT DATA section to see what records exist

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "supplier": {{
    "supplier_id": <int or null>,
    "exists": <true/false>,
    "operation": "<INSERT or NONE>",
    "reason": "<why>",
    "name": "<supplier name if INSERT needed>"
  }},
  "products": {{
    "<sku>": {{
      "product_id": <int or null for new>,
      "exists": <true/false>,
      "operation": "<INSERT or UPDATE or NONE>",
      "reason": "<why this decision>"
    }}
  }},
  "purchase_order": {{
    "po_id": <int or null>,
    "exists": <true/false>,
    "operation": "<INSERT or UPDATE or NONE>",
    "reason": "<why>"
  }},
  "purchase_order_lines": {{
    "<sku>": {{
      "po_id": <int>,
      "product_id": <int or null for new products>,
      "exists": <true/false>,
      "operation": "<INSERT or UPDATE>",
      "reason": "<why>"
    }}
  }}
}}
"""


# ============================================================================
# STEP 3: RELATIONSHIP CHECK
# ============================================================================

RELATIONSHIP_CHECK_PROMPT = """You are a database relationship analyst. Check what junction table records are needed.

## JUNCTION TABLES IN SCHEMA

{junction_tables}

## ENTITIES BEING INSERTED (from previous step)

{inserts_planned}

## SUPPLIER CONTEXT

Supplier ID: {supplier_id}

## YOUR TASK

For each NEW entity being inserted, check if any junction table records need to be created.

CRITICAL RULE: When a new entity is inserted, check if any junction tables need records too.
Junction tables link entities together - without the junction record, the relationship doesn't exist.

## HOW TO FILL VALUES

For each junction table INSERT:
1. Look at the table's COLUMNS in the schema
2. For EACH column, determine the appropriate value:
   - FK columns: use the ID or __NEW_<table>_id placeholder
   - Data columns: extract from the input data (document, email, context)
3. Do NOT leave columns empty if you have the data available

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "junction_inserts_needed": [
    {{
      "table": "<junction table name>",
      "reason": "<why this is needed>",
      "values": {{
        "<column_name>": "<value based on schema and available data>"
      }}
    }}
  ],
  "validation": {{
    "all_relationships_covered": <true/false>,
    "all_columns_filled": <true/false>,
    "warnings": ["<any concerns>"]
  }}
}}
"""


# ============================================================================
# STEP 4: OPERATION GENERATION
# ============================================================================

OPERATION_GENERATION_PROMPT = """You are a SQL operation generator. Generate the final database operations.

## SCHEMA

{schema}

## ORIGINAL EXTRACTED DATA (from document)

{extracted_data}

## ANALYSIS FROM PREVIOUS STEPS

Entity Resolution:
{entity_resolution}

Existence Analysis:
{existence_analysis}

Relationship Check:
{relationship_check}

## CONTEXT INSTRUCTIONS (from email)

{context_instructions}

## YOUR TASK

Generate the final list of INSERT and UPDATE operations.

Rules:
1. Order operations by dependency:
   - supplier (if new) → FIRST
   - products → SECOND
   - purchase_order → THIRD (needs supplier_id)
   - junction tables (supplier_product) → FOURTH
   - purchase_order_lines → LAST (needs purchase_order_id and product_id)
2. Use "__NEW_<table>_id" placeholders for FK references to newly created records
3. Include all junction table inserts identified in relationship check
4. Apply any context instructions (e.g., "push back ETA to 2027")
5. For UPDATEs, only set fields that have new values

## CRITICAL: FILL ALL COLUMNS - WHERE TO GET DATA

For EVERY INSERT operation:
1. Look at the table's columns in the SCHEMA - check NOT NULL constraints!
2. For EACH column, get the value from the correct source:

   **FK columns** (columns ending in _id like supplier_id, product_id, purchase_order_id):
   - Get from ENTITY RESOLUTION results (resolved IDs)
   - If entity is being created in this plan, use __NEW_<table>_id placeholder
   
   **Data columns** (quantity, delivery_date, title, sku, etc.):
   - Get from ORIGINAL EXTRACTED DATA (document fields, line items)
   - Match by meaning: qty→quantity, date→delivery_date, etc.

3. NEVER leave NOT NULL columns as null - the INSERT will fail
4. If a required FK isn't resolved and entity isn't being created, you MUST create it first

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "operations": [
    {{
      "operation": "INSERT",
      "table": "<table_name>",
      "values": {{"<column>": "<value>"}},
      "reason": "<why>"
    }},
    {{
      "operation": "UPDATE",
      "table": "<table_name>",
      "where": {{"<column>": "<value>"}},
      "set": {{"<column>": "<new_value>"}},
      "reason": "<why>"
    }}
  ],
  "summary": {{
    "total_inserts": <int>,
    "total_updates": <int>,
    "tables_affected": ["<table1>", "<table2>"]
  }}
}}
"""


@dataclass
class ChainResult:
    """Result from a chain step."""
    success: bool
    step: str
    data: Dict[str, Any]
    error: Optional[str] = None


class ChainPlanner:
    """
    Multi-step LLM planner with focused calls.
    
    Each step has a single responsibility:
    1. Entity Resolution - Match inputs to DB records
    2. Existence Analysis - INSERT vs UPDATE decisions
    3. Relationship Check - Junction table needs
    4. Operation Generation - Final SQL operations
    """
    
    def __init__(self, engine, api_key: str = None, model: str = "gpt-5.2"):
        self.engine = engine
        self.schema_builder = RichSchemaBuilder(engine)
        self.llm = LLMClient(api_key=api_key, model=model, temperature=0.0)
    
    def plan(
        self,
        email_body: str,
        extracted_data: dict,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Generate operation plan through chain of focused LLM calls.
        """
        
        if verbose:
            print(f"\n{'='*70}")
            print("CHAIN PLANNER - Multi-Step Architecture")
            print(f"{'='*70}")
        
        # Build schema context once
        schema = self.schema_builder.build()
        schema_text = self.schema_builder.format_for_llm()
        
        # ================================================================
        # STEP 1: Entity Resolution
        # ================================================================
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 1: Entity Resolution")
            print(f"{'─'*70}")
        
        step1_result = self._step1_entity_resolution(
            email_body, extracted_data, schema, verbose
        )
        
        if not step1_result.success:
            return {"success": False, "error": f"Step 1 failed: {step1_result.error}"}
        
        entity_resolution = step1_result.data
        
        # ================================================================
        # STEP 2: Existence Analysis
        # ================================================================
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 2: Existence Analysis")
            print(f"{'─'*70}")
        
        step2_result = self._step2_existence_analysis(
            entity_resolution, schema, verbose
        )
        
        if not step2_result.success:
            return {"success": False, "error": f"Step 2 failed: {step2_result.error}"}
        
        existence_analysis = step2_result.data
        
        # ================================================================
        # STEP 3: Relationship Check
        # ================================================================
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 3: Relationship Check")
            print(f"{'─'*70}")
        
        step3_result = self._step3_relationship_check(
            entity_resolution, existence_analysis, schema, verbose
        )
        
        if not step3_result.success:
            return {"success": False, "error": f"Step 3 failed: {step3_result.error}"}
        
        relationship_check = step3_result.data
        
        # ================================================================
        # STEP 4: Operation Generation
        # ================================================================
        if verbose:
            print(f"\n{'─'*70}")
            print("STEP 4: Operation Generation")
            print(f"{'─'*70}")
        
        step4_result = self._step4_operation_generation(
            entity_resolution, existence_analysis, relationship_check,
            extracted_data, schema_text, verbose
        )
        
        if not step4_result.success:
            return {"success": False, "error": f"Step 4 failed: {step4_result.error}"}
        
        operations = step4_result.data
        
        # ================================================================
        # Final Summary
        # ================================================================
        if verbose:
            print(f"\n{'='*70}")
            print("CHAIN COMPLETE")
            print(f"{'='*70}")
            summary = operations.get("summary", {})
            print(f"  INSERTs: {summary.get('total_inserts', 0)}")
            print(f"  UPDATEs: {summary.get('total_updates', 0)}")
            print(f"  Tables: {summary.get('tables_affected', [])}")
        
        return {
            "success": True,
            "plan": operations,
            "chain_results": {
                "entity_resolution": entity_resolution,
                "existence_analysis": existence_analysis,
                "relationship_check": relationship_check
            }
        }
    
    # ========================================================================
    # STEP IMPLEMENTATIONS
    # ========================================================================
    
    def _step1_entity_resolution(
        self,
        email_body: str,
        extracted_data: dict,
        schema: dict,
        verbose: bool
    ) -> ChainResult:
        """Step 1: Match input entities to database records."""
        
        # Build DB snapshot for entity matching
        db_snapshot = self._format_db_snapshot(schema["data_snapshot"])
        
        prompt = ENTITY_RESOLUTION_PROMPT.format(
            db_snapshot=db_snapshot,
            email_body=email_body,
            extracted_data=json.dumps(extracted_data, indent=2)
        )
        
        try:
            result = self.llm.call_with_text(
                prompt="You are an entity resolution specialist. Return JSON.",
                text=prompt,
                json_mode=True
            )
            
            if verbose:
                self._print_step1_summary(result)
            
            return ChainResult(success=True, step="entity_resolution", data=result)
            
        except Exception as e:
            if verbose:
                print(f"  ✗ Error: {e}")
            return ChainResult(success=False, step="entity_resolution", data={}, error=str(e))
    
    def _step2_existence_analysis(
        self,
        entity_resolution: dict,
        schema: dict,
        verbose: bool
    ) -> ChainResult:
        """Step 2: Determine INSERT vs UPDATE for each entity."""
        
        # Build identity rules from schema
        identity_rules = self._format_identity_rules(schema["tables"])
        
        # Format current data
        current_data = self._format_current_data(schema["data_snapshot"])
        
        prompt = EXISTENCE_ANALYSIS_PROMPT.format(
            identity_rules=identity_rules,
            current_data=current_data,
            resolved_entities=json.dumps(entity_resolution, indent=2)
        )
        
        try:
            result = self.llm.call_with_text(
                prompt="You are a database analyst. Return JSON.",
                text=prompt,
                json_mode=True
            )
            
            if verbose:
                self._print_step2_summary(result)
            
            return ChainResult(success=True, step="existence_analysis", data=result)
            
        except Exception as e:
            if verbose:
                print(f"  ✗ Error: {e}")
            return ChainResult(success=False, step="existence_analysis", data={}, error=str(e))
    
    def _step3_relationship_check(
        self,
        entity_resolution: dict,
        existence_analysis: dict,
        schema: dict,
        verbose: bool
    ) -> ChainResult:
        """Step 3: Check what junction table records are needed."""
        
        # Get junction tables info
        junction_tables = self._format_junction_tables(schema["tables"])
        
        # Get planned inserts
        inserts_planned = self._extract_inserts(existence_analysis)
        
        # Get supplier ID
        supplier_id = entity_resolution.get("supplier", {}).get("supplier_id")
        
        prompt = RELATIONSHIP_CHECK_PROMPT.format(
            junction_tables=junction_tables,
            inserts_planned=json.dumps(inserts_planned, indent=2),
            supplier_id=supplier_id
        )
        
        try:
            result = self.llm.call_with_text(
                prompt="You are a database relationship analyst. Return JSON.",
                text=prompt,
                json_mode=True
            )
            
            if verbose:
                self._print_step3_summary(result)
            
            return ChainResult(success=True, step="relationship_check", data=result)
            
        except Exception as e:
            if verbose:
                print(f"  ✗ Error: {e}")
            return ChainResult(success=False, step="relationship_check", data={}, error=str(e))
    
    def _step4_operation_generation(
        self,
        entity_resolution: dict,
        existence_analysis: dict,
        relationship_check: dict,
        extracted_data: dict,
        schema_text: str,
        verbose: bool
    ) -> ChainResult:
        """Step 4: Generate final SQL operations."""
        
        context_instructions = entity_resolution.get("context_instructions", [])
        
        prompt = OPERATION_GENERATION_PROMPT.format(
            schema=schema_text,
            entity_resolution=json.dumps(entity_resolution, indent=2),
            existence_analysis=json.dumps(existence_analysis, indent=2),
            relationship_check=json.dumps(relationship_check, indent=2),
            extracted_data=json.dumps(extracted_data, indent=2),
            context_instructions=json.dumps(context_instructions, indent=2)
        )
        
        try:
            result = self.llm.call_with_text(
                prompt="You are a SQL operation generator. Return JSON.",
                text=prompt,
                json_mode=True
            )
            
            if verbose:
                self._print_step4_summary(result)
            
            return ChainResult(success=True, step="operation_generation", data=result)
            
        except Exception as e:
            if verbose:
                print(f"  ✗ Error: {e}")
            return ChainResult(success=False, step="operation_generation", data={}, error=str(e))
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _format_db_snapshot(self, snapshot: dict) -> str:
        """Format database snapshot for entity resolution."""
        lines = []
        
        lines.append("### PRODUCTS")
        for p in snapshot.get("products", []):
            lines.append(f"  id={p['id']}, sku='{p['sku']}', title='{p.get('title', '')}'")
        
        lines.append("\n### SUPPLIERS")
        for s in snapshot.get("suppliers", []):
            lines.append(f"  id={s['id']}, name='{s['name']}', email='{s.get('email', '')}'")
        
        lines.append("\n### SUPPLIER-PRODUCT MAPPINGS (vendor SKU → internal)")
        for m in snapshot.get("supplier_product_mappings", []):
            vendor_sku = m.get('supplier_sku') or '(internal)'
            lines.append(f"  supplier_id={m['supplier_id']}: '{vendor_sku}' → product_id={m['product_id']} (internal: '{m.get('internal_sku', '')}')")
        
        lines.append("\n### PURCHASE ORDERS")
        for po in snapshot.get("purchase_orders", []):
            lines.append(f"  id={po['id']}, reference='{po['reference_num']}', supplier_id={po['supplier_id']}")
        
        lines.append("\n### PURCHASE ORDER LINES")
        for pol in snapshot.get("purchase_order_lines", []):
            lines.append(f"  po_id={pol['purchase_order_id']}, product_id={pol['product_id']} ({pol.get('sku', '')}), qty={pol['quantity']}")
        
        return "\n".join(lines)
    
    def _format_identity_rules(self, tables: dict) -> str:
        """Format identity rules for existence analysis."""
        lines = []
        for table_name, info in tables.items():
            identity = info.get("identity", info.get("primary_key", []))
            identity_note = info.get("identity_note", "")
            lines.append(f"### {table_name.upper()}")
            lines.append(f"  IDENTITY: ({', '.join(identity)})")
            if identity_note:
                lines.append(f"  → {identity_note}")
            lines.append("")
        return "\n".join(lines)
    
    def _format_current_data(self, snapshot: dict) -> str:
        """Format current data for existence checks."""
        lines = []
        
        lines.append("### PURCHASE ORDER LINES (check by po_id + product_id)")
        for pol in snapshot.get("purchase_order_lines", []):
            lines.append(f"  (po_id={pol['purchase_order_id']}, product_id={pol['product_id']}): qty={pol['quantity']}, date={pol.get('delivery_date')}")
        
        lines.append("\n### SUPPLIER_PRODUCT (check by supplier_id + product_id)")
        for m in snapshot.get("supplier_product_mappings", []):
            lines.append(f"  (supplier_id={m['supplier_id']}, product_id={m['product_id']}): supplier_sku='{m.get('supplier_sku', '')}'")
        
        return "\n".join(lines)
    
    def _format_junction_tables(self, tables: dict) -> str:
        """Format junction table info."""
        lines = []
        for table_name, info in tables.items():
            if info.get("is_junction_table"):
                lines.append(f"### {table_name.upper()}")
                lines.append(f"  Purpose: {info.get('purpose', '')}")
                lines.append(f"  Identity: ({', '.join(info.get('identity', []))})")
                lines.append(f"  Notes: {info.get('notes', '')}")
                lines.append("")
        return "\n".join(lines) if lines else "No junction tables defined."
    
    def _extract_inserts(self, existence_analysis: dict) -> dict:
        """Extract planned INSERTs from existence analysis."""
        inserts = {"products": [], "purchase_order_lines": []}
        
        products = existence_analysis.get("products", {})
        for sku, info in products.items():
            if info.get("operation") == "INSERT":
                inserts["products"].append({"sku": sku, **info})
        
        po_lines = existence_analysis.get("purchase_order_lines", {})
        for sku, info in po_lines.items():
            if info.get("operation") == "INSERT":
                inserts["purchase_order_lines"].append({"sku": sku, **info})
        
        return inserts
    
    # ========================================================================
    # PRINT HELPERS
    # ========================================================================
    
    def _print_step1_summary(self, result: dict):
        """Print Step 1 summary."""
        print("\n  📍 Entity Resolution Results:")
        
        supplier = result.get("supplier", {})
        print(f"    Supplier: {supplier.get('supplier_name', 'Unknown')} (id={supplier.get('supplier_id')})")
        
        po = result.get("purchase_order", {})
        print(f"    PO: '{po.get('input_reference')}' → {po.get('matched_reference')} (id={po.get('matched_po_id')})")
        print(f"        Method: {po.get('match_method')}, New: {po.get('is_new')}")
        
        products = result.get("products", {})
        print(f"    Products: {len(products)}")
        for sku, info in products.items():
            status = "NEW" if info.get("is_new") else f"id={info.get('product_id')}"
            print(f"      {sku} → {status} ({info.get('match_method')})")
        
        instructions = result.get("context_instructions", [])
        if instructions:
            print(f"    Instructions: {instructions}")
    
    def _print_step2_summary(self, result: dict):
        """Print Step 2 summary."""
        print("\n  📊 Existence Analysis Results:")
        
        products = result.get("products", {})
        for sku, info in products.items():
            print(f"    product.{sku}: {info.get('operation')} ({info.get('reason', '')[:50]})")
        
        po = result.get("purchase_order", {})
        print(f"    purchase_order: {po.get('operation')} ({po.get('reason', '')[:50]})")
        
        po_lines = result.get("purchase_order_lines", {})
        for sku, info in po_lines.items():
            print(f"    po_line.{sku}: {info.get('operation')}")
    
    def _print_step3_summary(self, result: dict):
        """Print Step 3 summary."""
        print("\n  🔗 Relationship Check Results:")
        
        junction_inserts = result.get("junction_inserts_needed", [])
        if junction_inserts:
            print(f"    Junction INSERTs needed: {len(junction_inserts)}")
            for ji in junction_inserts:
                print(f"      → {ji.get('table')}: {ji.get('reason', '')[:50]}")
        else:
            print("    No junction INSERTs needed")
        
        validation = result.get("validation", {})
        if validation.get("warnings"):
            print(f"    ⚠️ Warnings: {validation['warnings']}")
    
    def _print_step4_summary(self, result: dict):
        """Print Step 4 summary."""
        print("\n  🔧 Generated Operations:")
        
        operations = result.get("operations", [])
        for i, op in enumerate(operations, 1):
            op_type = op.get("operation")
            table = op.get("table")
            
            if op_type == "INSERT":
                values = op.get("values", {})
                preview = ", ".join(f"{k}={v}" for k, v in list(values.items())[:3])
                print(f"    {i}. INSERT {table}: {preview}...")
            elif op_type == "UPDATE":
                where = op.get("where", {})
                set_vals = op.get("set", {})
                print(f"    {i}. UPDATE {table} WHERE {where} SET {set_vals}")

