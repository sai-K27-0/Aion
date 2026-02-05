import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
from uuid import uuid4

from app.schemas.ai import Plan, TaskStep
from app.services.ai_service import AIService
from app.services.action_service import ActionService

logger = logging.getLogger(__name__)

class PlanningService:
    """Service for breaking goals into multi-step plans and executing them."""
    
    def __init__(self, ai_service: AIService, action_service: ActionService):
        self.ai = ai_service
        self.actions = action_service
        self._plans: Dict[str, Plan] = {} # In-memory storage for now

    async def generate_plan(self, goal: str) -> Plan:
        """Use LLM to decompose a goal into task steps."""
        logger.info(f"Generating plan for goal: {goal}")
        
        system_prompt = """You are Aion's Planning Engine.
        Your job is to break down a complex user goal into logical, sequential steps.
        Each step must use one of the available action types:
        - create_block: {name, description, block_type, parent_id}
        - update_block: {block_id, name, description}
        - web_search: {query}
        - browser_task: {task}
        - focus_mode: {topic, urls}
        
        Respond ONLY with a JSON array of steps. Example:
        [
            {"description": "Search for news", "action_type": "web_search", "parameters": {"query": "AI news"}, "reasoning": "Need base info"},
            {"description": "Create a block", "action_type": "create_block", "parameters": {"name": "AI News"}, "reasoning": "Store results"}
        ]
        """
        
        response = await self.ai.chat(
            message=f"Break this down into steps: {goal}",
            system_prompt=system_prompt,
            temperature=0.3
        )
        
        try:
            # Extract JSON from response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                steps_data = json.loads(response[start:end])
                steps = [TaskStep(**step) for step in steps_data]
            else:
                raise ValueError("No steps found in LLM response")
        except Exception as e:
            logger.error(f"Failed to parse plan steps: {e}")
            # Fallback simple plan
            steps = [TaskStep(
                description=f"Try to execute: {goal}",
                action_type="chat", # Handle as fallback
                parameters={"message": goal}
            )]

        plan = Plan(goal=goal, steps=steps)
        self._plans[plan.id] = plan
        return plan

    async def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    async def execute_step(self, plan_id: str, step_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError("Plan not found")
        
        step = next((s for s in plan.steps if s.id == step_id), None)
        if not step:
            raise ValueError("Step not found")
        
        step.status = "running"
        step.started_at = datetime.now()
        plan.status = "active"
        plan.updated_at = datetime.now()

        try:
            result = await self.actions.execute_action(step.action_type, step.parameters)
            step.status = "completed" if result.success else "failed"
            step.result = result.data or result.message
        except Exception as e:
            logger.error(f"Step execution error: {e}")
            step.status = "failed"
            step.result = str(e)
        
        step.completed_at = datetime.now()
        
        # Check if plan is complete
        if all(s.status == "completed" for s in plan.steps):
            plan.status = "completed"
        elif any(s.status == "failed" for s in plan.steps):
            plan.status = "failed"
            
        plan.updated_at = datetime.now()
        return plan

    async def run_autonomous(self, plan_id: str) -> Plan:
        """Run all pending steps in a plan sequentially."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError("Plan not found")
            
        for step in plan.steps:
            if step.status == "pending":
                await self.execute_step(plan_id, step.id)
                if step.status == "failed":
                    break
        
        return plan

# Note: get_planning_service is now in app.api.deps to avoid circular imports.
