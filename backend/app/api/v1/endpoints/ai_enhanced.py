"""
Enhanced AI API Endpoints - Advanced AI features.

Provides endpoints for:
- Conversation memory
- Agent execution
- RAG queries
- Proactive suggestions
- Metrics and evaluation
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import CurrentUser
from app.services.memory_service import MemoryService
from app.services.rag_service import get_rag_service, RAGResult
from app.services.agent_service import get_agent_service, AgentResult
from app.services.proactive_service import get_proactive_service, Suggestion
from app.services.evaluation_service import get_evaluation_service, FeedbackType
from app.services.model_router import get_model_router

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class ConversationMessage(BaseModel):
    role: str
    content: str


class ChatWithMemoryRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    use_memory: bool = True
    use_rag: bool = True


class ChatWithMemoryResponse(BaseModel):
    response: str
    conversation_id: str
    sources: Optional[List[dict]] = None
    confidence: Optional[float] = None
    facts_extracted: int = 0


class RAGQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    max_sources: int = Field(5, ge=1, le=10)
    rerank: bool = True
    expand_query: bool = True


class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    confidence: float
    reasoning: Optional[str] = None


class AgentRequest(BaseModel):
    request: str = Field(..., min_length=1)
    context: Optional[str] = None


class AgentResponse(BaseModel):
    answer: str
    steps: List[dict]
    tools_used: List[str]
    success: bool
    error: Optional[str] = None


class FeedbackRequest(BaseModel):
    request_id: str
    feedback: str  # thumbs_up, thumbs_down, flag
    comment: Optional[str] = None


class MetricsSummaryResponse(BaseModel):
    period_hours: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p95_latency_ms: float
    satisfaction_rate: float
    by_model: dict
    by_task: dict


# ============================================================================
# Conversation Memory Endpoints
# ============================================================================

@router.post(
    "/chat/memory",
    response_model=ChatWithMemoryResponse,
    summary="Chat with Memory",
    description="Chat with persistent conversation memory and fact extraction.",
)
async def chat_with_memory(
    request: ChatWithMemoryRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Chat with persistent memory.
    
    Features:
    - Maintains conversation history
    - Extracts and remembers facts
    - Uses RAG for relevant context
    - Automatic context summarization
    """
    from app.services.ai_service import get_ai_service
    
    memory_service = MemoryService(db, current_user.id)
    ai_service = get_ai_service()
    rag_service = get_rag_service()
    
    # Get or create conversation
    conversation = await memory_service.get_or_create_conversation(
        request.conversation_id
    )
    
    # Build context
    context_parts = []
    
    # Add conversation history
    history = await memory_service.get_conversation_context(conversation.id)
    
    # Add memory context
    if request.use_memory:
        memory_context = await memory_service.build_memory_context(request.message)
        if memory_context:
            context_parts.append(memory_context)
    
    # Add RAG context
    sources = []
    confidence = None
    if request.use_rag:
        rag_result = await rag_service.query(
            request.message,
            user_id=current_user.id,
            max_sources=3,
        )
        if rag_result.sources:
            sources = [s.to_dict() for s in rag_result.sources]
            context_parts.append(
                "\n[Relevant Notes]\n" + 
                "\n".join([f"- {s.title}: {s.content[:200]}" for s in rag_result.sources])
            )
        confidence = rag_result.confidence
    
    # Build system prompt
    system_prompt = "\n\n".join(context_parts) if context_parts else None
    
    # Add user message to history (store the returned ConversationMessage for fact extraction)
    user_message = await memory_service.add_message(
        conversation.id,
        "user",
        request.message,
    )
    
    # Generate response
    try:
        response = await ai_service.chat(
            message=request.message,
            system_prompt=system_prompt,
            context=history,
            temperature=0.7,
        )
        
        # Add assistant message
        await memory_service.add_message(
            conversation.id,
            "assistant",
            response,
            sources=sources,
            confidence=confidence,
        )
        
        # Extract facts from the user message (using the ConversationMessage object)
        facts = await memory_service.extract_facts_from_message(user_message)
        
        return ChatWithMemoryResponse(
            response=response,
            conversation_id=conversation.id,
            sources=sources if sources else None,
            confidence=confidence,
            facts_extracted=len(facts) if facts else 0,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}",
        )


@router.get(
    "/conversations",
    summary="List Conversations",
)
async def list_conversations(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """List user's conversations."""
    from sqlalchemy import select, desc
    from app.models.conversation import Conversation
    
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
    )
    conversations = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "title": c.title or "Untitled",
            "message_count": c.message_count,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in conversations
    ]


@router.get(
    "/facts",
    summary="List User Facts",
)
async def list_facts(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """List facts the AI has learned about the user."""
    memory_service = MemoryService(db, current_user.id)
    facts = await memory_service.get_user_facts(category=category, limit=limit)
    
    return [
        {
            "id": f.id,
            "category": f.category,
            "content": f.content,
            "confidence": f.confidence,
            "reference_count": f.reference_count,
            "created_at": f.created_at.isoformat(),
        }
        for f in facts
    ]


# ============================================================================
# RAG Endpoints
# ============================================================================

@router.post(
    "/rag/query",
    response_model=RAGQueryResponse,
    summary="RAG Query",
    description="Query using enhanced RAG with reranking.",
)
async def rag_query(
    request: RAGQueryRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Enhanced RAG query with:
    - Query expansion for better recall
    - Cross-encoder reranking
    - Confidence scoring
    """
    rag_service = get_rag_service()
    memory_service = MemoryService(db, current_user.id)
    
    # Get memory context
    memory_context = await memory_service.build_memory_context(request.question)
    
    result = await rag_service.query(
        request.question,
        user_id=current_user.id,
        max_sources=request.max_sources,
        rerank=request.rerank,
        expand_query=request.expand_query,
        memory_context=memory_context,
    )
    
    return RAGQueryResponse(
        answer=result.answer,
        sources=[s.to_dict() for s in result.sources],
        confidence=result.confidence,
        reasoning=result.reasoning,
    )


# ============================================================================
# Agent Endpoints
# ============================================================================

@router.post(
    "/agent/run",
    response_model=AgentResponse,
    summary="Run Agent",
    description="Run the ReAct agent to complete a task.",
)
async def run_agent(
    request: AgentRequest,
    current_user: CurrentUser,
):
    """
    Run the AI agent with tool use.
    
    The agent can:
    - Search your notes
    - Search the web
    - Do calculations
    - Create notes
    - And more...
    """
    agent_service = get_agent_service()
    
    try:
        result = await agent_service.run(
            request.request,
            context=request.context,
        )
        
        return AgentResponse(
            answer=result.answer,
            steps=[
                {
                    "thought": s.thought,
                    "action": s.action,
                    "action_input": s.action_input,
                    "observation": s.observation,
                    "is_final": s.is_final,
                }
                for s in result.steps
            ],
            tools_used=result.tools_used,
            success=result.success,
            error=result.error,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {str(e)}",
        )


# ============================================================================
# Proactive Suggestions
# ============================================================================

@router.get(
    "/suggestions",
    summary="Get Suggestions",
)
async def get_suggestions(
    current_user: CurrentUser,
):
    """Get proactive suggestions."""
    proactive_service = get_proactive_service()
    suggestions = proactive_service.get_pending_suggestions()
    
    return [
        {
            "id": s.id,
            "type": s.type,
            "title": s.title,
            "content": s.content,
            "priority": s.priority,
            "actionable": s.actionable,
            "action_type": s.action_type,
            "timestamp": s.timestamp.isoformat(),
        }
        for s in suggestions
    ]


@router.post(
    "/suggestions/contextual",
    summary="Get Contextual Suggestion",
)
async def get_contextual_suggestion(
    current_user: CurrentUser,
    active_window: Optional[str] = None,
    recent_activity: Optional[str] = None,
):
    """Get a suggestion based on current context."""
    proactive_service = get_proactive_service()
    
    context = {
        "active_window": active_window,
        "recent_activity": recent_activity or "Unknown",
        "upcoming_events": "None",  # Would integrate with calendar
        "goals": "None",  # Would get from user's blocks
    }
    
    suggestion = await proactive_service.get_contextual_suggestion(context)
    
    if suggestion:
        return {
            "id": suggestion.id,
            "type": suggestion.type,
            "title": suggestion.title,
            "content": suggestion.content,
            "priority": suggestion.priority,
        }
    
    return {"suggestion": None}


@router.delete(
    "/suggestions/{suggestion_id}",
    summary="Dismiss Suggestion",
)
async def dismiss_suggestion(
    suggestion_id: str,
    current_user: CurrentUser,
):
    """Dismiss a suggestion."""
    proactive_service = get_proactive_service()
    proactive_service.dismiss_suggestion(suggestion_id)
    return {"status": "dismissed"}


# ============================================================================
# Evaluation & Metrics
# ============================================================================

@router.post(
    "/feedback",
    summary="Submit Feedback",
)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: CurrentUser,
):
    """Submit feedback on an AI response."""
    eval_service = get_evaluation_service()
    
    feedback_type = FeedbackType(request.feedback)
    success = eval_service.add_feedback(
        request.request_id,
        feedback_type,
        request.comment,
    )
    
    return {"success": success}


@router.get(
    "/metrics",
    response_model=MetricsSummaryResponse,
    summary="Get Metrics",
)
async def get_metrics(
    current_user: CurrentUser,
    hours: int = Query(24, ge=1, le=168),
):
    """Get AI performance metrics."""
    eval_service = get_evaluation_service()
    summary = eval_service.get_summary(hours=hours)
    
    return MetricsSummaryResponse(
        period_hours=hours,
        total_requests=summary.total_requests,
        successful_requests=summary.successful_requests,
        failed_requests=summary.failed_requests,
        avg_latency_ms=summary.avg_latency_ms,
        p95_latency_ms=summary.p95_latency_ms,
        satisfaction_rate=summary.satisfaction_rate,
        by_model=summary.by_model,
        by_task=summary.by_task,
    )


@router.get(
    "/models",
    summary="List Available Models",
)
async def list_models(
    current_user: CurrentUser,
):
    """List available AI models and their stats."""
    from app.services.ai_service import get_ai_service
    
    model_router = get_model_router()
    ai_service = get_ai_service()
    
    # Refresh available models
    await model_router.refresh_available_models(ai_service)
    
    return {
        "available": model_router.available_models,
        "default": model_router.DEFAULT_MODEL,
        "cache_stats": model_router.get_cache_stats(),
        "usage_stats": model_router.get_usage_stats(),
    }
