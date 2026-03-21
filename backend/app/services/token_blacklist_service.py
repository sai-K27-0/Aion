"""Redis-backed JWT token blacklist with in-memory fallback."""
import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)


class TokenBlacklistService:
    def __init__(self):
        self._redis = None
        self._memory_blacklist: Set[str] = set()
        self._initialized = False

    async def _get_redis(self):
        """Lazy-connect to Redis. Returns None if unavailable."""
        if self._initialized:
            return self._redis
        self._initialized = True
        try:
            import redis.asyncio as aioredis
            from app.config import settings
            self._redis = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
            await self._redis.ping()
            logger.info("Token blacklist using Redis")
        except Exception:
            logger.warning("Redis unavailable — token blacklist using in-memory fallback")
            self._redis = None
        return self._redis

    async def blacklist_token(self, jti: str, expires_in: int) -> None:
        """Blacklist a JWT by its JTI. Expires after `expires_in` seconds."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.set(f"token_blacklist:{jti}", "1", ex=expires_in)
                return
            except Exception:
                logger.warning("Redis SET failed — falling back to in-memory")
        self._memory_blacklist.add(jti)

    async def is_blacklisted(self, jti: str) -> bool:
        """Check if a JWT JTI is blacklisted."""
        redis = await self._get_redis()
        if redis:
            try:
                return await redis.exists(f"token_blacklist:{jti}") > 0
            except Exception:
                logger.warning("Redis EXISTS failed — checking in-memory")
        return jti in self._memory_blacklist


_service: Optional[TokenBlacklistService] = None


def get_token_blacklist_service() -> TokenBlacklistService:
    global _service
    if _service is None:
        _service = TokenBlacklistService()
    return _service
