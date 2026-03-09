"""Schemas for AI-powered block creation."""
from pydantic import BaseModel
from typing import Optional


class SmartActionRequest(BaseModel):
    message: str
    context_block_id: Optional[str] = None


class CreatedBlockInfo(BaseModel):
    id: str
    name: str
    parent_name: Optional[str] = None
    block_type: str = "default"
    depth: int = 0


class SmartActionResponse(BaseModel):
    action_taken: str
    blocks_created: list[CreatedBlockInfo] = []
    summary: str
