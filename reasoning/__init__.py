"""
Reasoning module for autonomous LLM agents.

Two architectures available:
- MasterReasoningOrchestrator: Single agent with tool calling (legacy)
- PlanningLLM + OperationExecutor: Generic schema reasoning (recommended)

The generic approach:
- RichSchemaBuilder: Creates LLM-friendly schema with FK relationships, 
  table purposes, and business context
- PlanningLLM: Reasons from schema to determine INSERT/UPDATE operations
- OperationExecutor: Executes standard SQL operations with FK substitution
"""

from .master_orchestrator import MasterReasoningOrchestrator
from .schema_builder import RichSchemaBuilder
from .planner import PlanningLLM
from .executor import OperationExecutor

__all__ = [
    'MasterReasoningOrchestrator',
    'RichSchemaBuilder',
    'PlanningLLM',
    'OperationExecutor'
]

