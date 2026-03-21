"""
Configuration management for Aion Backend.
All settings are loaded from environment variables with sensible defaults.
"""

import warnings
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application
    app_name: str = "Aion"
    app_version: str = "0.4.3"
    debug: bool = False
    
    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost:1420",
        "http://localhost:1421",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "tauri://localhost",
        "https://tauri.localhost",
    ]
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database - PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "aion"
    postgres_password: str = "aion_local_secret"
    postgres_db: str = "aion"
    
    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """Construct sync PostgreSQL connection URL for migrations."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # Vector Database - Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "aion_embeddings"
    
    @property
    def qdrant_url(self) -> str:
        """Construct Qdrant connection URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    # AI - Ollama (default; used when no API key is set)
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"
    
    @property
    def ollama_url(self) -> str:
        """Construct Ollama API URL. Set OLLAMA_HOST/PORT for device-specific Ollama."""
        return f"http://{self.ollama_host}:{self.ollama_port}"
    
    # AI - Optional API keys (if set, used for chat instead of Ollama)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    # Preferred provider when multiple keys exist: ollama | openai | anthropic
    ai_provider: str = "ollama"

    # OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    oauth_redirect_base_url: str = "http://localhost:8000"

    # Optional cloud relay for cross-network sync
    relay_url: Optional[str] = None

    # Tunnel
    tunnel_domain: Optional[str] = None

    # Security
    secret_key: str = "change-this-in-production-to-a-secure-random-key"
    access_token_expire_minutes: int = 30  # 30 minutes for access tokens
    refresh_token_expire_days: int = 7  # 7 days for refresh tokens
    # Optional: set DATA_ENCRYPTION_KEY (e.g. from Fernet.generate_key()) to encrypt
    # sensitive fields at rest (e.g. block content, entry data)
    data_encryption_key: Optional[str] = None

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # Production mode
    production: bool = False
    require_https: bool = False
    
    # File Storage
    data_dir: str = "./data"
    max_file_size_mb: int = 100

    # AI Voice - ElevenLabs
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: str = "pNInz6obpguXKHuJmNLW"  # Default 'Adam' voice
    elevenlabs_model_id: str = "eleven_monolingual_v1"

    # AI Voice - Edge TTS (Free Alternative)
    edge_tts_voice: str = "en-US-AndrewNeural"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    s = Settings()
    
    # Security check: Fail in production, warn in dev
    if s.secret_key == "change-this-in-production-to-a-secure-random-key":
        if s.production:
            raise ValueError(
                "SECURITY ERROR: You must set a secure SECRET_KEY environment variable in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        else:
            warnings.warn(
                "WARNING: Using default secret key. Set SECRET_KEY env var for security. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
                UserWarning,
                stacklevel=2,
            )

    return s


# Export settings singleton
settings = get_settings()
