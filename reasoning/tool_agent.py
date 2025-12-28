"""
Tool-Calling Agent for Database Exploration.

This wraps the LLM with function calling capabilities, allowing it to:
- Call database exploration tools
- Think through problems step by step
- Build understanding iteratively

The agent runs a conversation loop until it reaches a conclusion.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from llm_client import LLMClient
from reasoning.db_tools import DatabaseTools


@dataclass
class AgentStep:
    """A single step in the agent's reasoning process."""
    step_number: int
    thinking: Optional[str]
    tool_call: Optional[Dict[str, Any]]
    tool_result: Optional[Dict[str, Any]]
    

@dataclass
class AgentResult:
    """Final result from the agent."""
    success: bool
    result: Dict[str, Any]
    steps: List[AgentStep]
    total_tool_calls: int
    error: Optional[str] = None


class ToolAgent:
    """
    LLM Agent with tool-calling capabilities.
    
    Runs a conversation loop where the LLM can:
    1. Think about the problem
    2. Call tools to gather information
    3. Reason about results
    4. Reach a conclusion
    """
    
    def __init__(
        self,
        db_tools: DatabaseTools,
        api_key: str = None,
        model: str = "gpt-5.2",
        temperature: float = 0.0,
        max_iterations: int = 20,
        verbose: bool = True
    ):
        self.db_tools = db_tools
        self.max_iterations = max_iterations
        self.verbose = verbose
        
        # Use centralized LLMClient instead of raw OpenAI client
        self.llm = LLMClient(api_key=api_key, model=model, temperature=temperature)
        self.tools = DatabaseTools.get_tool_definitions()
    
    def run(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: Dict[str, Any] = None
    ) -> AgentResult:
        """
        Run the agent until it produces a final answer.
        
        Args:
            system_prompt: Instructions for the agent
            user_message: The task/question
            output_schema: Optional JSON schema for final output
            
        Returns:
            AgentResult with the final answer and reasoning trace
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        steps = []
        iteration = 0
        
        if self.verbose:
            print(f"\n{'='*70}")
            print("TOOL AGENT - Starting")
            print(f"{'='*70}")
        
        while iteration < self.max_iterations:
            iteration += 1
            
            if self.verbose:
                print(f"\n{'─'*70}")
                print(f"Iteration {iteration}")
                print(f"{'─'*70}")
            
            # Call LLM using centralized client
            try:
                response = self.llm.call_with_tools_conversation(
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto"
                )
            except Exception as e:
                return AgentResult(
                    success=False,
                    result={},
                    steps=steps,
                    total_tool_calls=len([s for s in steps if s.tool_call]),
                    error=f"LLM call failed: {str(e)}"
                )
            
            choice = response.choices[0]
            message = choice.message
            
            # Check for thinking/content
            if message.content:
                if self.verbose:
                    print(f"\n💭 Thinking:\n{message.content[:500]}...")
            
            # Check if we have tool calls
            if message.tool_calls:
                # Process each tool call
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    if self.verbose:
                        print(f"\n🔧 Tool Call: {tool_name}")
                        print(f"   Args: {json.dumps(tool_args, indent=2)[:200]}")
                    
                    # Execute the tool
                    tool_result = self.db_tools.execute_tool(tool_name, tool_args)
                    
                    if self.verbose:
                        result_preview = json.dumps(tool_result, indent=2)[:300]
                        print(f"   Result: {result_preview}...")
                    
                    # Record step
                    steps.append(AgentStep(
                        step_number=iteration,
                        thinking=message.content,
                        tool_call={"name": tool_name, "arguments": tool_args},
                        tool_result=tool_result
                    ))
                    
                    # Add to messages
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_call.function.arguments
                                }
                            }
                        ]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result)
                    })
            
            else:
                # No tool calls - this should be the final answer
                if self.verbose:
                    print(f"\n✅ Final Answer")
                
                # Record final step
                steps.append(AgentStep(
                    step_number=iteration,
                    thinking=message.content,
                    tool_call=None,
                    tool_result=None
                ))
                
                # Try to parse as JSON
                try:
                    # Extract JSON from the response
                    content = message.content.strip()
                    
                    # Handle markdown code blocks
                    if "```json" in content:
                        start = content.find("```json") + 7
                        end = content.find("```", start)
                        content = content[start:end].strip()
                    elif "```" in content:
                        start = content.find("```") + 3
                        end = content.find("```", start)
                        content = content[start:end].strip()
                    
                    result = json.loads(content)
                    
                    return AgentResult(
                        success=True,
                        result=result,
                        steps=steps,
                        total_tool_calls=len([s for s in steps if s.tool_call])
                    )
                    
                except json.JSONDecodeError:
                    # Not valid JSON - might need to ask for JSON
                    if self.verbose:
                        print("   (Response not valid JSON, requesting structured output)")
                    
                    messages.append({"role": "assistant", "content": message.content})
                    messages.append({
                        "role": "user", 
                        "content": "Please provide your final answer as valid JSON."
                    })
                    continue
            
            # Check for finish reason
            if choice.finish_reason == "stop" and not message.tool_calls:
                break
        
        # Max iterations reached
        return AgentResult(
            success=False,
            result={},
            steps=steps,
            total_tool_calls=len([s for s in steps if s.tool_call]),
            error=f"Max iterations ({self.max_iterations}) reached without conclusion"
        )
    
    def format_trace(self, result: AgentResult) -> str:
        """Format the agent's reasoning trace for display."""
        
        lines = []
        lines.append("=" * 70)
        lines.append("AGENT REASONING TRACE")
        lines.append("=" * 70)
        
        for step in result.steps:
            lines.append(f"\n--- Step {step.step_number} ---")
            
            if step.thinking:
                lines.append(f"Thinking: {step.thinking[:200]}...")
            
            if step.tool_call:
                lines.append(f"Tool: {step.tool_call['name']}")
                lines.append(f"Args: {json.dumps(step.tool_call['arguments'])}")
                if step.tool_result:
                    lines.append(f"Result: {json.dumps(step.tool_result)[:200]}...")
        
        lines.append(f"\n{'='*70}")
        lines.append(f"Total tool calls: {result.total_tool_calls}")
        lines.append(f"Success: {result.success}")
        if result.error:
            lines.append(f"Error: {result.error}")
        lines.append("=" * 70)
        
        return "\n".join(lines)

