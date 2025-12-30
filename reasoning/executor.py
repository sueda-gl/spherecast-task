"""
Generic Operation Executor - Executes INSERT/UPDATE operations from LLM plan.

This executor:
- Handles standard SQL operations (INSERT, UPDATE)
- Tracks created IDs for FK substitution
- Maintains transaction integrity
- Works for any table structure
"""

from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import text, inspect
import re


class OperationExecutor:
    """
    Executes generic SQL operations from LLM plan.
    
    Key features:
    - Handles "__NEW_<table>_id" placeholder substitution
    - Transaction support (all-or-nothing)
    - Detailed audit logging
    """
    
    def __init__(self, engine, update_tracker=None):
        """
        Initialize executor.
        
        Args:
            engine: SQLAlchemy engine
            update_tracker: Optional UpdateAuditTracker for logging
        """
        self.engine = engine
        self.update_tracker = update_tracker
        
        # Get table metadata for column info
        self.inspector = inspect(engine)
        self.table_columns = {}
        for table_name in self.inspector.get_table_names():
            self.table_columns[table_name] = [
                col["name"] for col in self.inspector.get_columns(table_name)
            ]
    
    def execute(
        self,
        plan: dict,
        extraction_id: int = None,
        source_document_path: str = None,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Execute operation plan.
        
        Args:
            plan: Operation plan from ChainPlanner
            extraction_id: For audit logging
            source_document_path: For audit logging
            verbose: Print progress
            
        Returns:
            Execution result with created/updated record IDs
        """
        
        if verbose:
            print(f"\n{'='*70}")
            print("EXECUTOR - Running operations")
            print(f"{'='*70}")
        
        results = {
            "success": True,
            "operations_executed": [],
            "records_created": [],
            "records_updated": [],
            "errors": []
        }
        
        operations = plan.get("operations", [])
        
        if not operations:
            if verbose:
                print("\n⚠️  No operations to execute")
            return results
        
        if verbose:
            print(f"\n📋 Executing {len(operations)} operations...")
        
        # Track newly created IDs for placeholder substitution
        # Uses CANONICAL format: "table:identifier" for bulletproof matching
        # e.g., "product:SKU-7" → 6, "purchase_order:TR-45678" → 3
        created_ids = {}
        # Also store by table for generic lookups (last created of each type)
        created_by_table = {}
        
        try:
            with self.engine.begin() as conn:
                for i, op in enumerate(operations, 1):
                    op_type = op.get("operation")
                    table = op.get("table", "")
                    table_lower = table.lower()  # Normalize for consistent lookup
                    
                    if verbose:
                        print(f"\n[{i}/{len(operations)}] {op_type} {table}")
                    
                    try:
                        if op_type == "INSERT":
                            result = self._execute_insert(conn, op, created_ids, verbose)
                            
                            if result.get("success"):
                                new_id = result.get("id")
                                if new_id:
                                    # Store by table for generic lookups
                                    created_by_table[table_lower] = new_id
                                    
                                    # CANONICAL STORAGE: "table:identifier" format
                                    # This is bulletproof - we extract identifier and store simply
                                    if table_lower == "product" and "sku" in op.get("values", {}):
                                        sku = op['values']['sku']
                                        # Normalize: lowercase, strip whitespace
                                        canonical_key = f"product:{sku.lower().strip()}"
                                        created_ids[canonical_key] = new_id
                                        if verbose:
                                            print(f"    📌 Registered: {canonical_key} → {new_id}")
                                    
                                    elif table_lower == "purchase_order" and "reference_num" in op.get("values", {}):
                                        ref = op['values']['reference_num']
                                        canonical_key = f"purchase_order:{ref.lower().strip()}"
                                        created_ids[canonical_key] = new_id
                                        if verbose:
                                            print(f"    📌 Registered: {canonical_key} → {new_id}")
                                    
                                    elif table_lower == "supplier" and "name" in op.get("values", {}):
                                        name = op['values']['name']
                                        canonical_key = f"supplier:{name.lower().strip()}"
                                        created_ids[canonical_key] = new_id
                                        if verbose:
                                            print(f"    📌 Registered: {canonical_key} → {new_id}")
                                
                                results["records_created"].append({
                                    "table": table,
                                    "id": new_id,
                                    "values": result.get("values")  # Use actual inserted values (after placeholder substitution)
                                })
                        
                        elif op_type == "UPDATE":
                            result = self._execute_update(conn, op, created_ids, verbose)
                            
                            if result.get("success"):
                                results["records_updated"].append({
                                    "table": table,
                                    "id": result.get("id"),
                                    "changes": result.get("changes")
                                })
                        
                        else:
                            result = {"success": False, "error": f"Unknown operation: {op_type}"}
                        
                        results["operations_executed"].append({
                            "step": i,
                            "operation": op_type,
                            "table": table,
                            "result": result
                        })
                        
                        if not result.get("success"):
                            results["errors"].append({
                                "step": i,
                                "operation": op_type,
                                "table": table,
                                "error": result.get("error")
                            })
                    
                    except Exception as e:
                        error_msg = str(e)
                        if verbose:
                            print(f"  ✗ Error: {error_msg}")
                        results["errors"].append({
                            "step": i,
                            "operation": op_type,
                            "table": table,
                            "error": error_msg
                        })
                        results["operations_executed"].append({
                            "step": i,
                            "operation": op_type,
                            "table": table,
                            "result": {"success": False, "error": error_msg}
                        })
            
            # Transaction committed if we get here
            if verbose:
                print(f"\n{'─'*70}")
                print("EXECUTION COMPLETE")
                print(f"{'─'*70}")
                print(f"  ✓ Created: {len(results['records_created'])} records")
                print(f"  ✓ Updated: {len(results['records_updated'])} records")
                if results["errors"]:
                    print(f"  ✗ Errors: {len(results['errors'])}")
                print(f"{'─'*70}\n")
        
        except Exception as e:
            results["success"] = False
            results["errors"].append({"step": "transaction", "error": str(e)})
            if verbose:
                print(f"\n✗ Transaction failed, rolled back: {e}")
        
        return results
    
    def _execute_insert(
        self,
        conn,
        op: dict,
        created_ids: dict,
        verbose: bool
    ) -> dict:
        """
        Execute an INSERT operation.
        
        Handles:
        - Placeholder substitution for FKs
        - Column validation
        - Returns new ID
        """
        table = op.get("table", "").lower()  # Normalize to lowercase
        values = op.get("values", {}).copy()
        reason = op.get("reason", "")
        
        # Validate table exists
        if table not in self.table_columns:
            return {"success": False, "error": f"Unknown table: {table}"}
        
        # Substitute placeholders
        values = self._substitute_placeholders(values, created_ids, verbose)
        
        # Filter to valid columns only
        valid_columns = self.table_columns[table]
        filtered_values = {}
        
        for k, v in values.items():
            # Skip if not a valid column
            if k not in valid_columns:
                continue
            # Skip 'id' column - it's auto-increment
            if k == "id":
                continue
            # Skip unresolved placeholders (strings starting with __NEW_)
            if isinstance(v, str) and v.startswith("__NEW_"):
                if verbose:
                    print(f"  ⚠️ Skipping unresolved placeholder: {k}={v}")
                continue
            filtered_values[k] = v
        
        if not filtered_values:
            return {"success": False, "error": "No valid columns to insert"}
        
        if verbose:
            preview = ", ".join(f"{k}={v}" for k, v in list(filtered_values.items())[:4])
            print(f"  INSERT INTO {table}: {preview}...")
            if reason:
                print(f"  Reason: {reason[:60]}")
        
        # Handle composite key tables (no auto-increment id)
        # For supplier_product, the identity is (supplier_id, product_id)
        composite_key_tables = {
            "supplier_product": ["supplier_id", "product_id"]
        }
        
        # Build and execute INSERT
        columns = list(filtered_values.keys())
        placeholders = [f":{col}" for col in columns]
        
        # Use INSERT OR IGNORE for junction tables to handle idempotent operations
        if table in composite_key_tables:
            query = text(f"""
                INSERT OR IGNORE INTO {table} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
            """)
        else:
            query = text(f"""
                INSERT INTO {table} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
            """)
        
        result = conn.execute(query, filtered_values)
        new_id = result.lastrowid
        rows_affected = result.rowcount
        
        if table in composite_key_tables:
            # Build composite key from values
            key_cols = composite_key_tables[table]
            key_parts = [str(filtered_values.get(col, "")) for col in key_cols]
            composite_id = "-".join(key_parts)
            
            if rows_affected == 0:
                # Record already existed, this is fine for junction tables
                if verbose:
                    print(f"  ✓ {table} ({', '.join(key_cols)})=({', '.join(key_parts)}) already exists (skipped)")
                return {"success": True, "id": composite_id, "values": filtered_values, "skipped": True}
            else:
                if verbose:
                    print(f"  ✓ Created {table} ({', '.join(key_cols)})=({', '.join(key_parts)})")
                return {"success": True, "id": composite_id, "values": filtered_values}
        
        if verbose:
            print(f"  ✓ Created {table} id={new_id}")
        
        return {"success": True, "id": new_id, "values": filtered_values}
    
    def _execute_update(
        self,
        conn,
        op: dict,
        created_ids: dict,
        verbose: bool
    ) -> dict:
        """
        Execute an UPDATE operation.
        
        Handles:
        - Placeholder substitution in WHERE clause
        - Change tracking
        """
        table = op.get("table", "").lower()  # Normalize to lowercase
        where = op.get("where", {}).copy()
        set_values = op.get("set", {}).copy()
        reason = op.get("reason", "")
        
        # Validate table exists
        if table not in self.table_columns:
            return {"success": False, "error": f"Unknown table: {table}"}
        
        # Substitute placeholders in WHERE
        where = self._substitute_placeholders(where, created_ids, verbose)
        set_values = self._substitute_placeholders(set_values, created_ids, verbose)
        
        if not where:
            return {"success": False, "error": "UPDATE requires WHERE clause"}
        
        if not set_values:
            return {"success": False, "error": "UPDATE requires SET values"}
        
        if verbose:
            print(f"  UPDATE {table} WHERE {where}")
            print(f"  SET {set_values}")
            if reason:
                print(f"  Reason: {reason[:60]}")
        
        # First, get current values for change tracking
        where_clauses = [f"{k} = :where_{k}" for k in where.keys()]
        where_params = {f"where_{k}": v for k, v in where.items()}
        
        select_query = text(f"""
            SELECT * FROM {table}
            WHERE {' AND '.join(where_clauses)}
        """)
        existing = conn.execute(select_query, where_params).fetchone()
        
        if not existing:
            return {"success": False, "error": f"No record found matching {where}"}
        
        old_values = dict(existing._mapping)
        
        # Handle composite key tables (supplier_product) - build composite record_id
        composite_key_tables = {
            "supplier_product": ["supplier_id", "product_id"]
        }
        
        if table in composite_key_tables:
            key_cols = composite_key_tables[table]
            key_parts = [str(old_values.get(col, "")) for col in key_cols]
            record_id = "-".join(key_parts)
        else:
            record_id = old_values.get("id")
        
        # Track changes
        changes = {}
        valid_columns = self.table_columns[table]
        filtered_set = {}
        
        for col, new_val in set_values.items():
            if col in valid_columns:
                old_val = old_values.get(col)
                # Compare as strings to handle date/number conversions
                if str(new_val) != str(old_val):
                    filtered_set[col] = new_val
                    changes[col] = {"old": old_val, "new": new_val}
        
        if not filtered_set:
            if verbose:
                print(f"  ✓ No changes needed (values already match)")
            return {"success": True, "id": record_id, "changes": {}}
        
        # Build and execute UPDATE
        set_clauses = [f"{col} = :set_{col}" for col in filtered_set.keys()]
        set_params = {f"set_{col}": v for col, v in filtered_set.items()}
        
        update_query = text(f"""
            UPDATE {table}
            SET {', '.join(set_clauses)}
            WHERE {' AND '.join(where_clauses)}
        """)
        
        conn.execute(update_query, {**where_params, **set_params})
        
        if verbose:
            print(f"  ✓ Updated {table} id={record_id}: {list(changes.keys())}")
        
        return {"success": True, "id": record_id, "changes": changes}
    
    def _substitute_placeholders(
        self,
        values: dict,
        created_ids: dict,
        verbose: bool
    ) -> dict:
        """
        Substitute __NEW_<table>_id placeholders with actual IDs.
        
        BULLETPROOF APPROACH:
        1. Extract the table type (product, purchase_order, supplier)
        2. Extract the identifier (SKU, reference number, etc.)
        3. Look up using canonical key: "table:identifier"
        
        This handles ANY placeholder format the LLM might generate:
        - __NEW_product_id_SKU-7
        - __NEW_product_id_for_SKU-7__
        - __NEW_product_sku_SKU-7
        - __NEW_PRODUCT_ID_SKU-7
        All resolve to canonical lookup: "product:sku-7"
        """
        result = {}
        
        for key, value in values.items():
            if isinstance(value, str) and value.upper().startswith("__NEW_"):
                actual_id = self._resolve_placeholder(value, created_ids, verbose)
                result[key] = actual_id
            else:
                result[key] = value
        
        return result
    
    def _resolve_placeholder(self, placeholder: str, created_ids: dict, verbose: bool):
        """
        Resolve a placeholder to an actual ID using canonical lookup.
        
        Extracts table type and identifier from ANY placeholder format,
        then looks up using canonical "table:identifier" key.
        
        BULLETPROOF: Normalizes hyphens/underscores/spaces to match any format.
        """
        # Clean up: strip trailing underscores, lowercase
        clean = placeholder.rstrip('_').lower()
        
        def normalize_identifier(s):
            """Normalize identifier: lowercase, convert underscores to hyphens."""
            return s.lower().strip().replace('_', '-')
        
        def try_lookup(table: str, identifier: str) -> int | None:
            """Try to find identifier in created_ids with various normalizations."""
            # Normalize the identifier
            norm_id = normalize_identifier(identifier)
            
            # Try multiple variations
            variations = [
                f"{table}:{identifier}",           # Original
                f"{table}:{norm_id}",              # Normalized (underscores → hyphens)
                f"{table}:{identifier.replace('-', '_')}",  # Hyphens → underscores
            ]
            
            for key in variations:
                if key in created_ids:
                    return created_ids[key]
            
            # Also try fuzzy match on all keys for this table
            for stored_key, stored_id in created_ids.items():
                if stored_key.startswith(f"{table}:"):
                    stored_identifier = stored_key.split(":", 1)[1]
                    if normalize_identifier(stored_identifier) == norm_id:
                        return stored_id
            
            return None
        
        # Pattern to extract table and identifier from various formats:
        # __new_product_id_SKU-7, __new_product_id_for_SKU-7, __new_product_sku_SKU-7
        # __new_purchase_order_id_TR-45678, __new_purchase_order_id_for_TR-45678
        # __new_supplier_id_for_Big_Supplier
        
        # Try product patterns
        product_patterns = [
            r"__new_product_(?:id|sku)_(?:for_)?(.+)",  # Standard patterns
            r"__new_product_(?:id|sku)_(.+)",           # Without for_
        ]
        for pattern in product_patterns:
            match = re.match(pattern, clean)
            if match:
                identifier = match.group(1).strip()
                actual_id = try_lookup("product", identifier)
                if actual_id is not None:
                    if verbose:
                        print(f"  → Substituting {placeholder} → {actual_id}")
                    return actual_id
        
        # Try purchase_order patterns
        po_patterns = [
            r"__new_purchase_order_(?:id)_(?:for_)?(.+)",
            r"__new_purchase_order_(?:id)_(.+)",
            r"__new_po_(?:id)_(?:for_)?(.+)",  # Short form
        ]
        for pattern in po_patterns:
            match = re.match(pattern, clean)
            if match:
                identifier = match.group(1).strip()
                actual_id = try_lookup("purchase_order", identifier)
                if actual_id is not None:
                    if verbose:
                        print(f"  → Substituting {placeholder} → {actual_id}")
                    return actual_id
        
        # Try supplier patterns
        supplier_patterns = [
            r"__new_supplier_(?:id)_(?:for_)?(.+)",
            r"__new_supplier_(?:id)_(.+)",
        ]
        for pattern in supplier_patterns:
            match = re.match(pattern, clean)
            if match:
                identifier = match.group(1).strip().replace('_', ' ')  # Restore spaces
                actual_id = try_lookup("supplier", identifier)
                if actual_id is not None:
                    if verbose:
                        print(f"  → Substituting {placeholder} → {actual_id}")
                    return actual_id
        
        # If no match found, return original placeholder (will cause FK error)
        if verbose:
            print(f"  ⚠️ Could not resolve placeholder: {placeholder}")
            print(f"      Available keys: {list(created_ids.keys())}")
        return placeholder
