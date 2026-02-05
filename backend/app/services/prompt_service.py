"""
Prompt Service - Template management and prompt engineering infrastructure.

Handles:
- Prompt templates with variable substitution
- Few-shot example management
- Prompt versioning and A/B testing
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import hashlib


# ============================================================================
# Prompt Templates
# ============================================================================

PROMPT_TEMPLATES = {
    # System prompts
    "system_default": """You are Aion, an AI assistant for personal life management.

Current date and time: {current_datetime}

{memory_context}

{persona_rules}

Be helpful, concise, and proactive. Remember user preferences and past conversations.""",

    "system_voice": """You are Aion, speaking in voice mode.

Current time: {current_time}

Guidelines:
- Be conversational and natural
- Keep responses brief (1-3 sentences typically)
- No markdown, bullet points, or formatting
- Use contractions and casual language
- Be warm but professional

{memory_context}""",

    # Intent parsing
    "intent_parser": """Analyze the user's message and extract any actionable intent.

Current time: {current_datetime}

User message: "{user_message}"

Available actions:
1. create_block - Create a note, task, event, or project
2. search - Search user's blocks/notes
3. schedule_event - Add to calendar
4. open_app - Open a system application
5. web_search - Search the internet
6. browser_task - Automated web task
7. focus_mode - Prepare workspace for a task
8. none - Just conversation, no action needed

Return JSON:
{{
    "action": "action_name or none",
    "confidence": 0.0-1.0,
    "parameters": {{}},
    "reasoning": "brief explanation"
}}

Only return the JSON, nothing else.""",

    # RAG query expansion
    "query_expansion": """Generate 3 alternative phrasings of this search query to improve retrieval.

Original query: "{query}"

Return JSON array of alternative queries:
["query1", "query2", "query3"]

Make queries diverse - use synonyms, rephrase, and consider different angles.
Only return the JSON array.""",

    # Fact extraction
    "fact_extraction": """Extract memorable facts from this user message.

Message: "{message}"

Categories:
- preference: Likes, dislikes, preferred ways
- fact: Personal facts (name, job, etc.)
- relationship: People and their relations
- schedule: Regular schedules, routines
- goal: Goals, aspirations
- habit: Regular behaviors

Return JSON array:
[{{"category": "...", "content": "...", "confidence": 0.0-1.0}}]

Only extract explicit facts. Return empty array if none.
Only return the JSON array.""",

    # Conversation summary
    "summarize_conversation": """Summarize this conversation, preserving key facts and decisions.

Conversation:
{conversation}

Write a concise summary (2-4 sentences) that captures:
- Main topics discussed
- Key decisions or conclusions
- Important facts mentioned
- Any action items

Summary:""",

    # Response with sources
    "response_with_sources": """Answer the user's question using the provided context.

Context from user's notes:
{context}

User question: "{question}"

{memory_context}

Instructions:
1. Answer based primarily on the provided context
2. If context is insufficient, say so
3. Be concise but complete
4. Cite sources by mentioning note names when relevant

Response:""",

    # Proactive suggestion
    "proactive_suggestion": """Based on the current context, generate a helpful proactive suggestion.

Current time: {current_datetime}
Recent activity: {recent_activity}
User's upcoming events: {upcoming_events}
User's active goals: {goals}

{memory_context}

Generate ONE brief, actionable suggestion that would be helpful right now.
Be specific and contextual. If nothing relevant, respond with "none".

Suggestion:""",

    # Agent reasoning
    "agent_reasoning": """You are an AI agent that can use tools to help the user.

Current time: {current_datetime}

Available tools:
{tools_description}

User request: "{user_request}"

Think step by step:
1. What is the user trying to accomplish?
2. Which tool(s) would help?
3. What parameters are needed?

Respond with your reasoning and tool call:

Thought: [your reasoning]
Action: [tool_name]
Action Input: [JSON parameters]

Or if no tool needed:
Thought: [your reasoning]
Final Answer: [your response to user]""",

    # Confidence assessment
    "confidence_assessment": """Rate your confidence in this response.

User question: "{question}"
Your response: "{response}"
Sources used: {sources}

Rate confidence 0.0-1.0 based on:
- How well sources support the answer
- Whether information is current/relevant
- Completeness of the answer

Return JSON:
{{"confidence": 0.0-1.0, "reasoning": "brief explanation"}}

Only return the JSON.""",
}


class PromptService:
    """Service for managing and rendering prompt templates."""
    
    def __init__(self):
        self.templates = PROMPT_TEMPLATES.copy()
        self.usage_stats: Dict[str, int] = {}
    
    def get_template(self, name: str) -> Optional[str]:
        """Get a prompt template by name."""
        return self.templates.get(name)
    
    def render(
        self,
        template_name: str,
        **kwargs,
    ) -> str:
        """Render a template with variables."""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        
        # Add default variables
        now = datetime.now(timezone.utc)
        defaults = {
            "current_datetime": now.strftime("%A, %B %d, %Y at %I:%M %p"),
            "current_time": now.strftime("%I:%M %p"),
            "current_date": now.strftime("%B %d, %Y"),
            "memory_context": "",
            "persona_rules": "",
        }
        
        # Merge with provided kwargs
        variables = {**defaults, **kwargs}
        
        # Render template
        try:
            rendered = template.format(**variables)
        except KeyError as e:
            # Handle missing variables gracefully
            rendered = template
            for key, value in variables.items():
                rendered = rendered.replace(f"{{{key}}}", str(value))
        
        # Track usage
        self.usage_stats[template_name] = self.usage_stats.get(template_name, 0) + 1
        
        return rendered
    
    def add_template(self, name: str, template: str):
        """Add or update a template."""
        self.templates[name] = template
    
    def list_templates(self) -> List[str]:
        """List all available template names."""
        return list(self.templates.keys())
    
    def get_usage_stats(self) -> Dict[str, int]:
        """Get template usage statistics."""
        return self.usage_stats.copy()


# Singleton instance
_prompt_service: Optional[PromptService] = None


def get_prompt_service() -> PromptService:
    """Get the prompt service singleton."""
    global _prompt_service
    if _prompt_service is None:
        _prompt_service = PromptService()
    return _prompt_service
