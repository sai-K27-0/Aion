"""
AI Block Service - Autonomous block creation from natural language.

This service combines AIService (LLM chat) with BlockService (block CRUD)
to let the AI plan and create blocks from a user's natural-language request.
"""

import json
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import Block
from app.schemas.ai_block import CreatedBlockInfo, SmartActionResponse
from app.schemas.block import BlockCreate
from app.services.ai_service import AIService, get_ai_service
from app.services.block_service import BlockService

logger = logging.getLogger(__name__)

BLOCK_PLANNING_PROMPT = """\
You are Aion's Block Planning Module.
The user will describe what they want to organise. Your job is to return a
JSON **array** of block objects to create.

Each object MUST have:
  - "name"       (string, required)
  - "block_type" (string, one of: default, database, document, folder)
  - "children"   (array of the same shape, may be empty)

Optional fields:
  - "description" (string)
  - "parent_name" (string — name of an EXISTING block to nest under)

Rules:
1. Return ONLY valid JSON — no prose, no markdown fences.
2. Keep names short and clear.
3. Use "folder" for organisational groups, "document" for notes/pages,
   "database" for structured data, "default" otherwise.
4. Nest children logically; avoid more than 3 levels deep.
5. If the user's request is ambiguous, make a sensible default choice.

EXISTING TOP-LEVEL BLOCKS (for reference — use "parent_name" to nest under one):
{context}
"""


class AIBlockService:
    """Combines AI planning with block creation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai: AIService = get_ai_service()
        self.blocks = BlockService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def smart_action(
        self,
        user_id: str,
        message: str,
        context_block_id: Optional[str] = None,
    ) -> SmartActionResponse:
        """
        End-to-end flow:
        1. Gather existing blocks for context.
        2. Ask the AI to produce a creation plan (JSON).
        3. Parse the plan.
        4. Execute it (create blocks in the DB).
        5. Return a summary.
        """
        context_text = await self._get_block_context(context_block_id)

        system_prompt = BLOCK_PLANNING_PROMPT.replace("{context}", context_text)

        ai_response = await self.ai.chat(
            message=message,
            system_prompt=system_prompt,
            temperature=0.3,
        )

        plan = self._parse_plan(ai_response)

        if not plan:
            return SmartActionResponse(
                action_taken="none",
                blocks_created=[],
                summary="Could not determine which blocks to create from your request.",
            )

        created = await self._execute_plan(plan, context_block_id)

        names = ", ".join(b.name for b in created)
        return SmartActionResponse(
            action_taken="create_blocks",
            blocks_created=created,
            summary=f"Created {len(created)} block(s): {names}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_block_context(
        self, context_block_id: Optional[str] = None
    ) -> str:
        """Return a short textual summary of existing top-level blocks."""
        if context_block_id:
            block = await self.blocks.get_block_by_id(context_block_id)
            if block:
                children, _ = await self.blocks.get_blocks(
                    parent_id=context_block_id, limit=20
                )
                lines = [f"- {block.name} (current context)"]
                for child in children:
                    lines.append(f"  - {child.name} ({child.block_type})")
                return "\n".join(lines)

        # Fall back to root blocks
        roots, _ = await self.blocks.get_blocks(parent_id=None, limit=30)
        if not roots:
            return "(none yet)"
        return "\n".join(
            f"- {b.name} ({b.block_type})" for b in roots
        )

    def _parse_plan(self, ai_text: str) -> list[dict]:
        """
        Extract a JSON array from the AI response.

        Handles:
        - Raw JSON arrays
        - Markdown fenced code blocks (```json ... ```)
        - JSON embedded in surrounding prose
        """
        text = ai_text.strip()

        # 1. Try the raw string directly
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 2. Try extracting from markdown code fences
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            try:
                result = json.loads(fence_match.group(1).strip())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 3. Try finding the outermost [...] bracket pair
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        logger.warning("AIBlockService: could not parse plan from AI response")
        return []

    async def _execute_plan(
        self,
        plan: list[dict],
        context_block_id: Optional[str] = None,
    ) -> list[CreatedBlockInfo]:
        """Create blocks according to the parsed plan."""
        created: list[CreatedBlockInfo] = []

        for item in plan:
            name = item.get("name")
            if not name:
                continue

            block_type = item.get("block_type", "default")
            description = item.get("description")
            parent_name = item.get("parent_name")

            # Resolve parent
            parent_id: Optional[str] = context_block_id
            resolved_parent_name: Optional[str] = None

            if parent_name:
                parent_block = await self._find_block_by_name(parent_name)
                if parent_block:
                    parent_id = parent_block.id
                    resolved_parent_name = parent_block.name

            data = BlockCreate(
                name=name,
                block_type=block_type,
                description=description,
                parent_id=parent_id,
            )
            block = await self.blocks.create_block(data)
            created.append(
                CreatedBlockInfo(
                    id=block.id,
                    name=block.name,
                    parent_name=resolved_parent_name,
                    block_type=block.block_type,
                    depth=block.depth,
                )
            )

            # Recursively create children
            children_specs = item.get("children", [])
            if children_specs:
                child_infos = await self._create_children(
                    children_specs, parent_id=block.id
                )
                created.extend(child_infos)

        return created

    async def _create_children(
        self, children: list[dict], parent_id: str
    ) -> list[CreatedBlockInfo]:
        """Recursively create child blocks."""
        created: list[CreatedBlockInfo] = []
        for child_spec in children:
            name = child_spec.get("name")
            if not name:
                continue

            data = BlockCreate(
                name=name,
                block_type=child_spec.get("block_type", "default"),
                description=child_spec.get("description"),
                parent_id=parent_id,
            )
            block = await self.blocks.create_block(data)
            created.append(
                CreatedBlockInfo(
                    id=block.id,
                    name=block.name,
                    parent_name=None,
                    block_type=block.block_type,
                    depth=block.depth,
                )
            )

            grandchildren = child_spec.get("children", [])
            if grandchildren:
                created.extend(
                    await self._create_children(grandchildren, parent_id=block.id)
                )

        return created

    async def _find_block_by_name(self, name: str) -> Optional[Block]:
        """Find an existing block by exact name (case-insensitive, non-deleted)."""
        from sqlalchemy import func as sa_func

        query = (
            select(Block)
            .where(sa_func.lower(Block.name) == name.lower())
            .where(Block.is_deleted == False)  # noqa: E712 — SQLAlchemy requires ==
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
