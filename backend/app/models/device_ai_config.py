"""
Device AI Configuration Model - Per-device AI routing and model preferences.

Each device can have its own AI configuration:
- Local Ollama (on the device itself)
- Remote Ollama (another machine on the network)
- Cloud API (OpenRouter, OpenAI, Anthropic)
- No AI (sync-only mode)

The backend routes AI requests to the correct provider based on the
requesting device's configuration, with automatic fallback.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Float, DateTime, ForeignKey, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin, TimestampMixin


class AISource:
    """AI source constants for device configuration."""
    LOCAL_OLLAMA = "local_ollama"       # Ollama running on this device
    REMOTE_OLLAMA = "remote_ollama"     # Ollama on another machine
    OPENROUTER = "openrouter"           # OpenRouter API (100+ models)
    OPENAI = "openai"                   # OpenAI API
    ANTHROPIC = "anthropic"             # Anthropic API
    NONE = "none"                       # No AI, sync-only

    ALL = [LOCAL_OLLAMA, REMOTE_OLLAMA, OPENROUTER, OPENAI, ANTHROPIC, NONE]


class DeviceAIConfig(Base, UUIDMixin, TimestampMixin):
    """
    Per-device AI configuration.

    Stores how each device should handle AI requests:
    which Ollama instance to use, which API keys, fallback behavior,
    and device hardware capabilities for model recommendations.
    """

    __tablename__ = "device_ai_configs"

    # Link to device
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Primary AI source ──────────────────────────────────────────────
    ai_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AISource.LOCAL_OLLAMA
    )

    # ── Ollama settings (local or remote) ──────────────────────────────
    ollama_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default="http://localhost:11434"
    )
    ollama_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="llama3.2"
    )
    ollama_embedding_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="nomic-embed-text"
    )

    # ── Cloud API settings ─────────────────────────────────────────────
    api_provider: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # "openrouter", "openai", "anthropic"
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Fernet-encrypted API key
    api_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "gpt-4o-mini", "claude-3-haiku"
    api_base_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Custom API base URL (e.g., OpenRouter)

    # ── Fallback configuration ─────────────────────────────────────────
    fallback_source: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # What to use if primary fails
    fallback_api_key_encrypted: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    fallback_api_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    auto_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )  # Auto-switch on failure?

    # ── Device hardware capabilities ───────────────────────────────────
    device_ram_gb: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    device_cpu_cores: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    device_gpu_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    device_gpu_vram_gb: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    device_free_disk_gb: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    device_os: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # ── Ollama status (updated periodically) ───────────────────────────
    ollama_installed: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    ollama_version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    ollama_models_installed: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON list of installed model names

    # ── Setup state ────────────────────────────────────────────────────
    setup_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_health_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # "healthy", "degraded", "offline"

    # ── Relationships ──────────────────────────────────────────────────
    device = relationship("Device", backref="ai_config", lazy="selectin", uselist=False)

    __table_args__ = (
        Index("ix_device_ai_configs_ai_source", "ai_source"),
    )

    def __repr__(self) -> str:
        return f"<DeviceAIConfig device={self.device_id} source={self.ai_source}>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses (excludes encrypted keys)."""
        import json as _json
        return {
            "id": self.id,
            "device_id": self.device_id,
            "ai_source": self.ai_source,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model,
            "ollama_embedding_model": self.ollama_embedding_model,
            "api_provider": self.api_provider,
            "api_model": self.api_model,
            "api_base_url": self.api_base_url,
            "has_api_key": bool(self.api_key_encrypted),
            "fallback_source": self.fallback_source,
            "fallback_api_model": self.fallback_api_model,
            "has_fallback_key": bool(self.fallback_api_key_encrypted),
            "auto_fallback": self.auto_fallback,
            "device_ram_gb": self.device_ram_gb,
            "device_cpu_cores": self.device_cpu_cores,
            "device_gpu_name": self.device_gpu_name,
            "device_gpu_vram_gb": self.device_gpu_vram_gb,
            "device_free_disk_gb": self.device_free_disk_gb,
            "device_os": self.device_os,
            "ollama_installed": self.ollama_installed,
            "ollama_version": self.ollama_version,
            "ollama_models_installed": (
                _json.loads(self.ollama_models_installed)
                if self.ollama_models_installed else []
            ),
            "setup_completed": self.setup_completed,
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
            "last_health_status": self.last_health_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
