"""
Device Schemas - Pydantic models for device management and AI configuration.
"""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════
# Device AI Configuration Schemas
# ═══════════════════════════════════════════════════════════════════════════

class DeviceHardwareInfo(BaseModel):
    """Hardware info reported by the client device."""
    ram_gb: Optional[float] = None
    cpu_cores: Optional[int] = None
    gpu_name: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    free_disk_gb: Optional[float] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None


class OllamaStatusReport(BaseModel):
    """Ollama status reported by the client device."""
    installed: bool = False
    version: Optional[str] = None
    running: bool = False
    url: str = "http://localhost:11434"
    models_installed: list[str] = Field(default_factory=list)


class DeviceAIConfigCreate(BaseModel):
    """Request to create/set AI config for a device."""
    ai_source: str = Field(
        "local_ollama",
        description="AI source: local_ollama, remote_ollama, openrouter, openai, anthropic, none",
    )
    # Ollama
    ollama_url: Optional[str] = Field(None, description="Ollama API URL")
    ollama_model: Optional[str] = Field(None, description="Chat model name")
    ollama_embedding_model: Optional[str] = Field(None, description="Embedding model name")
    # Cloud API
    api_provider: Optional[str] = Field(None, description="Cloud provider name")
    api_key: Optional[str] = Field(None, description="API key (will be encrypted at rest)")
    api_model: Optional[str] = Field(None, description="Cloud model name")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    # Fallback
    fallback_source: Optional[str] = Field(None, description="Fallback AI source")
    fallback_api_key: Optional[str] = Field(None, description="Fallback API key")
    fallback_api_model: Optional[str] = Field(None, description="Fallback model name")
    auto_fallback: bool = Field(True, description="Auto-switch to fallback on failure")
    # Hardware (optional, for model recommendations)
    hardware: Optional[DeviceHardwareInfo] = None
    # Ollama status (optional, reported by client)
    ollama_status: Optional[OllamaStatusReport] = None


class DeviceAIConfigUpdate(BaseModel):
    """Partial update for device AI config."""
    ai_source: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_embedding_model: Optional[str] = None
    api_provider: Optional[str] = None
    api_key: Optional[str] = None
    api_model: Optional[str] = None
    api_base_url: Optional[str] = None
    fallback_source: Optional[str] = None
    fallback_api_key: Optional[str] = None
    fallback_api_model: Optional[str] = None
    auto_fallback: Optional[bool] = None
    hardware: Optional[DeviceHardwareInfo] = None
    ollama_status: Optional[OllamaStatusReport] = None


class DeviceAIConfigResponse(BaseModel):
    """Response with device AI config (never exposes raw API keys)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    ai_source: str
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_embedding_model: Optional[str] = None
    api_provider: Optional[str] = None
    api_model: Optional[str] = None
    api_base_url: Optional[str] = None
    has_api_key: bool = False
    fallback_source: Optional[str] = None
    fallback_api_model: Optional[str] = None
    has_fallback_key: bool = False
    auto_fallback: bool = True
    # Hardware
    device_ram_gb: Optional[float] = None
    device_cpu_cores: Optional[int] = None
    device_gpu_name: Optional[str] = None
    device_gpu_vram_gb: Optional[float] = None
    device_free_disk_gb: Optional[float] = None
    device_os: Optional[str] = None
    # Ollama
    ollama_installed: Optional[bool] = None
    ollama_version: Optional[str] = None
    ollama_models_installed: list[str] = Field(default_factory=list)
    # Status
    setup_completed: bool = False
    last_health_check: Optional[datetime] = None
    last_health_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════════════
# Model Recommendation Schemas
# ═══════════════════════════════════════════════════════════════════════════

class ModelRecommendation(BaseModel):
    """A single model recommendation."""
    model_name: str
    display_name: str
    description: str
    size_gb: float
    ram_required_gb: float
    speed_description: str
    category: str = Field(description="chat, embedding, vision, coding")
    recommended: bool = False
    reason: str = ""
    can_run_on_device: bool = True
    warning: Optional[str] = None


class ModelRecommendationsResponse(BaseModel):
    """Full recommendation set for a device."""
    device_tier: str = Field(description="high, medium, low, minimal")
    device_summary: str
    chat_models: list[ModelRecommendation]
    embedding_models: list[ModelRecommendation]
    cloud_alternatives: list[ModelRecommendation]
    recommended_chat: Optional[str] = None
    recommended_embedding: Optional[str] = None
    total_download_gb: float = 0.0
    estimated_download_minutes: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Ollama Setup Schemas
# ═══════════════════════════════════════════════════════════════════════════

class OllamaInstallInstructions(BaseModel):
    """Platform-specific Ollama installation instructions."""
    platform: str
    is_installed: bool = False
    ollama_version: Optional[str] = None
    install_method: str = Field(description="auto, manual, not_supported")
    install_command: Optional[str] = None
    download_url: Optional[str] = None
    instructions: list[str] = Field(default_factory=list)
    post_install_check: str = "http://localhost:11434/api/version"


class OllamaModelPullRequest(BaseModel):
    """Request to pull (download) a model via Ollama."""
    model_name: str
    ollama_url: str = "http://localhost:11434"


class OllamaModelPullStatus(BaseModel):
    """Status update during model pull."""
    model_name: str
    status: str  # "downloading", "verifying", "complete", "error"
    progress_percent: Optional[float] = None
    downloaded_gb: Optional[float] = None
    total_gb: Optional[float] = None
    error: Optional[str] = None


class OllamaHealthResponse(BaseModel):
    """Health check response for an Ollama instance."""
    reachable: bool
    url: str
    version: Optional[str] = None
    models_installed: list[str] = Field(default_factory=list)
    model_details: list[dict[str, Any]] = Field(default_factory=list)
    gpu_available: bool = False
    error: Optional[str] = None


class AISetupWizardState(BaseModel):
    """Overall state for the AI setup wizard."""
    step: int = 1  # 1=detect, 2=recommend, 3=install, 4=test, 5=done
    device_id: str
    hardware: Optional[DeviceHardwareInfo] = None
    ollama_status: Optional[OllamaStatusReport] = None
    recommendations: Optional[ModelRecommendationsResponse] = None
    ai_config: Optional[DeviceAIConfigResponse] = None
    setup_completed: bool = False
    errors: list[str] = Field(default_factory=list)
