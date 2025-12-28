"""
Reasoning module for autonomous LLM agents.

Architectures available:
- MasterReasoningOrchestrator: Single agent with tool calling (legacy)
- PlanningLLM + OperationExecutor: Single-call schema reasoning
- ChainPlanner + OperationExecutor: Multi-step chain with tool-based entity resolution (recommended)

The chain approach:
- RichSchemaBuilder: Creates LLM-friendly schema with FK relationships
- DatabaseTools: Tools for LLM to explore database structure and data
- ToolAgent: Wrapper for tool-calling with thinking/reasoning
- ChainPlanner: 4 focused steps (tool-based entity resolution, existence, relationships, operations)
- OperationExecutor: Executes standard SQL operations with FK substitution
"""

from .master_orchestrator import MasterReasoningOrchestrator
from .schema_builder import RichSchemaBuilder
from .planner import PlanningLLM
from .chain_planner import ChainPlanner
from .executor import OperationExecutor
from .db_tools import DatabaseTools
from .tool_agent import ToolAgent

__all__ = [
    'MasterReasoningOrchestrator',
    'RichSchemaBuilder',
    'PlanningLLM',
    'ChainPlanner',
    'OperationExecutor',
    'DatabaseTools',
    'ToolAgent'
]

