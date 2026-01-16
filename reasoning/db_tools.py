"""
Database Exploration Tools for LLM Entity Resolution.

These tools allow the LLM to inspect and query the database dynamically,
rather than relying on pre-digested snapshots. The LLM can:
- Explore schema structure
- Understand relationships
- Query data to discover patterns
- Search for specific values

This enables true reasoning about the database, not string matching.
"""

import json
from typing import Dict, Any, List, Optional, Union
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


class DatabaseTools:
    """
    Tools for LLM to explore and understand the database.
    
    Each method is a tool the LLM can call via function calling.
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.inspector = inspect(engine)
    
    # =========================================================================
    # TOOL DEFINITIONS (for OpenAI function calling)
    # =========================================================================
    
    @classmethod
    def get_tool_definitions(cls) -> List[Dict]:
        """Return OpenAI-compatible tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "describe_table",
                    "description": "Get the structure of a database table including columns, types, constraints, primary keys, and foreign keys. Use this to understand what data a table holds and how it relates to other tables.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to describe"
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tables",
                    "description": "List all tables in the database. Use this first to understand what tables exist.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_relationships",
                    "description": "Get foreign key relationships for a table - both what it references and what references it. Use this to understand how tables connect.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table"
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_table",
                    "description": "Query a table to see its data. Can filter by column values. Use this to understand data patterns and formats.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to query"
                            },
                            "conditions": {
                                "type": "object",
                                "description": "Optional filter conditions as {column: value} pairs",
                                "additionalProperties": True
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum rows to return (default 10)",
                                "default": 10
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_value",
                    "description": "Search for a value across all text columns in specified tables (or all tables). Use this to find where an identifier like 'SKU-13' or 'PO-12' appears in the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {
                                "type": "string",
                                "description": "The value to search for"
                            },
                            "tables": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of tables to search (searches all if not specified)"
                            },
                            "exact_match": {
                                "type": "boolean",
                                "description": "If true, exact match only. If false, partial match (LIKE %value%)",
                                "default": True
                            }
                        },
                        "required": ["value"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_sample_data",
                    "description": "Get sample rows from a table to understand data patterns and formats. Use this to see what actual data looks like.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table"
                            },
                            "num_rows": {
                                "type": "integer",
                                "description": "Number of sample rows (default 5)",
                                "default": 5
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            }
        ]
    
    # =========================================================================
    # TOOL IMPLEMENTATIONS
    # =========================================================================
    
    def list_tables(self) -> Dict[str, Any]:
        """List all tables in the database."""
        tables = self.inspector.get_table_names()
        
        # Get row counts for each table
        table_info = []
        with self.engine.connect() as conn:
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    table_info.append({"name": table, "row_count": count})
                except:
                    table_info.append({"name": table, "row_count": "unknown"})
        
        return {
            "tables": table_info,
            "total_tables": len(tables)
        }
    
    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Get detailed table structure."""
        
        if table_name not in self.inspector.get_table_names():
            return {"error": f"Table '{table_name}' not found"}
        
        # Get columns
        columns = []
        for col in self.inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": str(col.get("default")) if col.get("default") else None
            })
        
        # Get primary key
        pk = self.inspector.get_pk_constraint(table_name)
        primary_key = pk.get("constrained_columns", [])
        
        # Get foreign keys
        foreign_keys = []
        for fk in self.inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                "column": fk["constrained_columns"][0] if fk["constrained_columns"] else None,
                "references_table": fk["referred_table"],
                "references_column": fk["referred_columns"][0] if fk["referred_columns"] else None
            })
        
        # Get unique constraints
        unique_constraints = []
        for uc in self.inspector.get_unique_constraints(table_name):
            unique_constraints.append(uc["column_names"])
        
        # Get indexes
        indexes = []
        for idx in self.inspector.get_indexes(table_name):
            indexes.append({
                "name": idx["name"],
                "columns": idx["column_names"],
                "unique": idx["unique"]
            })
        
        return {
            "table_name": table_name,
            "columns": columns,
            "primary_key": primary_key,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "indexes": indexes
        }
    
    def get_relationships(self, table_name: str) -> Dict[str, Any]:
        """Get all relationships for a table."""
        
        if table_name not in self.inspector.get_table_names():
            return {"error": f"Table '{table_name}' not found"}
        
        # Outgoing FKs (what this table references)
        references = []
        for fk in self.inspector.get_foreign_keys(table_name):
            references.append({
                "from_column": fk["constrained_columns"][0],
                "to_table": fk["referred_table"],
                "to_column": fk["referred_columns"][0],
                "relationship": f"{table_name}.{fk['constrained_columns'][0]} → {fk['referred_table']}.{fk['referred_columns'][0]}"
            })
        
        # Incoming FKs (what references this table)
        referenced_by = []
        for other_table in self.inspector.get_table_names():
            if other_table == table_name:
                continue
            for fk in self.inspector.get_foreign_keys(other_table):
                if fk["referred_table"] == table_name:
                    referenced_by.append({
                        "from_table": other_table,
                        "from_column": fk["constrained_columns"][0],
                        "to_column": fk["referred_columns"][0],
                        "relationship": f"{other_table}.{fk['constrained_columns'][0]} → {table_name}.{fk['referred_columns'][0]}"
                    })
        
        return {
            "table_name": table_name,
            "references": references,
            "referenced_by": referenced_by,
            "is_junction_table": len(references) >= 2 and len(referenced_by) == 0
        }
    
    def query_table(
        self, 
        table_name: str, 
        conditions: Dict[str, Any] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Query a table with optional conditions."""
        
        if table_name not in self.inspector.get_table_names():
            return {"error": f"Table '{table_name}' not found"}
        
        try:
            with self.engine.connect() as conn:
                # Build query
                query = f"SELECT * FROM {table_name}"
                params = {}
                
                if conditions:
                    where_clauses = []
                    for i, (col, val) in enumerate(conditions.items()):
                        param_name = f"p{i}"
                        where_clauses.append(f"{col} = :{param_name}")
                        params[param_name] = val
                    query += " WHERE " + " AND ".join(where_clauses)
                
                query += f" LIMIT {limit}"
                
                result = conn.execute(text(query), params)
                rows = [dict(r._mapping) for r in result]
                
                return {
                    "table": table_name,
                    "conditions": conditions,
                    "rows": rows,
                    "row_count": len(rows)
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def search_value(
        self, 
        value: str, 
        tables: List[str] = None,
        exact_match: bool = True
    ) -> Dict[str, Any]:
        """Search for a value across tables."""
        
        if tables is None:
            tables = self.inspector.get_table_names()
        
        results = []
        
        with self.engine.connect() as conn:
            for table_name in tables:
                if table_name not in self.inspector.get_table_names():
                    continue
                
                # Get text-like columns
                columns = self.inspector.get_columns(table_name)
                text_columns = [
                    col["name"] for col in columns
                    if "VARCHAR" in str(col["type"]).upper() 
                    or "TEXT" in str(col["type"]).upper()
                    or "CHAR" in str(col["type"]).upper()
                ]
                
                for col_name in text_columns:
                    try:
                        if exact_match:
                            query = text(f"SELECT * FROM {table_name} WHERE {col_name} = :val")
                        else:
                            query = text(f"SELECT * FROM {table_name} WHERE {col_name} LIKE :val")
                            value_param = f"%{value}%"
                        
                        result = conn.execute(
                            query, 
                            {"val": value if exact_match else value_param}
                        )
                        rows = [dict(r._mapping) for r in result]
                        
                        if rows:
                            results.append({
                                "table": table_name,
                                "column": col_name,
                                "matches": rows,
                                "match_count": len(rows)
                            })
                    except Exception as e:
                        continue
        
        return {
            "search_value": value,
            "exact_match": exact_match,
            "results": results,
            "total_matches": sum(r["match_count"] for r in results)
        }
    
    def get_sample_data(self, table_name: str, num_rows: int = 5) -> Dict[str, Any]:
        """Get sample rows from a table."""
        
        if table_name not in self.inspector.get_table_names():
            return {"error": f"Table '{table_name}' not found"}
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {num_rows}"))
                rows = [dict(r._mapping) for r in result]
                
                # Also get column info
                columns = [col["name"] for col in self.inspector.get_columns(table_name)]
                
                return {
                    "table": table_name,
                    "columns": columns,
                    "sample_rows": rows,
                    "row_count": len(rows)
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    # =========================================================================
    # TOOL EXECUTOR
    # =========================================================================
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given arguments."""
        
        tool_map = {
            "list_tables": self.list_tables,
            "describe_table": self.describe_table,
            "get_relationships": self.get_relationships,
            "query_table": self.query_table,
            "search_value": self.search_value,
            "get_sample_data": self.get_sample_data,
        }
        
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            return tool_map[tool_name](**arguments)
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}


