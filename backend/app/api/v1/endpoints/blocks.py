"""
Block API Endpoints - CRUD operations for hierarchical Blocks.

This module provides REST endpoints for:
- Block CRUD operations
- Hierarchy navigation (tree, ancestors, descendants)
- Block fields (custom database columns)
- Block entries (database rows)
"""

from typing import Optional, Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Path, status, Depends

from app.api.deps import BlockServiceDep, CurrentUser

# UUID path parameter type with validation
UUIDPath = Annotated[str, Path(
    pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    description="UUID identifier"
)]
from app.schemas.block import (
    BlockCreate,
    BlockUpdate,
    BlockResponse,
    BlockTreeResponse,
    BlockFieldCreate,
    BlockFieldUpdate,
    BlockFieldResponse,
    BlockEntryCreate,
    BlockEntryResponse,
    MoveBlockRequest,
)

router = APIRouter()


# ============================================================================
# Block CRUD Endpoints
# ============================================================================

@router.post(
    "",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Block",
    description="Create a new Block, optionally nested under a parent Block.",
)
async def create_block(
    data: BlockCreate,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockResponse:
    """
    Create a new Block with the following properties:
    
    - **name**: Block name (required)
    - **description**: Optional description
    - **icon**: Emoji or icon identifier
    - **color**: Hex color code (e.g., #FF5733)
    - **block_type**: Type of block (default, database, document, folder)
    - **parent_id**: Parent block ID for nesting (null for root)
    - **properties**: Custom metadata as JSON
    """
    try:
        block = await service.create_block(data)
        return BlockResponse.model_validate(block)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[BlockResponse],
    summary="List Blocks",
    description="Get a list of Blocks, optionally filtered by parent.",
)
async def list_blocks(
    service: BlockServiceDep,
    current_user: CurrentUser,
    parent_id: Optional[str] = Query(
        None,
        description="Filter by parent ID. Use 'root' or omit for root blocks.",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[BlockResponse]:
    """
    List Blocks with pagination.
    
    - Set `parent_id` to a block ID to get its children
    - Omit `parent_id` or set to 'root' to get root-level blocks
    """
    try:
        # Handle 'root' string as None
        if parent_id == "root":
            parent_id = None
        
        blocks, total = await service.get_blocks(
            parent_id=parent_id,
            limit=limit,
            offset=offset,
        )
        
        return [BlockResponse.model_validate(b) for b in blocks]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list blocks: {str(e)}",
        )


@router.get(
    "/tree",
    response_model=list[BlockTreeResponse],
    summary="Get Block Tree",
    description="Get Blocks as a nested tree structure.",
)
async def get_block_tree(
    service: BlockServiceDep,
    current_user: CurrentUser,
    parent_id: Optional[str] = Query(None, description="Root of the tree"),
    max_depth: int = Query(3, ge=1, le=10, description="Maximum depth to fetch"),
) -> list[BlockTreeResponse]:
    """
    Get a tree structure of Blocks with nested children.
    
    Useful for displaying the block hierarchy in a sidebar or navigator.
    """
    try:
        blocks = await service.get_block_tree(parent_id=parent_id, max_depth=max_depth)
        return [BlockTreeResponse.model_validate(b) for b in blocks]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get block tree: {str(e)}",
        )


@router.get(
    "/{block_id}",
    response_model=BlockResponse,
    summary="Get Block by ID",
)
async def get_block(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockResponse:
    """Get a single Block by its ID."""
    block = await service.get_block_by_id(block_id)
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Block not found: {block_id}",
        )
    return BlockResponse.model_validate(block)


@router.patch(
    "/{block_id}",
    response_model=BlockResponse,
    summary="Update Block",
)
async def update_block(
    block_id: UUIDPath,
    data: BlockUpdate,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockResponse:
    """
    Update a Block's properties.
    
    All fields are optional - only provided fields will be updated.
    To move a block, provide `parent_id` and optionally `position`.
    """
    try:
        block = await service.update_block(block_id, data)
        if not block:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Block not found: {block_id}",
            )
        return BlockResponse.model_validate(block)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Block",
)
async def delete_block(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> None:
    """
    Delete a Block and all its descendants.
    
    This operation is irreversible.
    """
    success = await service.delete_block(block_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Block not found: {block_id}",
        )


@router.post(
    "/{block_id}/move",
    response_model=BlockResponse,
    summary="Move Block",
)
async def move_block(
    block_id: UUIDPath,
    data: MoveBlockRequest,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockResponse:
    """
    Move a Block to a new parent or position.
    
    - Set `new_parent_id` to null to move to root level
    - `new_position` determines the order within the new parent
    """
    try:
        update_data = BlockUpdate(
            parent_id=data.new_parent_id,
            position=data.new_position,
        )
        block = await service.update_block(block_id, update_data)
        if not block:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Block not found: {block_id}",
            )
        return BlockResponse.model_validate(block)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ============================================================================
# Hierarchy Navigation Endpoints
# ============================================================================

@router.get(
    "/{block_id}/ancestors",
    response_model=list[BlockResponse],
    summary="Get Block Ancestors",
)
async def get_ancestors(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> list[BlockResponse]:
    """
    Get all ancestors of a Block from root to immediate parent.
    
    Useful for building breadcrumb navigation.
    """
    try:
        ancestors = await service.get_ancestors(block_id)
        return [BlockResponse.model_validate(b) for b in ancestors]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ancestors: {str(e)}",
        )


@router.get(
    "/{block_id}/descendants",
    response_model=list[BlockResponse],
    summary="Get Block Descendants",
)
async def get_descendants(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
    max_depth: Optional[int] = Query(None, ge=1, le=100),
) -> list[BlockResponse]:
    """
    Get all descendants of a Block.
    
    Use `max_depth` to limit how deep to traverse.
    """
    try:
        descendants = await service.get_descendants(block_id, max_depth=max_depth)
        return [BlockResponse.model_validate(b) for b in descendants]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get descendants: {str(e)}",
        )


# ============================================================================
# Block Field Endpoints (Database Columns)
# ============================================================================

@router.post(
    "/{block_id}/fields",
    response_model=BlockFieldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Field to Block",
)
async def add_field(
    block_id: UUIDPath,
    data: BlockFieldCreate,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockFieldResponse:
    """
    Add a custom field (database column) to a Block.
    
    Supported field types:
    - text, number, date, select, multi_select
    - checkbox, url, email, phone
    - relation, rollup, formula, file
    """
    try:
        field = await service.add_field(block_id, data)
        return BlockFieldResponse.model_validate(field)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{block_id}/fields",
    response_model=list[BlockFieldResponse],
    summary="Get Block Fields",
)
async def get_fields(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> list[BlockFieldResponse]:
    """Get all custom fields defined for a Block."""
    try:
        fields = await service.get_fields(block_id)
        return [BlockFieldResponse.model_validate(f) for f in fields]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get fields: {str(e)}",
        )


@router.patch(
    "/{block_id}/fields/{field_id}",
    response_model=BlockFieldResponse,
    summary="Update Block Field",
)
async def update_field(
    block_id: UUIDPath,
    field_id: UUIDPath,
    data: BlockFieldUpdate,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockFieldResponse:
    """Update a custom field definition."""
    try:
        field = await service.update_field(block_id, field_id, data)
        if not field:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Field not found: {field_id}",
            )
        return BlockFieldResponse.model_validate(field)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update field: {str(e)}",
        )


# ============================================================================
# Block Entry Endpoints (Database Rows)
# ============================================================================

@router.post(
    "/{block_id}/entries",
    response_model=BlockEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Entry in Block",
)
async def create_entry(
    block_id: UUIDPath,
    data: BlockEntryCreate,
    service: BlockServiceDep,
    current_user: CurrentUser,
) -> BlockEntryResponse:
    """
    Create a new entry (row) in a Block's database.
    
    The `data` field should contain values keyed by field IDs.
    """
    try:
        entry = await service.create_entry(block_id, data)
        return BlockEntryResponse.model_validate(entry)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create entry: {str(e)}",
        )


@router.get(
    "/{block_id}/entries",
    response_model=list[BlockEntryResponse],
    summary="Get Block Entries",
)
async def get_entries(
    block_id: UUIDPath,
    service: BlockServiceDep,
    current_user: CurrentUser,
    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[BlockEntryResponse]:
    """Get entries (rows) from a Block's database."""
    try:
        entries, total = await service.get_entries(
            block_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return [BlockEntryResponse.model_validate(e) for e in entries]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get entries: {str(e)}",
        )
