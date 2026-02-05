"""
Intent Service - Extracts structured actions from natural language input.

This service uses the LLM to understand user intent and map it to 
specific system actions like creating blocks, scheduling events, 
or setting reminders.
"""

import json
import logging
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.services.ai_service import get_ai_service

logger = logging.getLogger(__name__)

class IntentAction(BaseModel):
    """Represents a single action extracted from user intent."""
    action_type: str = Field(..., description="Type of action: create_block, schedule_event, search, set_reminder")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Explanation for this action")

class IntentResult(BaseModel):
    """Result of intent parsing containing multiple possible actions."""
    actions: list[IntentAction]
    primary_intent: str
    summary: str

class IntentService:
    """Service to convert natural language to structured system actions."""
    
    def __init__(self):
        self.ai = get_ai_service()
    
    async def parse_intent(self, message: str, context: Optional[str] = None) -> IntentResult:
        """
        Parse user message into structured actions using the LLM.
        """
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_prompt = f"""You are the Intent Parser for Aion, a personal OS.
Current System Time: {current_time}
Your job is to translate user natural language into structured system actions.

Available Actions:
1. create_block: For creating notes, lists, or entities.
   Params: name (str), description (str), parent_id (str, optional), block_type (str: 'note', 'task', 'event', 'project')
2. schedule_event: For calendar-related items.
   Params: title (str), start_time (ISO string), end_time (ISO string), description (str)
3. search: For finding information.
   Params: query (str), filter_type (str, optional)
4. open_app: For system control.
   Params: app_name (str)
5. web_search: For researching information online when local data is insufficient.
   Params: query (str), reason (str)
6. browser_task: For autonomous web automation (finding info, signing up, navigating).
   Params: task (str: "Log into site X and...", "Find the latest news on Y")
7. focus_mode: For preparing a specific work session by opening relevant tabs.
   Params: topic (str), urls (list of str, optional)

User Input Example: "Who is the current CEO of Google?"
Output JSON:
{
  "actions": [
    {
      "action_type": "web_search",
      "parameters": {
        "query": "current CEO of Google",
        "reason": "User is asking for factual information that might have changed."
      },
      "confidence": 0.98,
      "reasoning": "This is a factual question that requires up-to-date information from the internet."
    }
  ],
  "primary_intent": "research",
  "summary": "Searching for the current CEO of Google."
}

Respond ONLY with raw JSON. If no action is clear, return an empty actions list.
"""
        
        full_prompt = f"User Message: {message}"
        if context:
            full_prompt = f"Context: {context}\n\n{full_prompt}"
            
        try:
            response_text = await self.ai.chat(
                message=full_prompt,
                system_prompt=system_prompt,
                temperature=0.1, # Low temperature for consistent JSON
            )
            
            # Clean response (sometimes models add extra text)
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start == -1 or end == 0:
                 return IntentResult(actions=[], primary_intent="chat", summary="No specific action detected.")
            
            clean_json = response_text[start:end]
            data = json.loads(clean_json)
            
            return IntentResult(**data)
            
        except Exception as e:
            logger.error(f"Intent parsing failed: {e}")
            return IntentResult(actions=[], primary_intent="error", summary=f"Error parsing intent: {str(e)}")

# Singleton
_intent_service: Optional[IntentService] = None

def get_intent_service() -> IntentService:
    global _intent_service
    if _intent_service is None:
        _intent_service = IntentService()
    return _intent_service
