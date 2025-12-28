"""
Generic Planning LLM - Reasons from schema to determine database operations.

This is an LLM Engineering approach:
- LLM receives rich schema context (FKs, relationships, current data)
- LLM reasons about what database state is needed
- LLM outputs standard INSERT/UPDATE operations
- Works for ANY relational schema, not just this specific one
"""

import json
from typing import Dict, Any
from sqlalchemy import inspect, text

from llm_client import LLMClient
from reasoning.schema_builder import RichSchemaBuilder


# Generic reasoning prompt - works for any relational schema
PLANNING_PROMPT = """You are a database operations planner. Given input data and the current database state, determine what SQL operations are needed.

{schema}

======================================================================
INPUT DATA
======================================================================

## CONTEXT (email/message)
{email_body}

## STRUCTURED DATA (extracted from documents)
{extracted_data}

======================================================================
YOUR TASK
======================================================================

Determine what INSERT and UPDATE operations are needed to correctly represent this data in the database.

## CORE LOGIC: INSERT vs UPDATE DECISION

This is the most critical decision. For EVERY record you need to add or modify:

### Step 1: Identify the Record's Identity
Each table has columns that uniquely identify a record:
- Look at PRIMARY KEY columns
- Look at UNIQUE constraints  
- Look at logical identity from table notes (e.g., a junction table's identity is its FK combination)

### Step 2: Check if Record Exists
Look in the CURRENT DATA section of the schema:
- Search for a row matching the identity columns
- If you find a match → the record EXISTS
- If no match → the record DOES NOT EXIST

### Step 3: Choose Operation
- Record EXISTS → use UPDATE (modify existing row)
- Record DOES NOT EXIST → use INSERT (create new row)

### Example Reasoning Pattern:
```
I need to add/modify data for table X with identity values (col1=A, col2=B)
→ Check CURRENT DATA for table X
→ Is there a row where col1=A AND col2=B?
→ YES: UPDATE that row
→ NO: INSERT new row
```

## FOREIGN KEY DEPENDENCIES

Before inserting into any table, ensure all referenced records exist:

1. Check the FOREIGN KEYS listed for the table
2. For each FK, verify the referenced record exists in CURRENT DATA
3. If parent doesn't exist, INSERT parent FIRST
4. Follow the INSERTION ORDER shown in the schema

Use placeholder "__NEW_<table>_id" when referencing a record you're creating in the same plan.
The executor will substitute the actual ID.

## ENTITY RESOLUTION

When matching values from input to database records:
1. Try exact match first
2. Try normalized variants (with/without prefixes, different formatting)
3. Use contextual hints (related records, table notes) to disambiguate
4. If unresolved → may need to INSERT new record

## INPUT CONTEXT

The input may contain:
- Instructions that override or supplement the structured data
- Contextual information about what action to take
- References to existing records that need updating

Read both the context AND structured data to understand the full intent.

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "reasoning": {{
    "input_analysis": {{
      "intent": "<what the input is asking to do>",
      "key_entities": ["<list of main entities/records involved>"],
      "context_instructions": ["<any special instructions from the context>"]
    }},
    "entity_resolution": {{
      "<input_identifier>": {{
        "resolved_to": "<table.column = value>",
        "method": "<exact / normalized / contextual / unresolved>",
        "confidence": "<high / medium / low>"
      }}
    }},
    "existence_checks": {{
      "<table_name>": {{
        "<identity_description>": {{
          "identity_values": {{"<col>": "<val>"}},
          "found_in_data": <true/false>,
          "decision": "<INSERT or UPDATE>",
          "reason": "<why this decision>"
        }}
      }}
    }},
    "dependency_order": ["<table1>", "<table2>", "..."],
    "junction_table_check": {{
      "<new_record_table>": {{
        "junction_tables_checked": ["<list of junction tables that could link this>"],
        "inserts_needed": ["<junction tables that need INSERT>"],
        "reason": "<why or why not>"
      }}
    }}
  }},
  "operations": [
    {{
      "operation": "INSERT",
      "table": "<table_name>",
      "values": {{"<column>": "<value>"}},
      "reason": "<why this record needs to be created>"
    }},
    {{
      "operation": "UPDATE",
      "table": "<table_name>",
      "where": {{"<identity_col>": "<value>"}},
      "set": {{"<column>": "<new_value>"}},
      "reason": "<why this record needs to be updated>"
    }}
  ],
  "confidence": <0.0-1.0>,
  "warnings": ["<any ambiguities or concerns>"]
}}

## CRITICAL RULES

1. **Always check existence first**: Never INSERT if a matching record already exists. Never UPDATE if the record doesn't exist.

2. **Respect FK constraints**: Operations will fail if you reference non-existent parent records.

3. **Use table notes**: The schema includes PURPOSE and NOTES for each table - these explain business logic and special considerations. READ THEM CAREFULLY.

4. **Complete the data model**: If the input contains entities that span multiple related tables, create/update ALL necessary records.

5. **JUNCTION TABLE RULE - MANDATORY**: 
   When you INSERT a new record, you MUST check ALL junction tables that reference it.
   
   Pattern to follow:
   - Look at schema for tables where this new record could be an FK target
   - If any is a junction table (links two entities), INSERT into it too
   
   Example: When INSERTing a new product from supplier data:
   → Check: Does supplier_product link supplier and product? YES
   → Therefore: MUST INSERT supplier_product (supplier_id, product_id, supplier_sku)
   → Use: supplier_id from the document's supplier, product_id = "__NEW_product_id"
   
   WITHOUT this junction INSERT, the relationship between supplier and product doesn't exist!

6. **Placeholder syntax**: Use "__NEW_<table>_id" for FK references to records being created in the same plan.

7. **Dates in ISO format**: YYYY-MM-DD
"""


class PlanningLLM:
    """
    Generic LLM planner that reasons from schema to operations.
    
    Key difference from case-specific prompting:
    - Receives rich schema with FKs, relationships, business context
    - Reasons about what state is needed
    - Outputs standard SQL operations (INSERT/UPDATE)
    - Works for any relational schema
    """
    
    def __init__(self, engine, api_key: str = None, model: str = "gpt-5.2"):
        """
        Initialize planner.
        
        Args:
            engine: SQLAlchemy engine for schema fetching
            api_key: OpenAI API key
            model: LLM model to use
        """
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
        Generate operation plan from input data.
        
        Args:
            email_body: Context/instructions (email, message, etc.)
            extracted_data: Structured data extracted from documents
            verbose: Print progress
            
        Returns:
            Structured plan with reasoning and operations
        """
        
        if verbose:
            print(f"\n{'='*70}")
            print("PLANNING LLM - Generic Schema Reasoning")
            print(f"{'='*70}")
        
        # Step 1: Build rich schema context
        if verbose:
            print("\n[1/2] Building schema context...")
        
        schema_text = self.schema_builder.format_for_llm()
        
        if verbose:
            print(f"  ✓ Schema ready ({len(schema_text)} chars)")
        
        # Step 2: Single LLM call with reasoning
        if verbose:
            print("\n[2/2] LLM reasoning about operations...")
        
        prompt = PLANNING_PROMPT.format(
            schema=schema_text,
            email_body=email_body,
            extracted_data=json.dumps(extracted_data, indent=2)
        )
        
        try:
            plan = self.llm.call_with_text(
                prompt="You are a database operations planner. Analyze the input and return a JSON operation plan.",
                text=prompt,
                json_mode=True
            )
            
            if verbose:
                self._print_plan_summary(plan)
            
            return {
                "success": True,
                "plan": plan
            }
            
        except Exception as e:
            if verbose:
                print(f"\n✗ Planning failed: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "plan": None
            }
    
    def _print_plan_summary(self, plan: dict):
        """Print summary of the generated plan."""
        
        print(f"\n{'─'*70}")
        print("PLAN SUMMARY")
        print(f"{'─'*70}")
        
        reasoning = plan.get("reasoning", {})
        
        # Input analysis
        analysis = reasoning.get("input_analysis", {})
        if analysis:
            print(f"\n📋 Intent: {analysis.get('intent', 'Unknown')}")
            entities = analysis.get("key_entities", [])
            if entities:
                print(f"   Entities: {', '.join(entities[:5])}")
            instructions = analysis.get("context_instructions", [])
            if instructions:
                print(f"   Instructions: {instructions[0][:60]}..." if instructions else "")
        
        # Entity resolution - handle both dict and list formats
        entities = reasoning.get("entity_resolution", {})
        if entities:
            print(f"\n🔍 Entity Resolution:")
            try:
                if isinstance(entities, dict):
                    for input_id, info in list(entities.items())[:6]:
                        if isinstance(info, dict):
                            resolved = info.get("resolved_to", "unresolved")
                            method = info.get("method", "?")
                            print(f"   {input_id} → {resolved} ({method})")
                        else:
                            print(f"   {input_id} → {info}")
                elif isinstance(entities, list):
                    for item in entities[:6]:
                        if isinstance(item, dict):
                            input_id = item.get("from_input", item.get("input", "?"))
                            resolved = item.get("resolved_to", item.get("matched_to", "unresolved"))
                            method = item.get("method", item.get("resolution_method", "?"))
                            print(f"   {input_id} → {resolved} ({method})")
                        else:
                            print(f"   {item}")
            except Exception as e:
                print(f"   (could not parse: {e})")
        
        # Existence checks - handle both dict and list formats
        checks = reasoning.get("existence_checks", {})
        if checks:
            print(f"\n📊 Existence Checks:")
            try:
                if isinstance(checks, dict):
                    for table, table_checks in checks.items():
                        if isinstance(table_checks, dict):
                            for desc, check in table_checks.items():
                                if isinstance(check, dict):
                                    found = "EXISTS" if check.get("found_in_data") else "NOT FOUND"
                                    decision = check.get("decision", "?")
                                    print(f"   {table}: {found} → {decision}")
                                else:
                                    print(f"   {table}.{desc}: {check}")
                        else:
                            print(f"   {table}: {table_checks}")
                elif isinstance(checks, list):
                    for check in checks[:5]:
                        if isinstance(check, dict):
                            table = check.get("table", "?")
                            found = "EXISTS" if check.get("found_in_data", check.get("exists")) else "NOT FOUND"
                            decision = check.get("decision", check.get("action", "?"))
                            print(f"   {table}: {found} → {decision}")
                        else:
                            print(f"   {check}")
            except Exception as e:
                print(f"   (could not parse: {e})")
        
        # Operations
        operations = plan.get("operations", [])
        print(f"\n🔧 Operations ({len(operations)}):")
        for i, op in enumerate(operations, 1):
            op_type = op.get("operation")
            table = op.get("table")
            
            if op_type == "INSERT":
                values = op.get("values", {})
                preview = ", ".join(f"{k}={v}" for k, v in list(values.items())[:3])
                print(f"   {i}. INSERT {table}: {preview}...")
            elif op_type == "UPDATE":
                where = op.get("where", {})
                set_vals = op.get("set", {})
                print(f"   {i}. UPDATE {table} WHERE {where} SET {set_vals}")
            else:
                print(f"   {i}. {op_type} {table}")
            
            reason = op.get("reason", "")
            if reason:
                print(f"      → {reason[:70]}")
        
        # Confidence & warnings
        print(f"\n📊 Confidence: {plan.get('confidence', 0):.0%}")
        
        warnings = plan.get("warnings", [])
        if warnings:
            print(f"⚠️  Warnings: {warnings}")
        
        print(f"{'─'*70}\n")
