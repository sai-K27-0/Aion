"""
Comprehensive tests for AI features.

Tests:
- Memory service
- RAG service
- Agent service
- Model router
- Evaluation service
- Prompt service
- Proactive service
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Test the prompt service
class TestPromptService:
    """Tests for the prompt template service."""
    
    def test_render_basic_template(self):
        """Test basic template rendering."""
        from app.services.prompt_service import get_prompt_service
        
        service = get_prompt_service()
        
        # Test that templates exist
        templates = service.list_templates()
        assert "system_default" in templates
        assert "intent_parser" in templates
        assert "query_expansion" in templates
    
    def test_render_with_variables(self):
        """Test rendering with custom variables."""
        from app.services.prompt_service import get_prompt_service
        
        service = get_prompt_service()
        
        rendered = service.render(
            "intent_parser",
            user_message="Create a note about AI",
        )
        
        assert "Create a note about AI" in rendered
        assert "create_block" in rendered  # Should have action list
    
    def test_render_with_missing_variables(self):
        """Test that missing variables don't cause errors."""
        from app.services.prompt_service import get_prompt_service
        
        service = get_prompt_service()
        
        # Should handle missing variables gracefully
        rendered = service.render("system_default")
        assert "You are Aion" in rendered
    
    def test_add_custom_template(self):
        """Test adding a custom template."""
        from app.services.prompt_service import get_prompt_service
        
        service = get_prompt_service()
        
        service.add_template("test_template", "Hello {name}!")
        rendered = service.render("test_template", name="World")
        
        assert rendered == "Hello World!"


class TestModelRouter:
    """Tests for the model routing service."""
    
    def test_select_model_for_task(self):
        """Test model selection based on task type."""
        from app.services.model_router import get_model_router, TaskType
        
        router = get_model_router()
        
        # Should return a model for each task type
        for task_type in TaskType:
            model = router.select_model(task_type)
            assert model is not None
            assert isinstance(model, str)
    
    def test_select_model_prefer_speed(self):
        """Test model selection with speed preference."""
        from app.services.model_router import get_model_router, TaskType
        
        router = get_model_router()
        
        model = router.select_model(TaskType.INTENT, prefer_speed=True)
        assert model is not None
    
    def test_select_model_prefer_quality(self):
        """Test model selection with quality preference."""
        from app.services.model_router import get_model_router, TaskType
        
        router = get_model_router()
        
        model = router.select_model(TaskType.CHAT, prefer_quality=True)
        assert model is not None
    
    def test_cache_operations(self):
        """Test response caching."""
        from app.services.model_router import get_model_router, TaskType
        
        router = get_model_router()
        
        # Cache a response
        query = "What is AI?"
        response = "AI is artificial intelligence."
        
        router.cache_response(query, response, "llama3.2", task_type=TaskType.CHAT)
        
        # Retrieve cached response
        cached = router.get_cached_response(query, task_type=TaskType.CHAT)
        assert cached == response
        
        # Different task type should not match
        cached2 = router.get_cached_response(query, task_type=TaskType.CODE)
        assert cached2 is None
    
    def test_usage_tracking(self):
        """Test usage statistics tracking."""
        from app.services.model_router import get_model_router
        
        router = get_model_router()
        
        router.track_usage("llama3.2", 100)
        router.track_usage("llama3.2", 50)
        
        stats = router.get_usage_stats()
        assert "llama3.2" in stats
        assert stats["llama3.2"]["requests"] >= 2
        assert stats["llama3.2"]["tokens"] >= 150


class TestEvaluationService:
    """Tests for the evaluation/metrics service."""
    
    def test_request_tracking(self):
        """Test tracking AI requests."""
        from app.services.evaluation_service import get_evaluation_service
        
        service = get_evaluation_service()
        
        # Start and end a request
        request_id = "test-123"
        service.start_request(request_id)
        
        metric = service.end_request(
            request_id,
            model="llama3.2",
            task_type="chat",
            input_tokens=50,
            output_tokens=100,
        )
        
        assert metric.id == request_id
        assert metric.model == "llama3.2"
        assert metric.success is True
        assert metric.latency_ms >= 0  # Can be 0 for very fast operations
    
    def test_feedback_tracking(self):
        """Test user feedback tracking."""
        from app.services.evaluation_service import get_evaluation_service, FeedbackType
        
        service = get_evaluation_service()
        
        # Create a request
        request_id = "test-feedback-123"
        service.start_request(request_id)
        service.end_request(request_id, "llama3.2", "chat", 10, 20)
        
        # Add feedback
        success = service.add_feedback(request_id, FeedbackType.THUMBS_UP, "Great answer!")
        assert success is True
    
    def test_metrics_summary(self):
        """Test metrics summary calculation."""
        from app.services.evaluation_service import get_evaluation_service
        
        service = get_evaluation_service()
        
        # Create some requests
        for i in range(5):
            rid = f"test-summary-{i}"
            service.start_request(rid)
            service.end_request(rid, "llama3.2", "chat", 10, 20, success=(i != 2))
        
        summary = service.get_summary(hours=1)
        
        assert summary.total_requests >= 5
        assert summary.successful_requests >= 4
        assert summary.failed_requests >= 1


class TestAgentService:
    """Tests for the ReAct agent service."""
    
    def test_agent_has_tools(self):
        """Test that agent has default tools registered."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        
        assert "search" in agent.tools
        assert "web_search" in agent.tools
        assert "calculator" in agent.tools
        assert "get_time" in agent.tools
    
    def test_parse_agent_response_with_action(self):
        """Test parsing agent response with action."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        
        response = """Thought: I need to search for information about AI.
Action: search
Action Input: {"query": "artificial intelligence"}"""
        
        step = agent._parse_agent_response(response)
        
        assert "search" in step.thought.lower() or step.action == "search"
        assert step.is_final is False
    
    def test_parse_agent_response_final_answer(self):
        """Test parsing agent response with final answer."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        
        response = """Thought: I have all the information I need.
Final Answer: AI is a field of computer science focused on creating intelligent machines."""
        
        step = agent._parse_agent_response(response)
        
        assert step.is_final is True
        assert "AI is a field" in step.final_answer
    
    @pytest.mark.asyncio
    async def test_calculator_tool(self):
        """Test the calculator tool."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        
        result = await agent._tool_calculator("2 + 2")
        assert "4" in result
        
        result = await agent._tool_calculator("10 * 5")
        assert "50" in result
    
    @pytest.mark.asyncio
    async def test_get_time_tool(self):
        """Test the get time tool."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        
        result = await agent._tool_get_time()
        assert "Current time" in result


class TestRAGService:
    """Tests for the RAG service."""
    
    def test_rag_service_exists(self):
        """Test that RAG service can be instantiated."""
        from app.services.rag_service import get_rag_service
        
        service = get_rag_service()
        assert service is not None
    
    @pytest.mark.asyncio
    async def test_query_expansion_format(self):
        """Test query expansion returns correct format."""
        from app.services.rag_service import get_rag_service
        
        service = get_rag_service()
        
        # Mock the AI service to return a predictable response
        with patch.object(service.ai_service, 'chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '["What is machine learning?", "ML definition", "AI learning"]'
            
            expansions = await service._expand_query("What is AI?")
            
            assert isinstance(expansions, list)
            assert len(expansions) <= 3


class TestProactiveService:
    """Tests for the proactive suggestions service."""
    
    def test_default_triggers(self):
        """Test that default triggers are registered."""
        from app.services.proactive_service import get_proactive_service
        
        service = get_proactive_service()
        
        assert "morning_briefing" in service.triggers
        assert "meeting_reminder" in service.triggers
    
    def test_add_custom_trigger(self):
        """Test adding a custom trigger."""
        from app.services.proactive_service import get_proactive_service, ProactiveTrigger, TriggerType
        
        service = get_proactive_service()
        
        trigger = ProactiveTrigger(
            id="test_trigger",
            type=TriggerType.TIME_BASED,
            name="Test Trigger",
            description="A test trigger",
            time="12:00",
        )
        
        service.add_trigger(trigger)
        assert "test_trigger" in service.triggers
    
    def test_enable_disable_trigger(self):
        """Test enabling and disabling triggers."""
        from app.services.proactive_service import get_proactive_service
        
        service = get_proactive_service()
        
        # Disable
        service.enable_trigger("morning_briefing", enabled=False)
        assert service.triggers["morning_briefing"].enabled is False
        
        # Re-enable
        service.enable_trigger("morning_briefing", enabled=True)
        assert service.triggers["morning_briefing"].enabled is True
    
    def test_dismiss_suggestion(self):
        """Test dismissing suggestions."""
        from app.services.proactive_service import get_proactive_service, Suggestion
        
        service = get_proactive_service()
        
        # Add a suggestion to the queue
        suggestion = Suggestion(
            id="test-suggestion",
            type="test",
            title="Test",
            content="Test content",
            priority=1,
            context={},
            timestamp=datetime.now(timezone.utc),
        )
        service.suggestions_queue.append(suggestion)
        
        # Dismiss it
        service.dismiss_suggestion("test-suggestion")
        
        # Should be removed
        ids = [s.id for s in service.suggestions_queue]
        assert "test-suggestion" not in ids


# Integration tests (require services to be running)
class TestIntegration:
    """Integration tests that require backend services."""
    
    @pytest.mark.skip(reason="Requires Ollama to be running")
    @pytest.mark.asyncio
    async def test_full_rag_query(self):
        """Test a full RAG query with real services."""
        from app.services.rag_service import get_rag_service
        
        service = get_rag_service()
        result = await service.query("What is artificial intelligence?")
        
        assert result.answer is not None
        assert result.confidence >= 0
        assert result.confidence <= 1
    
    @pytest.mark.skip(reason="Requires Ollama to be running")
    @pytest.mark.asyncio
    async def test_full_agent_run(self):
        """Test a full agent run with real services."""
        from app.services.agent_service import get_agent_service
        
        agent = get_agent_service()
        result = await agent.run("What is 25 * 4?")
        
        assert result.success is True
        assert "100" in result.answer


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
