"""
Action Service - Executes structured actions parsed by IntentService.

This service acts as the 'hands' of the AI, taking intent objects 
and calling the appropriate domain services (BlockService, etc.) 
to perform database operations.
"""

import logging
from typing import Any, Optional
from pydantic import BaseModel

from app.services.block_service import BlockService
from app.services.search_service import SearchService
from app.services.browser_service import BrowserService
from app.schemas.block import BlockCreate, BlockUpdate, BlockFieldCreate, BlockEntryCreate
from app.api.deps import get_db

logger = logging.getLogger(__name__)

class ActionExecutionResult(BaseModel):
    """Result of an action execution."""
    success: bool
    action_type: str
    message: str
    data: Optional[Any] = None

class ActionService:
    """Service to execute structured actions against the system."""
    
    def __init__(self, block_service: BlockService, search_service: SearchService, browser_service: BrowserService):
        self.blocks = block_service
        self.search_service = search_service
        self.browser = browser_service
    
    async def execute_action(self, action_type: str, parameters: dict[str, Any]) -> ActionExecutionResult:
        """
        Execute a specific action based on type and parameters.
        """
        try:
            if action_type == "create_block" or action_type == "add_to_block":
                return await self._execute_create_block(parameters)
            elif action_type == "update_block":
                return await self._execute_update_block(parameters)
            elif action_type == "schedule_event":
                # For now, schedule_event also creates a block of type 'event'
                parameters["block_type"] = "event"
                return await self._execute_create_block(parameters)
            elif action_type == "web_search":
                return await self._execute_web_search(parameters)
            elif action_type == "browser_task":
                return await self._execute_browser_task(parameters)
            elif action_type == "focus_mode":
                return await self._execute_focus_mode(parameters)
            else:
                return ActionExecutionResult(
                    success=False,
                    action_type=action_type,
                    message=f"Action type '{action_type}' is not yet supported for execution."
                )
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return ActionExecutionResult(
                success=False,
                action_type=action_type,
                message=f"Execution error: {str(e)}"
            )

    async def _execute_create_block(self, params: dict[str, Any]) -> ActionExecutionResult:
        """Helper to create a block from AI parameters."""
        name = params.get("name") or params.get("title")
        if not name:
             return ActionExecutionResult(success=False, action_type="create_block", message="Missing block name.")
        
        block_data = BlockCreate(
            name=name,
            description=params.get("description", ""),
            block_type=params.get("block_type", "default"),
            parent_id=params.get("parent_id"),
            properties=params.get("properties", {})
        )
        
        block = await self.blocks.create_block(block_data)
        
        # If it's a database, maybe add some default fields?
        if params.get("block_type") == "database":
            await self.blocks.add_field(block.id, BlockFieldCreate(name="Status", field_type="select"))
            await self.blocks.add_field(block.id, BlockFieldCreate(name="Last Updated", field_type="date"))

        return ActionExecutionResult(
            success=True,
            action_type="create_block",
            message=f"Successfully created block '{name}'",
            data={"id": block.id, "name": block.name}
        )

    async def _execute_update_block(self, params: dict[str, Any]) -> ActionExecutionResult:
        """Helper to update a block from AI parameters."""
        block_id = params.get("block_id")
        if not block_id:
             return ActionExecutionResult(success=False, action_type="update_block", message="Missing block ID.")
        
        update_data = BlockUpdate(
            name=params.get("name"),
            description=params.get("description"),
            properties=params.get("properties")
        )
        
        block = await self.blocks.update_block(block_id, update_data)
        if not block:
            return ActionExecutionResult(success=False, action_type="update_block", message="Block not found.")
            
        return ActionExecutionResult(
            success=True,
            action_type="update_block",
            message=f"Successfully updated block '{block.name}'",
            data={"id": block.id}
        )

    async def _execute_web_search(self, params: dict[str, Any]) -> ActionExecutionResult:
        """Helper to perform a web search with Deep Research capabilities."""
        query = params.get("query")
        if not query:
            return ActionExecutionResult(success=False, action_type="web_search", message="Missing search query.")
        
        # 1. Get Search Results
        results = await self.search_service.search(query)
        if not results:
             return ActionExecutionResult(success=False, action_type="web_search", message=f"No results found for '{query}'")

        # 2. Deep Research: Scrape the top result for more context
        top_url = results[0].get('href')
        deep_content = ""
        if top_url:
            logger.info(f"Performing Deep Research on: {top_url}")
            scraped_text = await self.search_service.scrape_url(top_url)
            if scraped_text:
                deep_content = f"\n\n--- Deep Research Content from {top_url} ---\n{scraped_text}\n"

        # 3. Format results for the AI
        formatted_results = "\n\n".join([
            f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}"
            for r in results
        ])
        
        full_context = formatted_results + deep_content

        return ActionExecutionResult(
            success=True,
            action_type="web_search",
            message=f"Found {len(results)} results for '{query}'. Deep Research performed on top link.",
            data={"results": results, "formatted": full_context}
        )

    async def _execute_browser_task(self, params: dict[str, Any]) -> ActionExecutionResult:
        """Helper to execute autonomous browser tasks."""
        task = params.get("task")
        if not task:
            return ActionExecutionResult(success=False, action_type="browser_task", message="Missing task description.")
        
        result = await self.browser.execute_browser_task(task)
        success = "Error" not in result
        
        return ActionExecutionResult(
            success=success,
            action_type="browser_task",
            message=result if success else f"Browser task failed: {result}",
            data={"result": result}
        )

    async def _execute_focus_mode(self, params: dict[str, Any]) -> ActionExecutionResult:
        """Helper to prepare workspace for focused work."""
        topic = params.get("topic", "General Work")
        urls = params.get("urls", [])
        
        # If no URLs provided, try to infer some common ones or search
        if not urls:
            if "aion" in topic.lower():
                urls = ["https://github.com", "http://localhost:1420"]
            else:
                urls = ["https://google.com"]
        
        success = await self.browser.prepare_workspace(urls)
        
        return ActionExecutionResult(
            success=success,
            action_type="focus_mode",
            message=f"Workspace prepared for '{topic}'. {len(urls)} tabs opened." if success else "Failed to open some tabs.",
            data={"urls": urls}
        )

# Note: get_action_service and ActionServiceDep are now in app.api.deps to avoid circular imports.
