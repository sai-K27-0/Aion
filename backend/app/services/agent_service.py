"""
Agent Service - ReAct-style agent with tool calling.

Implements a reasoning loop that can:
- Think about the problem
- Call tools to gather information or take actions
- Observe results
- Decide next steps
"""

import json
import re
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from app.services.ai_service import get_ai_service
from app.services.prompt_service import get_prompt_service
from app.services.rag_service import get_rag_service


class ToolType(str, Enum):
    """Available tool types."""
    SEARCH = "search"
    CREATE_BLOCK = "create_block"
    UPDATE_BLOCK = "update_block"
    WEB_SEARCH = "web_search"
    CALCULATOR = "calculator"
    GET_TIME = "get_time"
    GET_WEATHER = "get_weather"
    SEND_NOTIFICATION = "send_notification"


@dataclass
class Tool:
    """Definition of a tool the agent can use."""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable[..., Awaitable[str]]


@dataclass
class AgentStep:
    """A single step in the agent's reasoning."""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


@dataclass
class AgentResult:
    """Result of agent execution."""
    answer: str
    steps: List[AgentStep]
    tools_used: List[str]
    success: bool
    error: Optional[str] = None


class AgentService:
    """
    ReAct-style agent that reasons and uses tools.
    
    The agent follows a loop:
    1. Think about what to do
    2. Decide on an action (tool call) or final answer
    3. If action: execute and observe result
    4. Repeat until final answer or max steps
    """
    
    MAX_STEPS = 10
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self.prompt_service = get_prompt_service()
        self.rag_service = get_rag_service()
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register the default set of tools."""
        
        # Search tool
        self.register_tool(Tool(
            name="search",
            description="Search the user's notes and blocks for information. Use for questions about their data.",
            parameters={
                "query": "The search query",
            },
            function=self._tool_search,
        ))
        
        # Web search tool
        self.register_tool(Tool(
            name="web_search",
            description="Search the internet for current information. Use for questions about the world.",
            parameters={
                "query": "The search query",
            },
            function=self._tool_web_search,
        ))
        
        # Calculator tool
        self.register_tool(Tool(
            name="calculator",
            description="Perform mathematical calculations. Use for any math operations.",
            parameters={
                "expression": "The mathematical expression to evaluate",
            },
            function=self._tool_calculator,
        ))
        
        # Get current time
        self.register_tool(Tool(
            name="get_time",
            description="Get the current date and time.",
            parameters={},
            function=self._tool_get_time,
        ))
        
        # Create block/note
        self.register_tool(Tool(
            name="create_note",
            description="Create a new note or block for the user.",
            parameters={
                "title": "Title of the note",
                "content": "Content of the note",
                "type": "Type: note, task, or event (default: note)",
            },
            function=self._tool_create_note,
        ))
    
    def register_tool(self, tool: Tool):
        """Register a tool for the agent to use."""
        self.tools[tool.name] = tool
    
    async def run(
        self,
        user_request: str,
        context: Optional[str] = None,
    ) -> AgentResult:
        """
        Run the agent on a user request.
        
        Args:
            user_request: What the user wants
            context: Optional additional context
            
        Returns:
            AgentResult with answer and execution trace
        """
        steps: List[AgentStep] = []
        tools_used: List[str] = []
        
        # Build tools description
        tools_desc = self._build_tools_description()
        
        # Build initial prompt
        system_prompt = self.prompt_service.render(
            "agent_reasoning",
            tools_description=tools_desc,
            user_request=user_request,
        )
        
        # Scratchpad for conversation history
        scratchpad = ""
        
        for step_num in range(self.MAX_STEPS):
            # Generate next step
            full_prompt = f"{system_prompt}\n\n{scratchpad}" if scratchpad else system_prompt
            
            response = await self.ai_service.chat(
                message=full_prompt if not scratchpad else f"Continue reasoning:\n{scratchpad}",
                system_prompt=system_prompt if scratchpad else None,
                temperature=0.3,
            )
            
            # Parse response
            step = self._parse_agent_response(response)
            steps.append(step)
            
            if step.is_final:
                return AgentResult(
                    answer=step.final_answer or "I couldn't complete the request.",
                    steps=steps,
                    tools_used=tools_used,
                    success=True,
                )
            
            if step.action and step.action in self.tools:
                # Execute tool
                tool = self.tools[step.action]
                tools_used.append(step.action)
                
                try:
                    observation = await tool.function(**(step.action_input or {}))
                    step.observation = observation
                except Exception as e:
                    step.observation = f"Error: {str(e)}"
                
                # Add to scratchpad
                scratchpad += f"\nThought: {step.thought}"
                scratchpad += f"\nAction: {step.action}"
                scratchpad += f"\nAction Input: {json.dumps(step.action_input)}"
                scratchpad += f"\nObservation: {step.observation}\n"
            
            elif step.action:
                # Unknown tool
                step.observation = f"Unknown tool: {step.action}. Available: {', '.join(self.tools.keys())}"
                scratchpad += f"\nThought: {step.thought}"
                scratchpad += f"\nAction: {step.action}"
                scratchpad += f"\nObservation: {step.observation}\n"
        
        # Max steps reached
        return AgentResult(
            answer="I couldn't complete the request within the allowed steps.",
            steps=steps,
            tools_used=tools_used,
            success=False,
            error="Max steps reached",
        )
    
    def _build_tools_description(self) -> str:
        """Build a description of available tools."""
        lines = []
        for name, tool in self.tools.items():
            params = ", ".join([f"{k}: {v}" for k, v in tool.parameters.items()])
            lines.append(f"- {name}({params}): {tool.description}")
        return "\n".join(lines)
    
    def _parse_agent_response(self, response: str) -> AgentStep:
        """Parse the agent's response into a structured step."""
        thought = ""
        action = None
        action_input = None
        final_answer = None
        
        # Extract thought
        thought_match = re.search(r"Thought:\s*(.+?)(?=\n(?:Action|Final Answer)|$)", response, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
        
        # Check for final answer
        final_match = re.search(r"Final Answer:\s*(.+?)$", response, re.DOTALL)
        if final_match:
            return AgentStep(
                thought=thought,
                is_final=True,
                final_answer=final_match.group(1).strip(),
            )
        
        # Extract action
        action_match = re.search(r"Action:\s*(\w+)", response)
        if action_match:
            action = action_match.group(1).strip()
        
        # Extract action input
        input_match = re.search(r"Action Input:\s*(.+?)(?=\n(?:Thought|Action|Observation)|$)", response, re.DOTALL)
        if input_match:
            input_str = input_match.group(1).strip()
            try:
                action_input = json.loads(input_str)
            except json.JSONDecodeError:
                # Try to parse as simple key=value
                action_input = {"input": input_str}
        
        return AgentStep(
            thought=thought,
            action=action,
            action_input=action_input,
        )
    
    # ========================================================================
    # Tool Implementations
    # ========================================================================
    
    async def _tool_search(self, query: str) -> str:
        """Search user's notes."""
        result = await self.rag_service.query(query, max_sources=3)
        if result.sources:
            sources_text = "\n".join([
                f"- {s.title}: {s.content[:200]}..."
                for s in result.sources
            ])
            return f"Found {len(result.sources)} relevant notes:\n{sources_text}"
        return "No relevant notes found."
    
    async def _tool_web_search(self, query: str) -> str:
        """Search the web."""
        from app.services.search_service import get_search_service
        
        try:
            search_service = get_search_service()
            results = await search_service.search(query, num_results=3)
            
            if results:
                results_text = "\n".join([
                    f"- {r.get('title', 'No title')}: {r.get('body', '')[:200]}..."
                    for r in results
                ])
                return f"Web search results:\n{results_text}"
            return "No web results found."
        except Exception as e:
            return f"Web search failed: {e}"
    
    async def _tool_calculator(self, expression: str) -> str:
        """Evaluate a math expression."""
        try:
            # Safe eval for math only
            allowed = set("0123456789+-*/().% ")
            if not all(c in allowed for c in expression):
                return "Invalid expression. Only numbers and basic operators allowed."
            
            result = eval(expression)
            return f"Result: {result}"
        except Exception as e:
            return f"Calculation error: {e}"
    
    async def _tool_get_time(self) -> str:
        """Get current time."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return f"Current time: {now.strftime('%A, %B %d, %Y at %I:%M %p UTC')}"
    
    async def _tool_create_note(
        self,
        title: str,
        content: str,
        type: str = "note",
    ) -> str:
        """Create a note (placeholder - would integrate with block service)."""
        # In real implementation, this would call the block service
        return f"Created {type}: '{title}' with content: {content[:100]}..."


# Singleton
_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """Get the agent service singleton."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
