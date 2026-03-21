"""
AI Setup API Endpoints - Device AI configuration, Ollama management, and setup wizard.

Endpoints:
- Device AI config CRUD (per-device AI source, models, API keys)
- Ollama health check, install instructions, model pull
- Model recommendations based on hardware
- Setup wizard state management
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.schemas.device import (
    DeviceAIConfigCreate,
    DeviceAIConfigUpdate,
    DeviceAIConfigResponse,
    DeviceHardwareInfo,
    OllamaHealthResponse,
    OllamaInstallInstructions,
    OllamaModelPullRequest,
    ModelRecommendationsResponse,
    AISetupWizardState,
)
from app.services.ollama_setup_service import get_ollama_setup_service
from app.services.model_recommendation_service import get_recommendation_service
from app.models.device_ai_config import AISource

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Device AI Configuration
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/devices/{device_id}/ai-config", response_model=DeviceAIConfigResponse)
async def get_device_ai_config(device_id: str):
    """Get AI configuration for a specific device."""
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from sqlalchemy import select

    async for db in get_db():
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            # Return default config (not yet saved)
            return DeviceAIConfigResponse(
                id="",
                device_id=device_id,
                ai_source=AISource.LOCAL_OLLAMA,
                ollama_url="http://localhost:11434",
                ollama_model="llama3.2",
                ollama_embedding_model="nomic-embed-text",
                auto_fallback=True,
                setup_completed=False,
            )

        resp = config.to_dict()
        return DeviceAIConfigResponse(**resp)


@router.put("/devices/{device_id}/ai-config", response_model=DeviceAIConfigResponse)
async def set_device_ai_config(device_id: str, request: DeviceAIConfigCreate):
    """Create or update AI configuration for a device."""
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from app.models.device import Device
    from app.services.field_encryption import encrypt_str
    from sqlalchemy import select

    async for db in get_db():
        # Verify device exists
        device_result = await db.execute(
            select(Device).where(Device.id == device_id)
        )
        if not device_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Device not found")

        # Validate ai_source
        if request.ai_source not in AISource.ALL:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ai_source. Must be one of: {', '.join(AISource.ALL)}",
            )

        # Find existing or create new
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        if config is None:
            config = DeviceAIConfig(device_id=device_id)
            db.add(config)

        # Update fields
        config.ai_source = request.ai_source
        if request.ollama_url is not None:
            config.ollama_url = request.ollama_url
        if request.ollama_model is not None:
            config.ollama_model = request.ollama_model
        if request.ollama_embedding_model is not None:
            config.ollama_embedding_model = request.ollama_embedding_model
        if request.api_provider is not None:
            config.api_provider = request.api_provider
        if request.api_model is not None:
            config.api_model = request.api_model
        if request.api_base_url is not None:
            config.api_base_url = request.api_base_url
        if request.fallback_source is not None:
            config.fallback_source = request.fallback_source
        if request.fallback_api_model is not None:
            config.fallback_api_model = request.fallback_api_model
        config.auto_fallback = request.auto_fallback

        # Encrypt API keys before storing
        if request.api_key is not None:
            try:
                config.api_key_encrypted = encrypt_str(request.api_key)
            except Exception:
                config.api_key_encrypted = request.api_key  # Store plain if no key
        if request.fallback_api_key is not None:
            try:
                config.fallback_api_key_encrypted = encrypt_str(request.fallback_api_key)
            except Exception:
                config.fallback_api_key_encrypted = request.fallback_api_key

        # Update hardware info if provided
        if request.hardware:
            config.device_ram_gb = request.hardware.ram_gb
            config.device_cpu_cores = request.hardware.cpu_cores
            config.device_gpu_name = request.hardware.gpu_name
            config.device_gpu_vram_gb = request.hardware.gpu_vram_gb
            config.device_free_disk_gb = request.hardware.free_disk_gb
            config.device_os = request.hardware.os_name

        # Update Ollama status if provided
        if request.ollama_status:
            config.ollama_installed = request.ollama_status.installed
            config.ollama_version = request.ollama_status.version
            config.ollama_models_installed = json.dumps(request.ollama_status.models_installed)

        await db.commit()
        await db.refresh(config)

        return DeviceAIConfigResponse(**config.to_dict())


@router.patch("/devices/{device_id}/ai-config", response_model=DeviceAIConfigResponse)
async def update_device_ai_config(device_id: str, request: DeviceAIConfigUpdate):
    """Partially update AI configuration for a device."""
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from app.services.field_encryption import encrypt_str
    from sqlalchemy import select

    async for db in get_db():
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="AI config not found. Use PUT to create.")

        # Only update provided fields
        update_data = request.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "api_key" and value is not None:
                try:
                    config.api_key_encrypted = encrypt_str(value)
                except Exception:
                    config.api_key_encrypted = value
            elif field == "fallback_api_key" and value is not None:
                try:
                    config.fallback_api_key_encrypted = encrypt_str(value)
                except Exception:
                    config.fallback_api_key_encrypted = value
            elif field == "hardware" and value is not None:
                hw = DeviceHardwareInfo(**value) if isinstance(value, dict) else value
                config.device_ram_gb = hw.ram_gb
                config.device_cpu_cores = hw.cpu_cores
                config.device_gpu_name = hw.gpu_name
                config.device_gpu_vram_gb = hw.gpu_vram_gb
                config.device_free_disk_gb = hw.free_disk_gb
                config.device_os = hw.os_name
            elif field == "ollama_status" and value is not None:
                os_report = value if not isinstance(value, dict) else type('', (), value)()
                config.ollama_installed = getattr(os_report, 'installed', None)
                config.ollama_version = getattr(os_report, 'version', None)
                models = getattr(os_report, 'models_installed', [])
                config.ollama_models_installed = json.dumps(models)
            elif hasattr(config, field):
                setattr(config, field, value)

        await db.commit()
        await db.refresh(config)

        return DeviceAIConfigResponse(**config.to_dict())


# ═══════════════════════════════════════════════════════════════════════════
# Ollama Management
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/ollama/health", response_model=OllamaHealthResponse)
async def check_ollama_health(
    url: str = Query("http://localhost:11434", description="Ollama URL to check"),
):
    """Check if an Ollama instance is reachable and list its models."""
    service = get_ollama_setup_service()
    result = await service.check_health(url)
    return OllamaHealthResponse(**result)


@router.get("/ollama/install-instructions", response_model=OllamaInstallInstructions)
async def get_ollama_install_instructions(
    platform: str = Query(..., description="Platform: windows, macos, linux, android, ios"),
):
    """Get platform-specific Ollama installation instructions."""
    service = get_ollama_setup_service()
    result = service.get_install_instructions(platform)
    return OllamaInstallInstructions(**result)


@router.post("/ollama/pull")
async def pull_ollama_model(request: OllamaModelPullRequest):
    """
    Pull (download) an Ollama model. Returns a streaming response with progress.

    The response is a stream of JSON lines, each containing:
    - status: "downloading", "verifying", "installing", "complete", "error"
    - progress_percent: 0-100
    - downloaded_gb / total_gb
    """
    service = get_ollama_setup_service()

    # First verify Ollama is reachable
    health = await service.check_health(request.ollama_url)
    if not health["reachable"]:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Ollama at {request.ollama_url}. {health.get('error', '')}",
        )

    async def stream_progress():
        async for progress in service.pull_model_stream(
            request.model_name, request.ollama_url
        ):
            yield json.dumps(progress) + "\n"

    return StreamingResponse(
        stream_progress(),
        media_type="application/x-ndjson",
    )


@router.post("/ollama/verify")
async def verify_ollama_model(
    model_name: str = Query(..., description="Model name to verify"),
    ollama_url: str = Query("http://localhost:11434", description="Ollama URL"),
):
    """Verify a model works by sending a test prompt."""
    service = get_ollama_setup_service()
    result = await service.verify_model(model_name, ollama_url)
    return result


@router.post("/ollama/verify-embedding")
async def verify_embedding_model(
    model_name: str = Query(..., description="Embedding model name to verify"),
    ollama_url: str = Query("http://localhost:11434", description="Ollama URL"),
):
    """Verify an embedding model works by generating a test embedding."""
    service = get_ollama_setup_service()
    result = await service.verify_embedding_model(model_name, ollama_url)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Model Recommendations
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/recommendations", response_model=ModelRecommendationsResponse)
async def get_model_recommendations(hardware: DeviceHardwareInfo):
    """
    Get AI model recommendations based on device hardware.

    Send device specs (RAM, GPU, disk) and get back recommended models
    with download sizes, compatibility info, and alternatives.
    """
    service = get_recommendation_service()
    result = service.recommend_models(
        ram_gb=hardware.ram_gb,
        gpu_name=hardware.gpu_name,
        gpu_vram_gb=hardware.gpu_vram_gb,
        free_disk_gb=hardware.free_disk_gb,
    )
    return ModelRecommendationsResponse(**result)


@router.get("/recommendations/{device_id}", response_model=ModelRecommendationsResponse)
async def get_recommendations_for_device(device_id: str):
    """
    Get model recommendations using stored hardware info for a device.
    """
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from app.models.device import Device
    from sqlalchemy import select

    service = get_recommendation_service()

    async for db in get_db():
        # Try to get stored hardware info
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        # Also get device type
        dev_result = await db.execute(select(Device).where(Device.id == device_id))
        device = dev_result.scalar_one_or_none()

        if config and config.device_ram_gb:
            recs = service.recommend_models(
                ram_gb=config.device_ram_gb,
                gpu_name=config.device_gpu_name,
                gpu_vram_gb=config.device_gpu_vram_gb,
                free_disk_gb=config.device_free_disk_gb,
                device_type=device.device_type if device else None,
                platform=device.platform if device else None,
            )
        else:
            # No hardware info, give generic recommendations
            recs = service.recommend_models(
                device_type=device.device_type if device else None,
                platform=device.platform if device else None,
            )

        return ModelRecommendationsResponse(**recs)


# ═══════════════════════════════════════════════════════════════════════════
# Setup Wizard
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/setup/complete/{device_id}")
async def mark_setup_complete(device_id: str):
    """Mark AI setup as complete for a device."""
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from sqlalchemy import select
    from datetime import datetime, timezone

    async for db in get_db():
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="AI config not found")

        config.setup_completed = True
        config.last_health_check = datetime.now(timezone.utc)
        config.last_health_status = "healthy"

        await db.commit()
        return {"status": "ok", "message": "AI setup marked as complete"}


@router.get("/setup/status/{device_id}", response_model=AISetupWizardState)
async def get_setup_status(device_id: str):
    """Get the current AI setup wizard state for a device."""
    from app.db.session import get_db
    from app.models.device_ai_config import DeviceAIConfig
    from sqlalchemy import select

    async for db in get_db():
        result = await db.execute(
            select(DeviceAIConfig).where(DeviceAIConfig.device_id == device_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            return AISetupWizardState(step=1, device_id=device_id)

        # Determine step based on what's been configured
        step = 1
        if config.device_ram_gb is not None:
            step = 2  # Hardware detected
        if config.ollama_installed is not None:
            step = 3  # Ollama status known
        if config.ollama_models_installed and json.loads(config.ollama_models_installed):
            step = 4  # Models installed
        if config.setup_completed:
            step = 5  # Done

        return AISetupWizardState(
            step=step,
            device_id=device_id,
            hardware=DeviceHardwareInfo(
                ram_gb=config.device_ram_gb,
                cpu_cores=config.device_cpu_cores,
                gpu_name=config.device_gpu_name,
                gpu_vram_gb=config.device_gpu_vram_gb,
                free_disk_gb=config.device_free_disk_gb,
                os_name=config.device_os,
            ) if config.device_ram_gb else None,
            ai_config=DeviceAIConfigResponse(**config.to_dict()),
            setup_completed=config.setup_completed,
        )
