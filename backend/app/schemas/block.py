"""
Pydantic schemas for Block API validation and serialization.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Block Schemas
# ============================================================================

class BlockBase(BaseModel):
    """Base schema for Block data."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Block name")
    description: Optional[str] = Field(None, max_length=5000, description="Block description")
    icon: Optional[str] = Field(None, max_length=50, description="Emoji or icon identifier")
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color code")
    block_type: str = Field("default", description="Block type (default, database, document, folder)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class BlockCreate(BlockBase):
    """Schema for creating a new Block."""
    
    parent_id: Optional[str] = Field(None, description="Parent block ID for nesting")
    position: Optional[int] = Field(None, ge=0, description="Order within parent")


class BlockUpdate(BaseModel):
    """Schema for updating a Block. All fields optional."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    block_type: Optional[str] = None
    properties: Optional[dict[str, Any]] = None
    parent_id: Optional[str] = Field(None, description="Move block to new parent")
    position: Optional[int] = Field(None, ge=0)


class BlockResponse(BlockBase):
    """Schema for Block API responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    parent_id: Optional[str]
    path: str
    depth: int
    position: int
    created_at: datetime
    updated_at: datetime
    
    # Counts (populated by service layer)
    children_count: int = 0
    entries_count: int = 0


class BlockTreeResponse(BlockResponse):
    """Schema for Block with nested children (tree view)."""
    
    children: list["BlockTreeResponse"] = Field(default_factory=list)


# Enable self-referential model
BlockTreeResponse.model_rebuild()


# ============================================================================
# Block Field Schemas
# ============================================================================

class BlockFieldBase(BaseModel):
    """Base schema for Block field definitions."""
    
    name: str = Field(..., min_length=1, max_length=255)
    field_type: str = Field(
        ...,
        description="Field type: text, number, date, select, multi_select, checkbox, url, email, phone, relation, rollup, formula, file",
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Field configuration")
    is_required: bool = False
    is_hidden: bool = False
    default_value: Optional[dict[str, Any]] = None


class BlockFieldCreate(BlockFieldBase):
    """Schema for creating a new Block field."""
    
    position: Optional[int] = Field(None, ge=0)


class BlockFieldUpdate(BaseModel):
    """Schema for updating a Block field."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    config: Optional[dict[str, Any]] = None
    is_required: Optional[bool] = None
    is_hidden: Optional[bool] = None
    default_value: Optional[dict[str, Any]] = None
    position: Optional[int] = Field(None, ge=0)


class BlockFieldResponse(BlockFieldBase):
    """Schema for Block field API responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    block_id: str
    position: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Block Entry Schemas
# ============================================================================

class BlockEntryBase(BaseModel):
    """Base schema for Block entries (database rows)."""
    
    data: dict[str, Any] = Field(default_factory=dict, description="Field values keyed by field ID")


class BlockEntryCreate(BlockEntryBase):
    """Schema for creating a new Block entry."""
    pass


class BlockEntryUpdate(BaseModel):
    """Schema for updating a Block entry."""
    
    data: Optional[dict[str, Any]] = None
    is_archived: Optional[bool] = None


class BlockEntryResponse(BlockEntryBase):
    """Schema for Block entry API responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    block_id: str
    is_archived: bool
    archived_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Block Content Schemas
# ============================================================================

class BlockContentBase(BaseModel):
    """Base schema for Block content (notes, documents)."""
    
    title: Optional[str] = Field(None, max_length=500)
    content: str = Field("", description="Rich text content (markdown)")
    content_type: str = Field("markdown", description="Content format: markdown, html, plain")


class BlockContentCreate(BlockContentBase):
    """Schema for creating new Block content."""
    
    position: Optional[int] = Field(None, ge=0)


class BlockContentUpdate(BaseModel):
    """Schema for updating Block content."""
    
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    content_type: Optional[str] = None
    position: Optional[int] = Field(None, ge=0)


class BlockContentResponse(BlockContentBase):
    """Schema for Block content API responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    block_id: str
    position: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Utility Schemas
# ============================================================================

class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class MoveBlockRequest(BaseModel):
    """Request to move a block within or between parents."""
    
    new_parent_id: Optional[str] = Field(None, description="New parent block ID (null for root)")
    new_position: int = Field(..., ge=0, description="New position within parent")
