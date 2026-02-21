"""
AI API Endpoints - Comprehensive AI system.

This module provides REST endpoints for:
- AI chat interactions with memory and personality
- Model management (list, switch Ollama models)
- Action execution (control the app via AI)
- Study assistance
- Semantic search
- Screen understanding
- Real-time WebSocket communication
"""

import json
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.websockets import WebSocketState

# Rate limiter (shared with main app)
limiter = Limiter(key_func=get_remote_address)

# File upload limits
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 10MB

async def validate_file_size(file: UploadFile, max_size: int = MAX_FILE_SIZE_BYTES) -> bytes:
    """Read file and validate size limit."""
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
        )
    return contents

from app.services.ai_service import get_ai_service, AIService
from app.services.intent_service import get_intent_service
from app.services.action_executor import get_action_executor, ACTION_REGISTRY
from app.services.study_service import get_study_service
from app.services.user_profile_service import get_profile_service
from app.services.smart_model_router import get_smart_router, TaskType
from app.api.deps import (
    VoiceServiceDep, 
    ActionServiceDep, 
    get_planning_service, 
    PlanningService,
    get_vector_service,
    RealtimeVoiceServiceDep,
    STTServiceDep,
    CurrentUser,
)
from app.schemas.ai import PlanCreate, PlanExecute, Plan

router = APIRouter()

# Global model state (in production, use Redis or DB)
_current_model = None


# ============================================================================
# Request/Response Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Request for AI chat."""
    message: str = Field(..., min_length=1, max_length=10000)
    system_prompt: Optional[str] = Field(None, max_length=5000)
    context: Optional[list[dict]] = Field(None, description="Previous messages")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    model: Optional[str] = Field(None, description="Override Ollama model for this request")
    web_search: bool = Field(False, description="Enable web search for additional context")


class ChatResponse(BaseModel):
    """Response from AI chat."""
    response: str
    model: str


class SearchRequest(BaseModel):
    """Request for semantic search."""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(10, ge=1, le=100)
    block_id: Optional[str] = None
    content_types: Optional[list[str]] = None
    score_threshold: float = Field(0.5, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """Single search result."""
    score: float
    block_id: str
    content_id: Optional[str]
    content_type: str
    title: Optional[str]
    text: Optional[str]


class SearchResponse(BaseModel):
    """Response from semantic search."""
    results: list[SearchResult]
    query: str
    total: int


class ScreenAnalysisResponse(BaseModel):
    """Response from screen analysis."""
    description: str
    extracted_text: Optional[str]
    suggestions: list[dict]


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@router.get(
    "/status",
    summary="AI Service Status",
    description="Check the status of AI services (Ollama, Qdrant).",
)
async def get_ai_status():
    """Check if AI services are available."""
    ai_service = get_ai_service()
    vector_service = get_vector_service()
    
    ollama_available = await ai_service.is_available()
    qdrant_available = await vector_service.is_available()
    
    models = []
    if ollama_available:
        models = await ai_service.list_models()
    
    return {
        "ollama": {
            "available": ollama_available,
            "models": models,
            "chat_model": ai_service.model,
            "embedding_model": ai_service.embedding_model,
        },
        "qdrant": {
            "available": qdrant_available,
            "collection": vector_service.COLLECTION_NAME,
        },
    }


# ============================================================================
# Model Management Endpoints
# ============================================================================

class ModelInfo(BaseModel):
    """Information about an Ollama model."""
    name: str
    size: Optional[str] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None


class ModelsResponse(BaseModel):
    """Response with list of models."""
    models: List[ModelInfo]
    current_model: str


class SwitchModelRequest(BaseModel):
    """Request to switch models."""
    model_name: str


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="List Ollama Models",
    description="List all available Ollama models.",
)
async def list_models():
    """Get all models installed in Ollama."""
    ai_service = get_ai_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    try:
        client = await ai_service._get_client()
        response = await client.get("/api/tags")
        
        if response.status_code == 200:
            data = response.json()
            models = []
            for m in data.get("models", []):
                models.append(ModelInfo(
                    name=m.get("name", ""),
                    size=_format_size(m.get("size", 0)),
                    modified_at=m.get("modified_at", ""),
                    digest=m.get("digest", "")[:12] if m.get("digest") else None,
                ))
            
            return ModelsResponse(
                models=models,
                current_model=ai_service.model,
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to get models")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _format_size(size_bytes: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@router.post(
    "/models/switch",
    summary="Switch Ollama Model",
    description="Switch to a different Ollama model for chat.",
)
async def switch_model(request: SwitchModelRequest):
    """
    Switch the active chat model.
    
    The model must already be installed in Ollama.
    """
    ai_service = get_ai_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    # Verify model exists
    available = await ai_service.list_models()
    
    # Check both exact match and base name match (e.g., "llama3.2" matches "llama3.2:latest")
    model_exists = False
    for m in available:
        if m == request.model_name or m.startswith(request.model_name + ":"):
            model_exists = True
            break
    
    if not model_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{request.model_name}' not found. Available: {', '.join(available)}",
        )
    
    # Switch model
    old_model = ai_service.model
    ai_service.model = request.model_name
    
    return {
        "success": True,
        "previous_model": old_model,
        "current_model": request.model_name,
        "message": f"Switched from {old_model} to {request.model_name}",
    }


@router.post(
    "/models/pull",
    summary="Pull Ollama Model",
    description="Download a new model from Ollama library.",
)
async def pull_model(model_name: str = Query(..., description="Model to pull")):
    """
    Pull/download a model from Ollama.
    
    This may take a while for large models.
    """
    ai_service = get_ai_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    try:
        client = await ai_service._get_client()
        
        # Start pull (this is async in Ollama)
        response = await client.post(
            "/api/pull",
            json={"name": model_name, "stream": False},
            timeout=600.0,  # 10 min timeout for large models
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "model": model_name,
                "message": f"Successfully pulled {model_name}",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to pull model")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Action Execution Endpoints
# ============================================================================

class ActionRequest(BaseModel):
    """Request to execute an action."""
    action_type: str
    parameters: Dict[str, Any] = {}


class BatchActionRequest(BaseModel):
    """Request to execute multiple actions."""
    actions: List[ActionRequest]


@router.get(
    "/actions",
    summary="List Available Actions",
    description="Get all actions the AI can perform.",
)
async def list_actions():
    """Get all available AI actions with their parameters."""
    actions = []
    for name, defn in ACTION_REGISTRY.items():
        actions.append({
            "name": name,
            "description": defn.description,
            "parameters": defn.parameters,
            "required": defn.required_params,
            "examples": defn.examples,
        })
    return {"actions": actions}


@router.post(
    "/actions/execute",
    summary="Execute AI Action",
    description="Execute a single action.",
)
async def execute_action(request: ActionRequest):
    """Execute an action and return result with frontend commands."""
    executor = get_action_executor()
    result = await executor.execute(request.action_type, request.parameters)
    
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "frontend_action": result.frontend_action,
    }


@router.post(
    "/actions/batch",
    summary="Execute Multiple Actions",
    description="Execute a batch of actions in sequence.",
)
async def execute_batch_actions(request: BatchActionRequest):
    """Execute multiple actions and return all results."""
    executor = get_action_executor()
    
    results = []
    frontend_actions = []
    
    for action in request.actions:
        result = await executor.execute(action.action_type, action.parameters)
        results.append({
            "action": action.action_type,
            "success": result.success,
            "message": result.message,
        })
        if result.frontend_action:
            frontend_actions.append(result.frontend_action)
    
    return {
        "results": results,
        "frontend_actions": frontend_actions,
        "all_success": all(r["success"] for r in results),
    }


# ============================================================================
# Study Assistance Endpoints
# ============================================================================

class StudyPlanRequest(BaseModel):
    """Request to create a study plan."""
    subject: str
    topics: Optional[List[str]] = None
    exam_date: Optional[str] = None
    daily_hours: float = 2.0


class FlashcardRequest(BaseModel):
    """Request to generate flashcards."""
    topic: str
    count: int = 10
    notes_content: Optional[str] = None


class QuizRequest(BaseModel):
    """Request to generate a quiz."""
    topic: str
    count: int = 5


@router.post(
    "/study/plan",
    summary="Create Study Plan",
    description="Generate a comprehensive study plan.",
)
async def create_study_plan(request: StudyPlanRequest):
    """Create a personalized study plan with timetable."""
    study_service = get_study_service()
    
    try:
        plan = await study_service.create_study_plan(
            subject=request.subject,
            topics=request.topics,
            exam_date=request.exam_date,
            daily_hours=request.daily_hours,
        )
        
        # Convert to frontend-friendly format
        frontend_data = study_service.study_plan_to_blocks(plan)
        
        return {
            "success": True,
            "plan": {
                "id": plan.id,
                "subject": plan.subject,
                "total_hours": plan.total_hours,
                "exam_date": plan.exam_date,
                "topics": [
                    {"name": t.name, "hours": t.estimated_hours, "difficulty": t.difficulty}
                    for t in plan.topics
                ],
                "sessions_count": len(plan.sessions),
            },
            "blocks": frontend_data["blocks"],
            "calendar_tasks": frontend_data["calendar_tasks"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/study/explain",
    summary="Explain Topic",
    description="Get an AI explanation of a topic.",
)
async def explain_topic(
    topic: str = Query(..., description="Topic to explain"),
    depth: str = Query("medium", description="Depth: brief, medium, detailed"),
):
    """Get a clear explanation of any topic."""
    study_service = get_study_service()
    
    result = await study_service.explain_topic(topic=topic, depth=depth)
    return result


@router.post(
    "/study/flashcards",
    summary="Generate Flashcards",
    description="Create flashcards for studying.",
)
async def generate_flashcards(request: FlashcardRequest):
    """Generate flashcards from a topic or notes."""
    study_service = get_study_service()
    
    flashcards = await study_service.generate_flashcards(
        topic=request.topic,
        count=request.count,
        notes_content=request.notes_content,
    )
    
    return {
        "topic": request.topic,
        "flashcards": [
            {"id": f.id, "front": f.front, "back": f.back, "difficulty": f.difficulty}
            for f in flashcards
        ],
    }


@router.post(
    "/study/quiz",
    summary="Generate Quiz",
    description="Create a quiz for testing knowledge.",
)
async def generate_quiz(request: QuizRequest):
    """Generate quiz questions for a topic."""
    study_service = get_study_service()
    
    questions = await study_service.generate_quiz(
        topic=request.topic,
        count=request.count,
    )
    
    return {
        "topic": request.topic,
        "questions": [
            {
                "id": q.id,
                "question": q.question,
                "options": q.options,
                "difficulty": q.difficulty,
            }
            for q in questions
        ],
        # Send answers separately (for frontend quiz mode)
        "answers": {q.id: q.correct_answer for q in questions},
        "explanations": {q.id: q.explanation for q in questions},
    }


# ============================================================================
# Smart Chat Endpoint (with actions and memory)
# ============================================================================

class SmartChatRequest(BaseModel):
    """Request for smart AI chat."""
    message: str
    user_id: str = "default"
    execute_actions: bool = True
    include_study_help: bool = True
    stream: bool = False
    force_model: Optional[str] = None  # Override smart routing


@router.post(
    "/chat/smart",
    summary="Smart Chat",
    description="Chat with AI that can execute actions, remember context, and help with studying. Uses smart model routing.",
)
async def smart_chat(request: SmartChatRequest):
    """
    Intelligent chat that can:
    - Execute actions (create tasks, start timers, etc.)
    - Remember user preferences
    - Help with studying
    - Adapt to personality
    - Auto-select the best model for the task
    """
    ai_service = get_ai_service()
    profile_service = get_profile_service()
    action_executor = get_action_executor()
    smart_router = get_smart_router()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    try:
        # Extract any facts from the message
        await profile_service.extract_facts(request.user_id, request.message)
        
        # Get user profile context
        profile_context = profile_service.get_context_for_prompt(request.user_id)
        
        # Smart routing - detect task and select model
        routing = await smart_router.route(request.message, force_model=request.force_model)
        selected_model = routing["model"]
        task_type = routing["task_type"]
        
        # Build system prompt with actions
        tools_desc = action_executor.get_tools_description()
        
        system_prompt = f"""You are Aion, an intelligent productivity assistant.

{profile_context}

You can perform these actions for the user:
{tools_desc}

When the user asks you to do something, respond with your message AND any actions in this format:
[ACTION: action_name | param1=value1 | param2=value2]

Examples:
- User: "Create a task to review math"
  Response: "I'll create that task for you. [ACTION: create_task | text=Review math | priority=medium]"
  
- User: "Start a 30 minute timer"
  Response: "Starting a 30 minute focus timer now! [ACTION: start_timer | minutes=30]"

- User: "Help me study calculus"
  Response: "Let's set up a study session for calculus! [ACTION: set_focus | text=Studying Calculus] [ACTION: start_pomodoro | mode=work]"

Be helpful, concise, and proactive. If something would benefit from multiple actions, include them all.
"""
        
        # Get AI response using the routed model
        response = await ai_service.chat(
            message=request.message,
            system_prompt=system_prompt,
            temperature=0.7,
            model=selected_model,
        )
        
        # Parse actions from response
        actions = []
        clean_response = response
        
        if request.execute_actions:
            import re
            action_pattern = r'\[ACTION:\s*(\w+)\s*(?:\|([^\]]+))?\]'
            matches = re.findall(action_pattern, response)
            
            for match in matches:
                action_type = match[0]
                params_str = match[1] if match[1] else ""
                
                # Parse parameters
                params = {}
                if params_str:
                    for param in params_str.split("|"):
                        if "=" in param:
                            key, value = param.split("=", 1)
                            params[key.strip()] = value.strip()
                
                actions.append({"type": action_type, "params": params})
            
            # Remove action tags from response
            clean_response = re.sub(action_pattern, '', response).strip()
        
        # Execute actions
        frontend_actions = []
        if actions:
            for action in actions:
                result = await action_executor.execute(action["type"], action["params"])
                if result.frontend_action:
                    frontend_actions.append(result.frontend_action)
        
        # Adapt response to user preferences
        adapted_response = await profile_service.adapt_response(request.user_id, clean_response)
        
        return {
            "response": adapted_response,
            "actions_detected": len(actions),
            "frontend_actions": frontend_actions,
            "model": selected_model,
            "task_type": task_type.value if hasattr(task_type, 'value') else str(task_type),
            "routing_reason": routing.get("routing_reason", "default"),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Smart Model Routing Endpoints
# ============================================================================

@router.get(
    "/routing/info",
    summary="Get Routing Configuration",
    description="Get information about how tasks are routed to different models.",
)
async def get_routing_info():
    """Get the smart model routing configuration."""
    smart_router = get_smart_router()
    available = await smart_router.get_available_models()
    
    return {
        "available_models": available,
        "routing_config": smart_router.get_model_info(),
    }


@router.get(
    "/routing/stats",
    summary="Get Routing Statistics",
    description="Get usage statistics for model routing.",
)
async def get_routing_stats():
    """Get statistics on model usage by task type."""
    smart_router = get_smart_router()
    return smart_router.get_stats()


@router.post(
    "/routing/test",
    summary="Test Model Routing",
    description="Test which model would be selected for a given message.",
)
async def test_routing(message: str = Query(..., description="Message to test routing for")):
    """Test the smart routing for a message without sending to AI."""
    smart_router = get_smart_router()
    routing = await smart_router.route(message)
    
    return {
        "message": message,
        "selected_model": routing["model"],
        "task_type": routing["task_type"].value if hasattr(routing["task_type"], 'value') else str(routing["task_type"]),
        "reason": routing["routing_reason"],
    }


# ============================================================================
# WebSocket for Real-time Communication
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket connection for AI interaction.
    
    Supports:
    - Streaming chat responses
    - Real-time action execution
    - State synchronization
    """
    await websocket.accept()
    
    ai_service = get_ai_service()
    action_executor = get_action_executor()
    profile_service = get_profile_service()
    
    user_id = "default"
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            msg_type = data.get("type", "chat")
            
            if msg_type == "chat":
                # Handle chat message
                message = data.get("message", "")
                user_id = data.get("user_id", "default")
                
                # Extract facts
                await profile_service.extract_facts(user_id, message)
                
                # Get profile context
                profile_context = profile_service.get_context_for_prompt(user_id)
                
                # Build prompt
                tools_desc = action_executor.get_tools_description()
                system_prompt = f"""You are Aion, a helpful productivity assistant.
{profile_context}

Available actions:
{tools_desc}

Include actions as: [ACTION: name | param=value]
"""
                
                # Stream response
                if data.get("stream", True):
                    full_response = ""
                    async for chunk in ai_service.chat_stream(message, system_prompt):
                        full_response += chunk
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk,
                        })
                    
                    # Parse and execute actions
                    import re
                    action_pattern = r'\[ACTION:\s*(\w+)\s*(?:\|([^\]]+))?\]'
                    matches = re.findall(action_pattern, full_response)
                    
                    frontend_actions = []
                    for match in matches:
                        action_type = match[0]
                        params_str = match[1] if match[1] else ""
                        params = {}
                        if params_str:
                            for param in params_str.split("|"):
                                if "=" in param:
                                    key, value = param.split("=", 1)
                                    params[key.strip()] = value.strip()
                        
                        result = await action_executor.execute(action_type, params)
                        if result.frontend_action:
                            frontend_actions.append(result.frontend_action)
                    
                    # Send completion with actions
                    clean_response = re.sub(action_pattern, '', full_response).strip()
                    await websocket.send_json({
                        "type": "complete",
                        "response": clean_response,
                        "actions": frontend_actions,
                    })
                else:
                    # Non-streaming response
                    response = await ai_service.chat(message, system_prompt)
                    await websocket.send_json({
                        "type": "complete",
                        "response": response,
                    })
            
            elif msg_type == "action":
                # Execute a direct action
                action_type = data.get("action_type", "")
                params = data.get("params", {})
                
                result = await action_executor.execute(action_type, params)
                
                await websocket.send_json({
                    "type": "action_result",
                    "success": result.success,
                    "message": result.message,
                    "frontend_action": result.frontend_action,
                })
            
            elif msg_type == "state_sync":
                # Receive app state from frontend
                app_state = data.get("state", {})
                # Store for context (could be used for better AI responses)
                await websocket.send_json({
                    "type": "state_ack",
                    "received": True,
                })
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except:
            pass


# ============================================================================
# Intent Parsing Endpoints
# ============================================================================

class IntentRequest(BaseModel):
    """Request for intent parsing."""
    message: str = Field(..., min_length=1, description="User message to parse")


class IntentResponse(BaseModel):
    """Response from intent parsing."""
    action: str
    confidence: float
    parameters: dict
    reasoning: str


@router.post(
    "/intent",
    response_model=IntentResponse,
    summary="Parse Intent",
    description="Parse a user message to detect actionable intent.",
)
async def parse_intent(data: IntentRequest, current_user: CurrentUser):
    """
    Parse a user message to detect intent.
    
    Returns:
    - action: The detected action (create_block, search, schedule_event, etc.)
    - confidence: Confidence score (0-1)
    - parameters: Extracted parameters for the action
    - reasoning: Explanation of the detection
    """
    intent_service = get_intent_service()
    
    try:
        result = await intent_service.parse_intent(data.message)
        
        # Extract primary action from result
        if result.actions:
            primary = result.actions[0]
            return IntentResponse(
                action=primary.action_type,
                confidence=primary.confidence,
                parameters=primary.parameters,
                reasoning=primary.reasoning,
            )
        else:
            return IntentResponse(
                action="none",
                confidence=0.0,
                parameters={},
                reasoning=result.summary,
            )
    except Exception as e:
        # Return "none" action on error rather than failing
        return IntentResponse(
            action="none",
            confidence=0.0,
            parameters={},
            reasoning=f"Intent parsing failed: {str(e)}",
        )


# ============================================================================
# Chat Endpoints
# ============================================================================

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with AI",
    description="Send a message to the local AI and get a response.",
)
@limiter.limit("20/minute")
async def chat(request: Request, data: ChatRequest, current_user: CurrentUser):
    """
    Have a conversation with the local AI.
    
    The AI has access to your blocks and can help with:
    - Answering questions about your data
    - Generating content
    - Providing suggestions
    """
    ai_service = get_ai_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available. Make sure it's running.",
        )
    
    try:
        # Build enhanced system prompt with web search context
        system_prompt = data.system_prompt or ""
        used_model = data.model or ai_service.model
        
        # Web search for additional context
        if data.web_search:
            from app.services.search_service import get_search_service
            search_service = get_search_service()
            try:
                web_results = await search_service.search(data.message, num_results=3)
                if web_results:
                    web_context = "\n\n[Web Search Results]\n"
                    for i, result in enumerate(web_results, 1):
                        title = result.get('title', 'No title')
                        body = result.get('body', '')[:300]
                        url = result.get('href', '')
                        web_context += f"{i}. {title}\n   {body}\n   Source: {url}\n\n"
                    system_prompt = f"{system_prompt}\n\nUse the following web search results to help answer the user's question:\n{web_context}"
            except Exception as e:
                # Web search failed - continue without it
                import logging
                logging.warning(f"Web search failed: {e}")
        
        response = await ai_service.chat(
            message=data.message,
            system_prompt=system_prompt if system_prompt else None,
            context=data.context,
            temperature=data.temperature,
            model=used_model,
        )
        
        return ChatResponse(
            response=response,
            model=used_model,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat failed: {str(e)}",
        )


# ============================================================================
# Search Endpoints
# ============================================================================

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic Search",
    description="Search across all blocks using natural language.",
)
@limiter.limit("30/minute")
async def semantic_search(request: Request, data: SearchRequest, current_user: CurrentUser):
    """
    Perform semantic search across your blocks.
    
    Uses AI embeddings to find relevant content based on meaning,
    not just keywords.
    """
    vector_service = get_vector_service()
    
    if not await vector_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant is not available. Make sure it's running.",
        )
    
    try:
        results = await vector_service.semantic_search(
            query=data.query,
            limit=data.limit,
            block_id=data.block_id,
            content_types=data.content_types,
            score_threshold=data.score_threshold,
        )
        
        return SearchResponse(
            results=[SearchResult(**r) for r in results],
            query=data.query,
            total=len(results),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get(
    "/blocks/{block_id}/similar",
    response_model=list[dict],
    summary="Find Similar Blocks",
    description="Find blocks similar to the specified block.",
)
async def find_similar_blocks(
    block_id: str,
    limit: int = Query(5, ge=1, le=20),
):
    """Find blocks that are semantically similar to the given block."""
    vector_service = get_vector_service()
    
    if not await vector_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant is not available.",
        )
    
    try:
        results = await vector_service.find_similar_blocks(
            block_id=block_id,
            limit=limit,
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Similarity search failed: {str(e)}",
        )


# ============================================================================
# Screen Understanding Endpoints
# ============================================================================

@router.post(
    "/screen/analyze",
    response_model=ScreenAnalysisResponse,
    summary="Analyze Screenshot",
    description="Analyze a screenshot for context and suggestions.",
)
@limiter.limit("5/minute")
async def analyze_screen(
    request: Request,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="Screenshot image file"),
    extract_text: bool = Query(True, description="Also extract text via OCR"),
):
    """
    Analyze a screenshot to understand the current context.
    
    Returns:
    - Description of what's on screen
    - Extracted text (optional)
    - Contextual suggestions based on your blocks
    """
    ai_service = get_ai_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image.",
        )
    
    try:
        # Read and validate image size
        image_bytes = await validate_file_size(file)
        
        # Get description
        description = await ai_service.understand_screen(image_bytes=image_bytes)
        
        # Extract text if requested
        extracted_text = None
        if extract_text:
            extracted_text = await ai_service.extract_text_from_screen(
                image_bytes=image_bytes
            )
        
        # Get suggestions (would need block data from DB)
        # For now, return empty suggestions
        suggestions = []
        
        return ScreenAnalysisResponse(
            description=description,
            extracted_text=extracted_text,
            suggestions=suggestions,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screen analysis failed: {str(e)}",
        )


@router.post(
    "/screen/suggestions",
    summary="Get Contextual Suggestions",
    description="Get AI suggestions based on screen content and your blocks.",
)
async def get_screen_suggestions(
    file: UploadFile = File(..., description="Screenshot image file"),
):
    """
    Get contextual suggestions based on what's on screen.
    
    The AI will:
    1. Analyze the screenshot
    2. Compare with your existing blocks
    3. Suggest relevant actions (create note, add to block, etc.)
    """
    ai_service = get_ai_service()
    vector_service = get_vector_service()
    
    if not await ai_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama is not available.",
        )
    
    try:
        # Read, validate size, and analyze image
        image_bytes = await validate_file_size(file)
        description = await ai_service.understand_screen(image_bytes=image_bytes)
        
        # Search for relevant blocks based on screen content
        relevant_blocks = []
        if await vector_service.is_available():
            search_results = await vector_service.semantic_search(
                query=description,
                limit=10,
                content_types=["block"],
            )
            relevant_blocks = [
                {"name": r["title"], "description": r.get("text")}
                for r in search_results
            ]
        
        # Get AI suggestions
        suggestions = await ai_service.get_contextual_suggestions(
            screen_description=description,
            user_blocks=relevant_blocks,
        )
        
        return {
            "screen_description": description,
            "relevant_blocks": relevant_blocks,
            "suggestions": suggestions,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get suggestions: {str(e)}",
        )

@router.post(
    "/execute",
    summary="Execute Action",
    description="Execute a structured action proposed by the AI.",
)
@limiter.limit("5/minute")
async def execute_action(
    request: Request,
    current_user: CurrentUser,
    action_type: str,
    parameters: dict,
    service: ActionServiceDep
):
    """
    Perform a database or system action.
    """
    try:
        result = await service.execute_action(action_type, parameters)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Action execution failed: {str(e)}",
        )

@router.post(
    "/speak",
    summary="Text to Speech",
    description="Convert text to a human-like voice using ElevenLabs.",
)
async def text_to_speech(
    service: VoiceServiceDep,
    text: str = Query(..., min_length=1),
):
    """
    Generate audio from text. 
    Returns the audio bytes directly as an MP3 stream.
    """
    from fastapi.responses import Response
    
    audio_bytes = await service.text_to_speech(text)
    if not audio_bytes:
        # Fallback or error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech synthesis failed or not configured.",
        )
        
    return Response(content=audio_bytes, media_type="audio/mpeg")

@router.get(
    "/graph",
    summary="Get Neural Memory Graph",
    description="Retrieve nodes and links for semantic visualization.",
)
async def get_neural_graph(limit: int = 50):
    """
    Get all blocks and their semantic connections for visualization.
    """
    vector_service = get_vector_service()
    if not await vector_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector service not available.",
        )
    
    return await vector_service.get_semantic_graph(limit=limit)

# ============================================================================
# Persona / Adaptive Memory Endpoints
# ============================================================================

from app.services.persona_service import get_persona_service

class PersonaRuleRequest(BaseModel):
    content: str
    category: str = "general"

@router.post("/persona/rules", summary="Add Persona Rule")
async def add_persona_rule(request: PersonaRuleRequest):
    service = get_persona_service()
    return await service.add_rule(request.content, request.category)

@router.get("/persona/rules", summary="List Persona Rules")
async def list_persona_rules():
    service = get_persona_service()
    return await service.get_active_rules()

@router.delete("/persona/rules/{rule_id}", summary="Delete Persona Rule")
async def delete_persona_rule(rule_id: str):
    service = get_persona_service()
    success = await service.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}

# ============================================================================
# Autonomous Planning Endpoints
# ============================================================================

@router.post("/plan", response_model=Plan, summary="Create Autonomous Plan")
async def create_plan(
    request: PlanCreate,
    service: PlanningService = Depends(get_planning_service)
):
    """Generate a multi-step plan for a goal."""
    return await service.generate_plan(request.goal)

@router.get("/plan/{plan_id}", response_model=Plan, summary="Get Plan Status")
async def get_plan(
    plan_id: str,
    service: PlanningService = Depends(get_planning_service)
):
    """Get the current state of a plan."""
    plan = await service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.post("/plan/{plan_id}/execute/{step_id}", response_model=Plan, summary="Execute Plan Step")
async def execute_plan_step(
    plan_id: str,
    step_id: str,
    service: PlanningService = Depends(get_planning_service)
):
    """Execute a specific step in a plan."""
    return await service.execute_step(plan_id, step_id)

@router.post("/plan/execute/autonomous", response_model=Plan, summary="Run Plan Autonomously")
async def run_plan_autonomous(
    request: PlanExecute,
    service: PlanningService = Depends(get_planning_service)
):
    """Run all pending steps in a plan automatically."""
    return await service.run_autonomous(request.plan_id)

from starlette.websockets import WebSocketState

@router.websocket("/voice/stream")
async def websocket_voice_stream(
    websocket: WebSocket,
    voice_streaming: RealtimeVoiceServiceDep,
    stt_service: STTServiceDep,
    ai_service: AIService = Depends(get_ai_service)
):
    """
    Realtime Voice Interaction Endpoint.
    1. Receives Input (Text or Audio Bytes).
    2. If Audio -> Transcribe to Text (STT).
    3. Streams LLM tokens.
    4. Buffers sentences.
    5. Streams TTS audio chunks.
    """
    await websocket.accept()
    try:
        while True:
            # Receive message (can be text or binary)
            message = await websocket.receive()
            
            user_text = ""
            
            if "text" in message:
                user_text = message["text"]
            elif "bytes" in message:
                # Transcribe Audio
                # Send "Thinking" signal? Maybe frontend handles it.
                audio_bytes = message["bytes"]
                user_text = await stt_service.transcribe(audio_bytes)
                if not user_text:
                    # Failed to transcribe or silence
                    continue
                    
            if not user_text:
                continue

            # 1. Generate token stream from LLM
            token_stream = await ai_service.chat_stream(message=user_text)
            
            # 2. Process stream -> buffer sentences -> generate audio
            audio_stream = voice_streaming.process_token_stream(token_stream)
            
            # 3. Send audio chunks
            async for audio_chunk in audio_stream:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_bytes(audio_chunk)
            
            # Signal done
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text("END_OF_STREAM")
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Voice stream error: {e}")
        try:
            await websocket.close(code=1011)  # Internal server error
        except:
            pass
