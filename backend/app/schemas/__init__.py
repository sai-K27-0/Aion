"""Schemas module initialization."""

from app.schemas.block import (
    BlockCreate,
    BlockUpdate,
    BlockResponse,
    BlockTreeResponse,
    BlockFieldCreate,
    BlockFieldResponse,
    BlockEntryCreate,
    BlockEntryResponse,
)
from app.schemas.device import (
    DeviceAIConfigCreate,
    DeviceAIConfigUpdate,
    DeviceAIConfigResponse,
    DeviceHardwareInfo,
    ModelRecommendationsResponse,
    OllamaHealthResponse,
    OllamaInstallInstructions,
)

__all__ = [
    "BlockCreate",
    "BlockUpdate",
    "BlockResponse",
    "BlockTreeResponse",
    "BlockFieldCreate",
    "BlockFieldResponse",
    "BlockEntryCreate",
    "BlockEntryResponse",
    "DeviceAIConfigCreate",
    "DeviceAIConfigUpdate",
    "DeviceAIConfigResponse",
    "DeviceHardwareInfo",
    "ModelRecommendationsResponse",
    "OllamaHealthResponse",
    "OllamaInstallInstructions",
]
