"""
Block Service - Business logic for Block management.

This service handles all Block operations including:
- CRUD operations
- Hierarchy management (path computation, moves)
- Position ordering
- Batch operations
"""

from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import Block, BlockField, BlockEntry, BlockContent
from app.schemas.block import (
    BlockCreate,
    BlockUpdate,
    BlockFieldCreate,
    BlockFieldUpdate,
    BlockEntryCreate,
    BlockContentCreate,
    MoveBlockRequest,
)


class BlockService:
    """Service for Block management operations."""
    
    def __init__(self, db: AsyncSession, trigger_service = None):
        self.db = db
        self.trigger_service = trigger_service
    
    # ========================================================================
    # Block CRUD Operations
    # ========================================================================
    
    async def create_block(self, data: BlockCreate) -> Block:
        """
        Create a new Block.
        
        Automatically computes:
        - path: Materialized path from root
        - depth: Nesting level
        - position: Order within parent (appends to end if not specified)
        """
        block = Block(
            id=str(uuid4()),
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            block_type=data.block_type,
            properties=data.properties,
            parent_id=data.parent_id,
        )
        
        # Compute hierarchy info
        if data.parent_id:
            parent = await self.get_block_by_id(data.parent_id)
            if parent:
                block.path = f"{parent.path}.{parent.id}" if parent.path else parent.id
                block.depth = parent.depth + 1
            else:
                raise ValueError(f"Parent block not found: {data.parent_id}")
        else:
            block.path = ""
            block.depth = 0
        
        # Compute position (append to end if not specified)
        if data.position is not None:
            block.position = data.position
        else:
            max_position = await self._get_max_position(data.parent_id)
            block.position = max_position + 1
        
        self.db.add(block)
        await self.db.flush()
        await self.db.refresh(block)
        
        # Fire Triggers
        if self.trigger_service:
            await self.trigger_service.check_triggers(
                event_type="block_created",
                context={
                    "block_id": block.id,
                    "block_name": block.name,
                    "block_type": block.block_type
                }
            )
        
        return block
    
    async def get_block_by_id(
        self,
        block_id: str,
        include_children: bool = False,
        include_fields: bool = False,
    ) -> Optional[Block]:
        """
        Get a Block by ID with optional eager loading.
        """
        query = select(Block).where(Block.id == block_id)
        
        if include_children:
            query = query.options(selectinload(Block.children))
        if include_fields:
            query = query.options(selectinload(Block.fields))
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_blocks(
        self,
        parent_id: Optional[str] = None,
        include_children: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[Block], int]:
        """
        Get blocks with optional filtering.
        
        Args:
            parent_id: Filter by parent (None for root blocks)
            include_children: Eager load children
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            Tuple of (blocks, total_count)
        """
        # Base query — always exclude soft-deleted blocks
        if parent_id is not None:
            query = select(Block).where(
                and_(Block.parent_id == parent_id, Block.is_deleted == False)
            )
            count_query = select(func.count(Block.id)).where(
                and_(Block.parent_id == parent_id, Block.is_deleted == False)
            )
        else:
            # Root blocks (no parent)
            query = select(Block).where(
                and_(Block.parent_id.is_(None), Block.is_deleted == False)
            )
            count_query = select(func.count(Block.id)).where(
                and_(Block.parent_id.is_(None), Block.is_deleted == False)
            )
        
        # Add ordering
        query = query.order_by(Block.position)
        
        # Add eager loading
        if include_children:
            query = query.options(selectinload(Block.children))
        
        # Add pagination
        query = query.limit(limit).offset(offset)
        
        # Execute
        result = await self.db.execute(query)
        blocks = result.scalars().all()
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        return blocks, total
    
    async def update_block(self, block_id: str, data: BlockUpdate) -> Optional[Block]:
        """
        Update a Block's properties.
        
        Note: Moving to a new parent requires special handling
        to update paths of all descendants.
        """
        block = await self.get_block_by_id(block_id)
        if not block:
            return None
        
        # Update simple fields
        update_data = data.model_dump(exclude_unset=True, exclude={"parent_id", "position"})
        for key, value in update_data.items():
            setattr(block, key, value)
        
        # Handle parent change (move operation)
        if data.parent_id is not None and data.parent_id != block.parent_id:
            await self._move_block(block, data.parent_id, data.position or 0)
        elif data.position is not None and data.position != block.position:
            await self._reorder_block(block, data.position)
        
        await self.db.flush()
        await self.db.refresh(block)
        
        # Fire Triggers
        if self.trigger_service:
            await self.trigger_service.check_triggers(
                event_type="block_updated",
                context={
                    "block_id": block.id,
                    "block_name": block.name,
                    "block_type": block.block_type
                }
            )
            
        return block
    
    async def delete_block(self, block_id: str) -> bool:
        """Soft-delete a block and all its descendants."""
        block = await self.get_block_by_id(block_id)
        if not block:
            return False

        # Soft-delete descendants
        path_prefix = f"{block.path}.{block.id}" if block.path else block.id
        await self.db.execute(
            update(Block)
            .where(Block.path.like(f"{path_prefix}%"))
            .values(is_deleted=True)
        )

        # Soft-delete the block itself
        block.is_deleted = True
        await self.db.commit()
        return True
    
    # ========================================================================
    # Hierarchy Operations
    # ========================================================================
    
    async def get_ancestors(self, block_id: str) -> Sequence[Block]:
        """Get all ancestors of a block from root to parent."""
        block = await self.get_block_by_id(block_id)
        if not block or not block.path:
            return []
        
        ancestor_ids = block.path.split(".")
        if not ancestor_ids or ancestor_ids == [""]:
            return []
        
        query = select(Block).where(Block.id.in_(ancestor_ids))
        result = await self.db.execute(query)
        ancestors = result.scalars().all()
        
        # Sort by depth
        return sorted(ancestors, key=lambda b: b.depth)
    
    async def get_descendants(
        self,
        block_id: str,
        max_depth: Optional[int] = None,
    ) -> Sequence[Block]:
        """Get all descendants of a block."""
        block = await self.get_block_by_id(block_id)
        if not block:
            return []
        
        # Find all blocks whose path starts with this block's full path
        path_prefix = f"{block.path}.{block.id}" if block.path else block.id
        
        query = select(Block).where(Block.path.like(f"{path_prefix}%"))
        
        if max_depth is not None:
            query = query.where(Block.depth <= block.depth + max_depth)
        
        query = query.order_by(Block.depth, Block.position)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_block_tree(
        self,
        parent_id: Optional[str] = None,
        max_depth: int = 3,
    ) -> Sequence[Block]:
        """
        Get a block tree structure with nested children.
        
        Returns blocks with children eager-loaded up to max_depth.
        """
        # Start from root or specified parent
        if parent_id:
            parent = await self.get_block_by_id(parent_id, include_children=True)
            if not parent:
                return []
            blocks = [parent]
        else:
            blocks, _ = await self.get_blocks(parent_id=None, include_children=True)
        
        # Recursively load children up to max_depth
        async def load_children(block: Block, current_depth: int):
            if current_depth >= max_depth:
                return
            
            for child in block.children:
                await self.db.refresh(child, ["children"])
                await load_children(child, current_depth + 1)
        
        for block in blocks:
            await load_children(block, 0)
        
        return blocks
    
    async def _move_block(
        self,
        block: Block,
        new_parent_id: Optional[str],
        new_position: int,
    ) -> None:
        """
        Move a block to a new parent.
        
        Updates the path of the block and all its descendants.
        """
        old_path_prefix = f"{block.path}.{block.id}" if block.path else block.id
        
        # Compute new path
        if new_parent_id:
            new_parent = await self.get_block_by_id(new_parent_id)
            if not new_parent:
                raise ValueError(f"New parent not found: {new_parent_id}")
            
            # Prevent moving to own descendant
            if new_parent.path.startswith(old_path_prefix):
                raise ValueError("Cannot move block to its own descendant")
            
            new_path = f"{new_parent.path}.{new_parent.id}" if new_parent.path else new_parent.id
            new_depth = new_parent.depth + 1
        else:
            new_path = ""
            new_depth = 0
        
        old_depth = block.depth
        depth_diff = new_depth - old_depth
        
        # Update descendants' paths
        new_path_prefix = f"{new_path}.{block.id}" if new_path else block.id
        
        # Get all descendants and update their paths
        descendants = await self.get_descendants(block.id)
        for desc in descendants:
            desc.path = desc.path.replace(old_path_prefix, new_path_prefix, 1)
            desc.depth += depth_diff
        
        # Update the block itself
        block.parent_id = new_parent_id
        block.path = new_path
        block.depth = new_depth
        block.position = new_position
    
    async def _reorder_block(self, block: Block, new_position: int) -> None:
        """Reorder a block within its parent."""
        old_position = block.position
        
        if new_position == old_position:
            return
        
        # Shift other blocks
        if new_position < old_position:
            # Moving up: shift blocks down
            await self.db.execute(
                update(Block)
                .where(
                    and_(
                        Block.parent_id == block.parent_id,
                        Block.position >= new_position,
                        Block.position < old_position,
                    )
                )
                .values(position=Block.position + 1)
            )
        else:
            # Moving down: shift blocks up
            await self.db.execute(
                update(Block)
                .where(
                    and_(
                        Block.parent_id == block.parent_id,
                        Block.position > old_position,
                        Block.position <= new_position,
                    )
                )
                .values(position=Block.position - 1)
            )
        
        block.position = new_position
    
    async def _get_max_position(self, parent_id: Optional[str]) -> int:
        """Get the maximum position among siblings."""
        query = select(func.coalesce(func.max(Block.position), -1))
        
        if parent_id:
            query = query.where(Block.parent_id == parent_id)
        else:
            query = query.where(Block.parent_id.is_(None))
        
        result = await self.db.execute(query)
        return result.scalar() or -1
    
    # ========================================================================
    # Block Field Operations
    # ========================================================================
    
    async def add_field(self, block_id: str, data: BlockFieldCreate) -> BlockField:
        """Add a custom field to a block's database."""
        # Verify block exists
        block = await self.get_block_by_id(block_id)
        if not block:
            raise ValueError(f"Block not found: {block_id}")
        
        # Get next position
        if data.position is None:
            query = select(func.coalesce(func.max(BlockField.position), -1)).where(
                BlockField.block_id == block_id
            )
            result = await self.db.execute(query)
            position = (result.scalar() or -1) + 1
        else:
            position = data.position
        
        field = BlockField(
            id=str(uuid4()),
            block_id=block_id,
            name=data.name,
            field_type=data.field_type,
            config=data.config,
            position=position,
            is_required=data.is_required,
            is_hidden=data.is_hidden,
            default_value=data.default_value,
        )
        
        self.db.add(field)
        await self.db.flush()
        await self.db.refresh(field)
        
        return field
    
    async def get_fields(self, block_id: str) -> Sequence[BlockField]:
        """Get all fields for a block."""
        query = (
            select(BlockField)
            .where(BlockField.block_id == block_id)
            .order_by(BlockField.position)
        )
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def update_field(self, block_id: str, field_id: str, data: BlockFieldUpdate) -> Optional[BlockField]:
        """Update a custom field definition."""
        query = select(BlockField).where(
            and_(BlockField.id == field_id, BlockField.block_id == block_id)
        )
        result = await self.db.execute(query)
        field = result.scalar_one_or_none()
        
        if not field:
            return None
            
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(field, key, value)
            
        await self.db.flush()
        await self.db.refresh(field)
        return field
    
    # ========================================================================
    # Block Entry Operations
    # ========================================================================
    
    async def create_entry(self, block_id: str, data: BlockEntryCreate) -> BlockEntry:
        """Create a new entry in a block's database."""
        entry = BlockEntry(
            id=str(uuid4()),
            block_id=block_id,
            data=data.data,
        )
        
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        
        return entry
    
    async def get_entries(
        self,
        block_id: str,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[BlockEntry], int]:
        """Get entries for a block with pagination."""
        query = select(BlockEntry).where(BlockEntry.block_id == block_id)
        count_query = select(func.count(BlockEntry.id)).where(BlockEntry.block_id == block_id)
        
        if not include_archived:
            query = query.where(BlockEntry.is_archived == False)
            count_query = count_query.where(BlockEntry.is_archived == False)
        
        query = query.order_by(BlockEntry.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        entries = result.scalars().all()
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        return entries, total
