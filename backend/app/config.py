"""
Configuration management for Aion Backend.
All settings are loaded from environment variables with sensible defaults.
"""

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
    app_version: str = "0.1.0"
    debug: bool = False
    
    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:1421", "http://localhost:8000", "http://127.0.0.1:8000", "tauri://localhost", "http://*"]
    
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
    
    # AI - Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"
    
    @property
    def ollama_url(self) -> str:
        """Construct Ollama API URL."""
        return f"http://{self.ollama_host}:{self.ollama_port}"
    
    # Security
    secret_key: str = "change-this-in-production-to-a-secure-random-key"
    access_token_expire_minutes: int = 30  # 30 minutes for access tokens
    refresh_token_expire_days: int = 7  # 7 days for refresh tokens
    
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
    
    # Security check: Fail if using default secret key in production
    if s.production and s.secret_key == "change-this-in-production-to-a-secure-random-key":
        raise ValueError(
            "SECURITY ERROR: You must set a secure SECRET_KEY environment variable in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    
    return s


# Export settings singleton
settings = get_settings()
