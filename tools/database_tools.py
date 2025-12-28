"""
Universal Database Tools - Complete toolkit for LLM database interaction.

Provides discovery, search, CRUD operations for ANY database schema.
Clean, focused, no redundancy.
"""

from sqlalchemy import inspect, text, MetaData, Table
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import re


class UniversalDatabaseTools:
    """
    Complete database interaction toolkit.
    
    Design principles:
    - Single responsibility per method
    - No code duplication
    - Clear, predictable return formats
    - Handles errors gracefully
    """
    
    def __init__(self, engine):
        """
        Initialize tools with database engine.
        
        Args:
            engine: SQLAlchemy engine connected to database
        """
        self.engine = engine
        self.inspector = inspect(engine)
        self.metadata = MetaData()
    
    # ==================== DISCOVERY ====================
    
    def list_tables(self) -> Dict[str, Any]:
        """
        List all tables in database.
        
        Returns:
            {"tables": ["table1", ...], "total": N}
        """
        tables = self.inspector.get_table_names()
        return {"tables": tables, "total": len(tables)}
    
    def describe_table(self, table_name: str, sample_size: int = 5) -> Dict[str, Any]:
        """
        Complete table description: structure, relationships, samples.
        
        Args:
            table_name: Table to describe
            sample_size: Number of sample rows
            
        Returns:
            Full table metadata including columns, keys, relationships, samples
        """
        if not self._table_exists(table_name):
            return {"error": f"Table '{table_name}' does not exist"}
        
        return {
            "table": table_name,
            "columns": self._get_columns(table_name),
            "primary_key": self._get_primary_key(table_name),
            "foreign_keys": self._get_foreign_keys(table_name),
            "relationships": self._infer_relationships(table_name),
            "sample_data": self._get_sample_data(table_name, sample_size),
            "total_rows": self._count_rows(table_name)
        }
    
    # ==================== SEARCH / READ ====================
    
    def search_records(
        self,
        table: str,
        conditions: Dict[str, Any],
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search for records matching exact conditions.
        
        Args:
            table: Table name
            conditions: {"column": value, ...}
            limit: Max results
            
        Returns:
            {"found": N, "records": [...]}
        """
        if not self._table_exists(table):
            return {"error": f"Table '{table}' does not exist", "found": 0, "records": []}
        
        try:
            where_clause = " AND ".join([f"{col} = :{col}" for col in conditions.keys()])
            query = f"SELECT * FROM {table} WHERE {where_clause} LIMIT {limit}"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(query), conditions)
                records = [dict(row._mapping) for row in result]
            
            return {"found": len(records), "records": records}
            
        except Exception as e:
            return {"error": str(e), "found": 0, "records": []}
    
    def get_column_values(
        self,
        table: str,
        column: str,
        limit: int = 20,
        conditions: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Get sample of distinct values from a column.
        LLM can detect patterns from 20-50 samples without loading entire dataset.
        
        Args:
            table: Table name
            column: Column to get values from
            limit: Max results (default 20 - enough to detect patterns)
            conditions: Optional filter conditions
            
        Returns:
            {"found": N, "values": [...], "note": "Showing sample..."}
        
        Example:
            get_column_values("supplier_product", "supplier_sku", 
                            conditions={"supplier_id": 2})
            → Returns sample SKUs for supplier 2
            → LLM sees pattern and reasons contextually
        """
        if not self._table_exists(table):
            return {"error": f"Table '{table}' does not exist", "found": 0, "values": []}
        
        try:
            where_clause = ""
            params = {}
            
            if conditions:
                where_parts = [f"{col} = :{col}" for col in conditions.keys()]
                where_clause = f" WHERE {' AND '.join(where_parts)}"
                params = conditions
            
            query = f"SELECT DISTINCT {column} FROM {table}{where_clause} LIMIT {limit}"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                values = [row[0] for row in result if row[0] is not None]
            
            return {"found": len(values), "values": values}
            
        except Exception as e:
            return {"error": str(e), "found": 0, "values": []}
    
    def get_record(self, table: str, record_id: int) -> Dict[str, Any]:
        """
        Get single record by ID.
        
        Args:
            table: Table name
            record_id: Primary key value
            
        Returns:
            {"found": bool, "record": {...}}
        """
        if not self._table_exists(table):
            return {"error": f"Table '{table}' does not exist", "found": False}
        
        try:
            pk_column = self._get_primary_key(table)[0] if self._get_primary_key(table) else "id"
            query = f"SELECT * FROM {table} WHERE {pk_column} = :id"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {"id": record_id})
                row = result.fetchone()
                
                if row:
                    return {"found": True, "record": dict(row._mapping)}
                return {"found": False, "record": None}
                
        except Exception as e:
            return {"error": str(e), "found": False}
    
    def get_related_records(
        self,
        table: str,
        record_id: int,
        related_table: str
    ) -> Dict[str, Any]:
        """
        Get records from related table via foreign key.
        
        Args:
            table: Parent table
            record_id: Parent record ID
            related_table: Child table
            
        Returns:
            {"found": N, "records": [...]}
        """
        # Find FK column in related_table that points to table
        fks = self._get_foreign_keys(related_table)
        fk_column = None
        
        for fk in fks:
            if fk["references_table"] == table:
                fk_column = fk["column"]
                break
        
        if not fk_column:
            return {
                "error": f"No foreign key from {related_table} to {table}",
                "found": 0,
                "records": []
            }
        
        return self.search_records(related_table, {fk_column: record_id}, limit=100)
    
    # ==================== WRITE OPERATIONS ====================
    
    def create_record(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new record.
        
        Args:
            table: Table name
            data: Column values
            
        Returns:
            {
                "success": bool,
                "table": str,
                "operation": "create",
                "record_id": int,
                "record": {...}
            }
        """
        if not self._table_exists(table):
            return {"success": False, "error": f"Table '{table}' does not exist"}
        
        try:
            columns = ", ".join(data.keys())
            placeholders = ", ".join([f":{k}" for k in data.keys()])
            query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            
            with self.engine.begin() as conn:
                result = conn.execute(text(query), data)
                record_id = result.lastrowid
            
            # Read back created record
            created_record = self.get_record(table, record_id)
            
            return {
                "success": True,
                "table": table,
                "operation": "create",
                "record_id": record_id,
                "record": created_record.get("record")
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def update_record(
        self,
        table: str,
        record_id: int,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update existing record.
        
        Args:
            table: Table name
            record_id: Record ID to update
            updates: Columns to update
            
        Returns:
            {
                "success": bool,
                "table": str,
                "record_id": int,
                "operation": "update",
                "changes": {"field": {"old": ..., "new": ...}},
                "record": {...}
            }
        """
        if not self._table_exists(table):
            return {"success": False, "error": f"Table '{table}' does not exist"}
        
        try:
            # Get old values
            old_record = self.get_record(table, record_id)
            if not old_record.get("found"):
                return {"success": False, "error": f"Record {record_id} not found"}
            
            # Build update query
            pk_column = self._get_primary_key(table)[0] if self._get_primary_key(table) else "id"
            set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
            query = f"UPDATE {table} SET {set_clause} WHERE {pk_column} = :record_id"
            
            params = {**updates, "record_id": record_id}
            
            with self.engine.begin() as conn:
                conn.execute(text(query), params)
            
            # Read back updated record
            new_record = self.get_record(table, record_id)
            
            # Build changes dict
            changes = {}
            for field in updates.keys():
                old_val = old_record["record"].get(field)
                new_val = new_record["record"].get(field)
                if old_val != new_val:
                    changes[field] = {"old": old_val, "new": new_val}
            
            return {
                "success": True,
                "table": table,
                "record_id": record_id,
                "operation": "update",
                "changes": changes,
                "record": new_record.get("record")
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==================== HELPER METHODS ====================
    
    def _table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        return table_name in self.inspector.get_table_names()
    
    def _get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column metadata."""
        columns = self.inspector.get_columns(table_name)
        return [
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": col.get("default")
            }
            for col in columns
        ]
    
    def _get_primary_key(self, table_name: str) -> List[str]:
        """Get primary key columns."""
        pk = self.inspector.get_pk_constraint(table_name)
        return pk.get("constrained_columns", [])
    
    def _get_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        """Get foreign key relationships."""
        fks = self.inspector.get_foreign_keys(table_name)
        return [
            {
                "column": fk["constrained_columns"][0],
                "references_table": fk["referred_table"],
                "references_column": fk["referred_columns"][0]
            }
            for fk in fks
        ]
    
    def _infer_relationships(self, table_name: str) -> Dict[str, str]:
        """Infer human-readable relationships."""
        relationships = {}
        
        # Outgoing FKs (this table → others)
        fks = self._get_foreign_keys(table_name)
        for fk in fks:
            relationships[fk["references_table"]] = f"Many-to-One via {fk['column']}"
        
        # Incoming FKs (others → this table)
        for other_table in self.inspector.get_table_names():
            if other_table == table_name:
                continue
            other_fks = self._get_foreign_keys(other_table)
            for fk in other_fks:
                if fk["references_table"] == table_name:
                    relationships[other_table] = f"One-to-Many ({other_table} references this)"
        
        return relationships
    
    def _get_sample_data(self, table_name: str, limit: int) -> List[Dict[str, Any]]:
        """Get sample rows."""
        try:
            query = f"SELECT * FROM {table_name} LIMIT {limit}"
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                return [dict(row._mapping) for row in result]
        except:
            return []
    
    def _count_rows(self, table_name: str) -> int:
        """Count total rows."""
        try:
            query = f"SELECT COUNT(*) as cnt FROM {table_name}"
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                return result.scalar()
        except:
            return 0

