"""
Reasoning module for autonomous LLM agents.

Three architectures available:
- MasterReasoningOrchestrator: Single agent with tool calling (legacy)
- PlanningLLM + OperationExecutor: Single-call schema reasoning
- ChainPlanner + OperationExecutor: Multi-step chain (recommended)

The chain approach:
- RichSchemaBuilder: Creates LLM-friendly schema with FK relationships
- ChainPlanner: 4 focused LLM calls (entity resolution, existence, relationships, operations)
- OperationExecutor: Executes standard SQL operations with FK substitution
"""

from .master_orchestrator import MasterReasoningOrchestrator
from .schema_builder import RichSchemaBuilder
from .planner import PlanningLLM
from .chain_planner import ChainPlanner
from .executor import OperationExecutor

__all__ = [
    'MasterReasoningOrchestrator',
    'RichSchemaBuilder',
    'PlanningLLM',
    'ChainPlanner',
    'OperationExecutor'
]

