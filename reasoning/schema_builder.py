"""
Rich Schema Builder - Creates LLM-friendly schema representation.

The key insight: LLMs need to understand RELATIONSHIPS, not just columns.
This module extracts FK constraints, table purposes, and data patterns
so the LLM can reason about what operations are needed.
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy import inspect, text


# Table descriptions - what each table represents and why it exists
# IDENTITY tells the LLM what uniquely identifies a record (for INSERT vs UPDATE decisions)
TABLE_DESCRIPTIONS = {
    "product": {
        "purpose": "Internal product catalog. Each product has a unique internal SKU.",
        "identity": ["id"],  # or by sku (unique)
        "identity_note": "Check by 'sku' column - if SKU exists, UPDATE; if not, INSERT",
        "notes": "Master product record. All other tables reference this via product_id."
    },
    "supplier": {
        "purpose": "Vendors/suppliers that provide products to the company.",
        "identity": ["id"],  # or by email (unique)
        "identity_note": "Check by 'email' column for matching",
        "notes": "Each supplier may use different SKU formats than internal SKUs."
    },
    "supplier_product": {
        "purpose": "Junction table linking suppliers to products. Maps vendor SKUs to internal SKUs.",
        "identity": ["supplier_id", "product_id"],  # composite key
        "identity_note": "Unique by (supplier_id, product_id) - one mapping per supplier-product pair",
        "notes": """CRITICAL RULE: When you INSERT a new product, you MUST ALSO INSERT a supplier_product record 
            if the supplier is known. This links the vendor's SKU to the internal product.
            Without this mapping, future documents from the supplier won't resolve this product.""",
        "is_junction_table": True
    },
    "purchase_order": {
        "purpose": "Purchase order headers - one per order from a supplier.",
        "identity": ["id"],  # or by reference_num + supplier_id
        "identity_note": "Check by 'reference_num' + 'supplier_id'. Note: '12' and 'PO-12' may be the same PO.",
        "notes": "Always check if a PO exists before creating a new one."
    },
    "purchase_order_line": {
        "purpose": "Individual line items on a purchase order.",
        "identity": ["purchase_order_id", "product_id"],  # logical unique key
        "identity_note": "Unique by (purchase_order_id, product_id) - one line per product per PO",
        "notes": "If line exists for this PO+product, UPDATE it. Otherwise INSERT new line."
    }
}


class RichSchemaBuilder:
    """
    Builds a rich schema representation for LLM reasoning.
    
    Unlike a simple schema dump, this includes:
    - Foreign key relationships with direction
    - Table purposes and business context
    - Dependency graph (what must exist before what)
    - Current data samples
    """
    
    def __init__(self, engine):
        self.engine = engine
        self.inspector = inspect(engine)
    
    def build(self) -> Dict[str, Any]:
        """
        Build complete schema context for LLM.
        
        Returns dict with:
        - tables: Table definitions with columns, FKs, descriptions
        - dependency_graph: Which tables depend on which
        - data_snapshot: Current state of relevant tables
        """
        
        tables = {}
        dependency_graph = {}
        
        for table_name in self.inspector.get_table_names():
            table_info = self._build_table_info(table_name)
            tables[table_name] = table_info
            
            # Build dependency list (what this table needs to exist first)
            dependencies = [fk["references_table"] for fk in table_info["foreign_keys"]]
            if dependencies:
                dependency_graph[table_name] = dependencies
        
        return {
            "tables": tables,
            "dependency_graph": dependency_graph,
            "data_snapshot": self._get_data_snapshot(),
            "insertion_order": self._topological_sort(dependency_graph)
        }
    
    def _build_table_info(self, table_name: str) -> Dict[str, Any]:
        """Build detailed info for a single table."""
        
        # Get columns with types and constraints
        columns = []
        pk_columns = set(self.inspector.get_pk_constraint(table_name).get("constrained_columns", []))
        
        for col in self.inspector.get_columns(table_name):
            col_info = {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "is_primary_key": col["name"] in pk_columns
            }
            columns.append(col_info)
        
        # Get foreign keys with full context
        foreign_keys = []
        for fk in self.inspector.get_foreign_keys(table_name):
            fk_info = {
                "column": fk["constrained_columns"][0],
                "references_table": fk["referred_table"],
                "references_column": fk["referred_columns"][0],
                "constraint": f"{table_name}.{fk['constrained_columns'][0]} → {fk['referred_table']}.{fk['referred_columns'][0]}"
            }
            foreign_keys.append(fk_info)
        
        # Get unique constraints
        unique_constraints = []
        for constraint in self.inspector.get_unique_constraints(table_name):
            unique_constraints.append(constraint["column_names"])
        
        # Get business context
        description = TABLE_DESCRIPTIONS.get(table_name, {})
        
        return {
            "columns": columns,
            "primary_key": list(pk_columns),
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "purpose": description.get("purpose", ""),
            "identity": description.get("identity", list(pk_columns)),  # default to PK
            "identity_note": description.get("identity_note", ""),
            "notes": description.get("notes", ""),
            "is_junction_table": description.get("is_junction_table", False),
            "row_count": self._count_rows(table_name)
        }
    
    def _get_data_snapshot(self) -> Dict[str, Any]:
        """Get current data state for LLM context."""
        
        snapshot = {}
        
        with self.engine.connect() as conn:
            # Products - for SKU resolution
            result = conn.execute(text("SELECT id, sku, title FROM product"))
            snapshot["products"] = [dict(r._mapping) for r in result]
            
            # Suppliers
            result = conn.execute(text("SELECT id, name, email FROM supplier"))
            snapshot["suppliers"] = [dict(r._mapping) for r in result]
            
            # Supplier-product mappings - CRITICAL for SKU resolution
            result = conn.execute(text("""
                SELECT sp.supplier_id, sp.product_id, sp.supplier_sku, p.sku as internal_sku
                FROM supplier_product sp
                JOIN product p ON sp.product_id = p.id
            """))
            snapshot["supplier_product_mappings"] = [dict(r._mapping) for r in result]
            
            # Purchase orders
            result = conn.execute(text("""
                SELECT po.id, po.reference_num, po.supplier_id, s.name as supplier_name
                FROM purchase_order po
                JOIN supplier s ON po.supplier_id = s.id
            """))
            snapshot["purchase_orders"] = [dict(r._mapping) for r in result]
            
            # Purchase order lines
            result = conn.execute(text("""
                SELECT pol.id, pol.purchase_order_id, pol.product_id, p.sku,
                       pol.quantity, pol.delivery_date, pol.total_price
                FROM purchase_order_line pol
                JOIN product p ON pol.product_id = p.id
            """))
            snapshot["purchase_order_lines"] = [dict(r._mapping) for r in result]
        
        return snapshot
    
    def _count_rows(self, table_name: str) -> int:
        """Count rows in a table."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar()
        except:
            return 0
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """
        Sort tables by dependency order.
        
        Tables with no dependencies come first.
        This tells the LLM what order to create records in.
        """
        # Get all tables
        all_tables = set(self.inspector.get_table_names())
        
        # Tables with no dependencies
        no_deps = [t for t in all_tables if t not in graph]
        
        # Simple topological sort
        result = []
        visited = set()
        
        def visit(table):
            if table in visited:
                return
            visited.add(table)
            for dep in graph.get(table, []):
                visit(dep)
            result.append(table)
        
        for table in all_tables:
            visit(table)
        
        return result
    
    def format_for_llm(self) -> str:
        """
        Format schema as a clear text prompt for the LLM.
        
        This is the key - present the schema in a way that
        enables reasoning, not just data lookup.
        """
        
        schema = self.build()
        
        lines = []
        lines.append("=" * 70)
        lines.append("DATABASE SCHEMA & CURRENT STATE")
        lines.append("=" * 70)
        
        # Insertion order (dependency hint)
        lines.append("\n## INSERTION ORDER (respects foreign key dependencies)")
        lines.append(f"   {' → '.join(schema['insertion_order'])}")
        lines.append("   (Create records in this order to satisfy FK constraints)")
        
        # Tables
        lines.append("\n## TABLES")
        lines.append("-" * 70)
        
        for table_name, info in schema["tables"].items():
            lines.append(f"\n### {table_name.upper()}")
            
            # Purpose
            if info["purpose"]:
                lines.append(f"    Purpose: {info['purpose']}")
            
            # IDENTITY - critical for INSERT vs UPDATE decision
            if info.get("identity"):
                identity_cols = ", ".join(info["identity"])
                lines.append(f"    IDENTITY: ({identity_cols})")
                if info.get("identity_note"):
                    lines.append(f"    → {info['identity_note']}")
            
            # Notes (business logic)
            if info["notes"]:
                notes = info["notes"].strip().replace("\n", "\n    ")
                lines.append(f"    Notes: {notes}")
            
            # Columns
            lines.append(f"    Columns:")
            for col in info["columns"]:
                pk = " [PK]" if col["is_primary_key"] else ""
                nullable = "" if col["nullable"] else " NOT NULL"
                lines.append(f"      - {col['name']}: {col['type']}{pk}{nullable}")
            
            # Foreign keys
            if info["foreign_keys"]:
                lines.append(f"    Foreign Keys:")
                for fk in info["foreign_keys"]:
                    lines.append(f"      - {fk['constraint']}")
            
            # Unique constraints
            if info["unique_constraints"]:
                for uc in info["unique_constraints"]:
                    lines.append(f"    Unique: ({', '.join(uc)})")
            
            lines.append(f"    Current rows: {info['row_count']}")
        
        # Current data snapshot
        lines.append("\n" + "=" * 70)
        lines.append("CURRENT DATA (for entity resolution)")
        lines.append("=" * 70)
        
        snapshot = schema["data_snapshot"]
        
        # Products
        lines.append("\n### PRODUCTS (for SKU resolution)")
        for p in snapshot["products"]:
            lines.append(f"    id={p['id']}, sku='{p['sku']}', title='{p['title']}'")
        
        # Suppliers
        lines.append("\n### SUPPLIERS")
        for s in snapshot["suppliers"]:
            lines.append(f"    id={s['id']}, name='{s['name']}', email='{s['email']}'")
        
        # Supplier-product mappings (CRITICAL)
        lines.append("\n### SUPPLIER-PRODUCT MAPPINGS (for vendor SKU resolution)")
        lines.append("    (Vendor SKU → Internal SKU/Product ID)")
        for m in snapshot["supplier_product_mappings"]:
            vendor_sku = m['supplier_sku'] or '(uses internal)'
            lines.append(f"    supplier_id={m['supplier_id']}: '{vendor_sku}' → product_id={m['product_id']} (internal: '{m['internal_sku']}')")
        
        # Purchase orders
        lines.append("\n### PURCHASE ORDERS")
        for po in snapshot["purchase_orders"]:
            lines.append(f"    id={po['id']}, reference='{po['reference_num']}', supplier={po['supplier_name']} (id={po['supplier_id']})")
        
        # PO lines
        lines.append("\n### PURCHASE ORDER LINES")
        for pol in snapshot["purchase_order_lines"]:
            lines.append(f"    po_id={pol['purchase_order_id']}, product_id={pol['product_id']} ({pol['sku']}), qty={pol['quantity']}, date={pol['delivery_date']}")
        
        return "\n".join(lines)

