"""
Master Reasoning Orchestrator - Autonomous database agent.

Uses LLM with function calling to discover schema, match entities,
and execute database operations autonomously.
"""

from typing import Dict, Any, List
import json

from llm_client import LLMClient
from tools import UniversalDatabaseTools
from .prompts import MASTER_SYSTEM_PROMPT, build_reasoning_context


class MasterReasoningOrchestrator:
    """
    Autonomous agent that reasons about documents and executes database operations.
    
    Flow:
    1. Receives email + extracted document data
    2. Uses LLM with function calling to:
       - Discover database schema
       - Match entities
       - Plan operations
       - Execute changes
       - Verify results
    3. Returns complete operation log
    """
    
    def __init__(self, engine, api_key: str = None, model: str = "gpt-4o"):
        """
        Initialize orchestrator.
        
        Args:
            engine: SQLAlchemy engine for database
            api_key: OpenAI API key
            model: LLM model to use
        """
        self.llm = LLMClient(api_key=api_key, model=model, temperature=0.0)
        self.db_tools = UniversalDatabaseTools(engine)
        self.tool_definitions = self._build_tool_definitions()
    
    def process(
        self,
        email_body: str,
        extracted_data: dict,
        max_iterations: int = 20,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Process email and document by reasoning through database operations.
        
        Args:
            email_body: Email text content
            extracted_data: Verified extraction from document
            max_iterations: Max reasoning iterations
            verbose: Print full reasoning trail for debugging
            
        Returns:
            {
                "success": bool,
                "operations": [...],
                "tables_affected": [...],
                "summary": str,
                "confidence": float,
                "iterations": int,
                "reasoning_trail": [...]  # Full conversation for debugging
            }
        """
        
        # Build context
        user_message = build_reasoning_context(email_body, extracted_data)
        
        # Initialize conversation
        messages = [
            {"role": "system", "content": MASTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # Track full reasoning trail for debugging
        reasoning_trail = []
        
        if verbose:
            print(f"\n{'='*70}")
            print("MASTER LLM REASONING")
            print(f"{'='*70}")
        
        # Reasoning loop with function calling
        for iteration in range(max_iterations):
            
            # Call LLM with function calling enabled
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=messages,
                tools=self.tool_definitions,
                tool_choice="auto",
                temperature=0.0
            )
            
            message = response.choices[0].message
            
            # Check if done (no more tool calls)
            if not message.tool_calls:
                # LLM has finished reasoning
                if verbose:
                    print(f"\n[Iteration {iteration + 1}] LLM Final Response:")
                    print(message.content[:500] + "..." if len(message.content) > 500 else message.content)
                
                reasoning_trail.append({
                    "iteration": iteration + 1,
                    "type": "final_response",
                    "content": message.content
                })
                
                try:
                    # Try direct JSON parse first
                    result = json.loads(message.content)
                except json.JSONDecodeError:
                    # Extract JSON from markdown if wrapped in ```json blocks
                    content = message.content.strip()
                    
                    # Find JSON block in markdown
                    json_start = content.find('```json')
                    if json_start != -1:
                        json_start = content.find('\n', json_start) + 1
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                    elif '```' in content:
                        # Generic code block
                        json_start = content.find('```')
                        json_start = content.find('\n', json_start) + 1
                        json_end = content.find('```', json_start)
                        content = content[json_start:json_end].strip()
                    else:
                        # Try to find JSON object in text
                        json_start = content.find('{')
                        json_end = content.rfind('}') + 1
                        if json_start != -1 and json_end > json_start:
                            content = content[json_start:json_end]
                    
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        return {
                            "success": False,
                            "error": "LLM did not return valid JSON",
                            "content": message.content,
                            "iterations": iteration + 1,
                            "reasoning_trail": reasoning_trail
                        }
                
                result["iterations"] = iteration + 1
                result["reasoning_trail"] = reasoning_trail
                return result
            
            # Execute tool calls
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls]
            })
            
            if verbose:
                print(f"\n[Iteration {iteration + 1}] LLM Reasoning:")
                if message.content:
                    print(f"  {message.content[:200]}..." if len(message.content) > 200 else f"  {message.content}")
                print(f"  Tool calls: {len(message.tool_calls)}")
            
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                if verbose:
                    print(f"\n  → Calling: {function_name}({json.dumps(arguments, indent=4)})")
                
                # Execute the tool
                result = self._execute_tool(function_name, arguments)
                
                if verbose:
                    result_preview = json.dumps(result, indent=4)[:300]
                    print(f"  ← Result: {result_preview}..." if len(str(result)) > 300 else f"  ← Result: {result_preview}")
                
                # Track in reasoning trail
                reasoning_trail.append({
                    "iteration": iteration + 1,
                    "tool": function_name,
                    "arguments": arguments,
                    "result": result
                })
                
                # Add tool response to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        
        # Max iterations reached
        if verbose:
            print(f"\n⚠ Max iterations ({max_iterations}) reached without completion")
        
        return {
            "success": False,
            "error": "Max iterations reached without completion",
            "iterations": max_iterations,
            "reasoning_trail": reasoning_trail
        }
    
    def _execute_tool(self, function_name: str, arguments: dict) -> Dict[str, Any]:
        """
        Execute a database tool by name.
        
        Args:
            function_name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        try:
            # Map function names to methods
            tool_map = {
                "list_tables": self.db_tools.list_tables,
                "describe_table": self.db_tools.describe_table,
                "search_records": self.db_tools.search_records,
                "get_column_values": self.db_tools.get_column_values,
                "get_record": self.db_tools.get_record,
                "get_related_records": self.db_tools.get_related_records,
                "create_record": self.db_tools.create_record,
                "update_record": self.db_tools.update_record
            }
            
            if function_name not in tool_map:
                return {"error": f"Unknown tool: {function_name}"}
            
            # Execute the tool
            return tool_map[function_name](**arguments)
            
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}
    
    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        """Build OpenAI function calling tool definitions."""
        
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_tables",
                    "description": "List all tables in the database. Use this first to discover what tables exist.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "describe_table",
                    "description": "Get complete table structure: columns, types, relationships, sample data. Essential for understanding how to use a table.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {"type": "string", "description": "Name of table to describe"},
                            "sample_size": {"type": "integer", "description": "Number of sample rows (default 5)"}
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_records",
                    "description": "Search for records with exact match conditions. Use to check if records exist.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Table name"},
                            "conditions": {"type": "object", "description": "Conditions as {column: value}"},
                            "limit": {"type": "integer", "description": "Max results (default 10)"}
                        },
                        "required": ["table", "conditions"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_column_values",
                    "description": "Get sample of distinct values from a column (20-50 samples). Enough to detect patterns without loading entire dataset. Use to see SKU formats for a supplier, naming patterns, etc. Then reason about patterns yourself.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Table name"},
                            "column": {"type": "string", "description": "Column to get values from"},
                            "limit": {"type": "integer", "description": "Max results (default 20, increase to 50 if needed)"},
                            "conditions": {"type": "object", "description": "Optional filter as {column: value}"}
                        },
                        "required": ["table", "column"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_record",
                    "description": "Get a single record by its ID. Use to retrieve or verify specific records.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Table name"},
                            "record_id": {"type": "integer", "description": "Primary key value"}
                        },
                        "required": ["table", "record_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_related_records",
                    "description": "Get records from a related table via foreign key. Example: get all line items for a purchase order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Parent table"},
                            "record_id": {"type": "integer", "description": "Parent record ID"},
                            "related_table": {"type": "string", "description": "Child/related table"}
                        },
                        "required": ["table", "record_id", "related_table"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_record",
                    "description": "Create a new record in a table. Returns the created record with its new ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Table name"},
                            "data": {"type": "object", "description": "Column values as {column: value}"}
                        },
                        "required": ["table", "data"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_record",
                    "description": "Update an existing record. Returns the updated record and what changed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string", "description": "Table name"},
                            "record_id": {"type": "integer", "description": "Record ID to update"},
                            "updates": {"type": "object", "description": "Fields to update as {column: new_value}"}
                        },
                        "required": ["table", "record_id", "updates"]
                    }
                }
            }
        ]

