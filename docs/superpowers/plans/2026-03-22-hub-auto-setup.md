# Aion v0.5.0 — Hub Auto-Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a seamless first-time setup experience that auto-detects, installs, and configures the entire Aion backend via a wizard UI — without the user ever opening a terminal.

**Architecture:** Desktop app (Tauri) orchestrates Docker and Cloudflare processes via Rust commands. Backend (FastAPI) owns all security — auth, rate limiting, device approval. A JS state machine drives the wizard UI as a full-screen overlay. The Rust proxy pattern handles remote connectivity to avoid CSP issues.

**Tech Stack:** Rust (Tauri 2), JavaScript (Vite), Python 3.11 (FastAPI, SQLAlchemy 2 async, Redis), Docker Compose, Cloudflare Tunnel

**Spec:** `docs/superpowers/specs/2026-03-22-hub-auto-setup-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/app/models/system_settings.py` | SystemSettings singleton model (registration lock, setup state, tunnel config) |
| `backend/app/schemas/hub.py` | Pydantic schemas for hub status + registration endpoints |
| `backend/app/services/token_blacklist_service.py` | Redis-backed JWT token blacklist with in-memory fallback |
| `backend/app/utils/request.py` | Shared utility: `get_real_ip()` for rate limiting behind tunnel |
| `backend/app/api/v1/endpoints/hub.py` | Hub status and setup-complete endpoints |
| `backend/entrypoint.sh` | Docker entrypoint: run migrations, validate SECRET_KEY, start uvicorn |
| `backend/tests/test_hub.py` | Tests for hub endpoints, registration lock, token blacklist |
| `desktop/src-tauri/src/docker.rs` | Rust Tauri commands for Docker management |
| `desktop/src-tauri/src/cloudflare.rs` | Rust Tauri commands for Cloudflare tunnel |
| `desktop/src/services/hub_setup.js` | JS HubSetupService state machine |

### Modified Files

| File | What Changes |
|------|-------------|
| `backend/app/schemas/auth.py` | Make email explicitly `Optional` with default `None` in UserCreate |
| `backend/app/services/auth_service.py` | Use TokenBlacklistService, add registration lock check, first-user admin logic |
| `backend/app/services/device_service.py` | Full async rewrite using Device DB model |
| `backend/app/api/v1/endpoints/auth.py` | Add rate limiting, registration lock check, registration-status endpoint |
| `backend/app/api/v1/router.py` | Register hub router |
| `backend/app/main.py` | Dynamic CORS for tunnel domain, rate limiter key function for CF-Connecting-IP |
| `backend/app/config.py` | Add `tunnel_domain`, `redis_url` properties |
| `backend/docker-compose.yml` | Add health checks on backend + Qdrant containers |
| `backend/Dockerfile` | Use entrypoint.sh |
| `desktop/src-tauri/src/main.rs` | Register new commands from docker.rs, cloudflare.rs modules; add proxy_request command |
| `desktop/src-tauri/Cargo.toml` | Add module declarations |
| `desktop/index.html` | Add #hub-wizard overlay section |
| `desktop/src/main.js` | Add startup detection flow, wizard rendering |
| `desktop/src/styles/overlay.css` | Wizard step styles |

---

## Phase 1: Backend — Models, Schemas, Services

### Task 1: SystemSettings Model

**Files:**
- Create: `backend/app/models/system_settings.py`
- Modify: `backend/app/db/base.py` (import new model so Alembic sees it)
- Test: `backend/tests/test_hub.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/test_hub.py`:

```python
"""Tests for hub setup, registration lock, and token blacklist."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_settings import SystemSettings


class TestSystemSettings:
    @pytest.mark.asyncio
    async def test_create_default_settings(self, db_session: AsyncSession):
        settings = SystemSettings()
        db_session.add(settings)
        await db_session.commit()
        await db_session.refresh(settings)

        assert settings.id is not None
        assert settings.registration_locked is True
        assert settings.setup_complete is False
        assert settings.tunnel_domain is None
        assert settings.tunnel_type is None

    @pytest.mark.asyncio
    async def test_update_tunnel_config(self, db_session: AsyncSession):
        settings = SystemSettings()
        db_session.add(settings)
        await db_session.commit()

        settings.tunnel_domain = "aion.example.com"
        settings.tunnel_type = "permanent"
        await db_session.commit()
        await db_session.refresh(settings)

        assert settings.tunnel_domain == "aion.example.com"
        assert settings.tunnel_type == "permanent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_hub.py::TestSystemSettings -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.system_settings'`

- [ ] **Step 3: Implement SystemSettings model**

Create `backend/app/models/system_settings.py`:

```python
"""System-wide settings for the Aion hub (singleton row pattern)."""
from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class SystemSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    registration_locked: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    setup_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    tunnel_domain: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    tunnel_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )  # "quick" | "permanent" | None
```

Add the import in **two places**:

1. `backend/tests/conftest.py` — alongside the existing model imports (so tests can create the table in SQLite):
   ```python
   from app.models.system_settings import SystemSettings  # noqa: F401
   ```

2. `backend/app/models/__init__.py` or wherever Alembic's `env.py` imports models from — so `alembic revision --autogenerate` detects the new table. Check `backend/alembic/env.py` for the `target_metadata` source and ensure `SystemSettings` is reachable from that import chain.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_hub.py::TestSystemSettings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/system_settings.py backend/tests/test_hub.py
git commit -m "feat: add SystemSettings model for hub configuration"
```

---

### Task 2: Hub Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/hub.py`

- [ ] **Step 1: Create hub schemas**

Create `backend/app/schemas/hub.py`:

```python
"""Schemas for hub status and configuration endpoints."""
from typing import Optional

from pydantic import BaseModel


class HubStatusPublicResponse(BaseModel):
    """Returned to unauthenticated callers — minimal info only."""
    setup_complete: bool
    registration_open: bool


class HubStatusAdminResponse(HubStatusPublicResponse):
    """Returned to authenticated admin — includes operational details."""
    user_count: int
    tunnel_active: bool
    version: str


class RegistrationStatusResponse(BaseModel):
    open: bool


class RegistrationLockRequest(BaseModel):
    locked: bool


class TunnelConfigRequest(BaseModel):
    domain: str
    tunnel_type: str  # "quick" | "permanent"


class TunnelConfigResponse(BaseModel):
    domain: Optional[str]
    tunnel_type: Optional[str]
    active: bool
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/hub.py
git commit -m "feat: add Pydantic schemas for hub endpoints"
```

---

### Task 3: Token Blacklist Service

**Files:**
- Create: `backend/app/services/token_blacklist_service.py`
- Test: `backend/tests/test_hub.py` (append)

- [ ] **Step 1: Write the tests**

Append to `backend/tests/test_hub.py`:

```python
class TestTokenBlacklistService:
    @pytest.mark.asyncio
    async def test_blacklist_and_check(self):
        from app.services.token_blacklist_service import TokenBlacklistService

        service = TokenBlacklistService()
        # Falls back to in-memory since Redis isn't running in tests
        await service.blacklist_token("test-jti-123", expires_in=3600)
        assert await service.is_blacklisted("test-jti-123") is True

    @pytest.mark.asyncio
    async def test_not_blacklisted(self):
        from app.services.token_blacklist_service import TokenBlacklistService

        service = TokenBlacklistService()
        assert await service.is_blacklisted("unknown-jti") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_hub.py::TestTokenBlacklistService -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/token_blacklist_service.py`:

```python
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
```

- [ ] **Step 4: Add `redis_url` property to config**

In `backend/app/config.py`, add to the `Settings` class:

```python
    redis_host: str = "localhost"
    redis_port: int = 6379
```

And add a property:

```python
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hub.py::TestTokenBlacklistService -v`
Expected: PASS (in-memory fallback used since no Redis in tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/token_blacklist_service.py backend/app/config.py backend/tests/test_hub.py
git commit -m "feat: add Redis-backed token blacklist service with in-memory fallback"
```

---

### Task 4: Auth Service — Registration Lock + First-User Admin

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_hub.py` (append)

- [ ] **Step 1: Write the tests**

**Important:** The existing `AuthService` takes `db: AsyncSession` in its constructor (`AuthService(db=session)`) and has a `create_user(data: UserCreate)` method. We will add a new standalone function `register_user_with_lock()` that wraps the existing `create_user` with registration lock logic. This avoids modifying the existing `AuthService` constructor pattern.

Append to `backend/tests/test_hub.py`:

```python
from app.models.user import User
from app.schemas.auth import UserCreate


class TestRegistrationLock:
    @pytest.mark.asyncio
    async def test_first_user_becomes_superuser(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        user = await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )
        assert user.is_superuser is True
        assert user.username == "admin"

    @pytest.mark.asyncio
    async def test_auto_creates_settings_after_first_user(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )
        # SystemSettings should have been auto-created with registration locked
        result = await db_session.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()
        assert settings is not None
        assert settings.registration_locked is True

    @pytest.mark.asyncio
    async def test_registration_locked_after_first_user(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        # Create first user (auto-locks registration)
        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )

        # Second registration should fail
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await register_user_with_lock(
                db=db_session,
                data=UserCreate(username="user2", password="securepass123"),
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_registration_allowed_when_unlocked(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        # Create first user
        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )

        # Explicitly unlock
        result = await db_session.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one()
        settings.registration_locked = False
        await db_session.commit()

        # Second user should succeed
        user2 = await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="user2", password="securepass123"),
        )
        assert user2.is_superuser is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hub.py::TestRegistrationLock -v`
Expected: FAIL — `register_user_with_lock` doesn't exist yet

- [ ] **Step 3: Update UserCreate schema — make email optional**

In `backend/app/schemas/auth.py`, verify `email` field in `UserCreate` has `Optional[EmailStr] = None`. It already does per exploration — confirm and ensure no validator requires it.

- [ ] **Step 4: Add `register_user_with_lock` function to auth_service.py**

Add a new standalone async function at the bottom of `backend/app/services/auth_service.py`:

```python
from sqlalchemy import func, select
from app.models.system_settings import SystemSettings
from app.schemas.auth import UserCreate

async def register_user_with_lock(db: AsyncSession, data: UserCreate) -> User:
    """Register a user with registration lock enforcement.
    First user becomes admin and auto-locks registration."""
    from fastapi import HTTPException

    # Count existing users
    user_count = await db.scalar(select(func.count(User.id)))

    if user_count > 0:
        # Check registration lock
        result = await db.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()
        if settings is None or settings.registration_locked:
            raise HTTPException(status_code=403, detail="Registration is locked")

    # Create the user via existing AuthService
    auth = AuthService(db=db)
    user = await auth.create_user(data)

    # First user gets admin
    if user_count == 0:
        user.is_superuser = True
        await db.commit()
        await db.refresh(user)

        # Auto-create SystemSettings with registration locked
        settings = SystemSettings(registration_locked=True)
        db.add(settings)
        await db.commit()

    return user
```

This wraps the existing `AuthService.create_user()` without modifying its interface.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hub.py::TestRegistrationLock -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/auth_service.py backend/app/schemas/auth.py backend/tests/test_hub.py
git commit -m "feat: add registration lock and first-user admin logic to auth service"
```

---

### Task 5: Hub Endpoints

**Files:**
- Create: `backend/app/api/v1/endpoints/hub.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_hub.py` (append)

- [ ] **Step 1: Write the tests**

Append to `backend/tests/test_hub.py`:

```python
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


class TestHubEndpoints:
    @pytest.mark.asyncio
    async def test_hub_status_public_no_setup(self, db_session: AsyncSession):
        """When no SystemSettings exists, setup_complete=False, registration_open=True."""
        from app.api.v1.endpoints.hub import _get_hub_status_public
        result = await _get_hub_status_public(db_session)
        assert result.setup_complete is False
        assert result.registration_open is True

    @pytest.mark.asyncio
    async def test_hub_status_public_after_setup(self, db_session: AsyncSession):
        """After setup, reflects actual state."""
        from app.api.v1.endpoints.hub import _get_hub_status_public
        settings = SystemSettings(setup_complete=True, registration_locked=True)
        db_session.add(settings)
        await db_session.commit()

        result = await _get_hub_status_public(db_session)
        assert result.setup_complete is True
        assert result.registration_open is False

    @pytest.mark.asyncio
    async def test_registration_status(self, db_session: AsyncSession):
        """Registration is open when no users exist."""
        from app.api.v1.endpoints.hub import _get_registration_status
        result = await _get_registration_status(db_session)
        assert result.open is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hub.py::TestHubEndpoints -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement hub endpoints**

Create `backend/app/api/v1/endpoints/hub.py`:

```python
"""Hub status and configuration endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.hub import (
    HubStatusPublicResponse,
    HubStatusAdminResponse,
    RegistrationStatusResponse,
    TunnelConfigRequest,
    TunnelConfigResponse,
)

router = APIRouter()

VERSION = "0.5.0"


async def _get_or_create_settings(db: AsyncSession) -> SystemSettings:
    """Get the singleton SystemSettings row, creating it if absent."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def _require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Dependency that requires a valid admin JWT. Returns the admin user.
    Reuse the existing auth dependency pattern from auth.py (get_current_user),
    then check is_superuser."""
    # Import the existing auth dependency
    from app.api.v1.endpoints.auth import get_current_user
    user = await get_current_user(request, db)
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _get_hub_status_public(db: AsyncSession) -> HubStatusPublicResponse:
    """Build public hub status (no sensitive info)."""
    settings_result = await db.execute(select(SystemSettings).limit(1))
    settings = settings_result.scalar_one_or_none()

    if settings is None:
        return HubStatusPublicResponse(setup_complete=False, registration_open=True)

    return HubStatusPublicResponse(
        setup_complete=settings.setup_complete,
        registration_open=not settings.registration_locked,
    )


async def _get_registration_status(db: AsyncSession) -> RegistrationStatusResponse:
    """Check if registration is open."""
    user_count = await db.scalar(select(func.count(User.id)))
    if user_count == 0:
        return RegistrationStatusResponse(open=True)

    settings_result = await db.execute(select(SystemSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    if settings is None:
        return RegistrationStatusResponse(open=False)

    return RegistrationStatusResponse(open=not settings.registration_locked)


@router.get("/status")
async def hub_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Hub status. Returns minimal info for unauthenticated callers.
    Returns full info (user_count, tunnel_active, version) for authenticated admins."""
    # Try to get authenticated admin — if fails, return public response
    try:
        admin = await _require_admin(request, db)
        settings = await _get_or_create_settings(db)
        user_count = await db.scalar(select(func.count(User.id)))
        return HubStatusAdminResponse(
            setup_complete=settings.setup_complete,
            registration_open=not settings.registration_locked,
            user_count=user_count,
            tunnel_active=settings.tunnel_domain is not None,
            version=VERSION,
        )
    except HTTPException:
        return await _get_hub_status_public(db)


@router.get("/registration-status", response_model=RegistrationStatusResponse)
async def registration_status(db: AsyncSession = Depends(get_db)):
    """Check if registration is currently open."""
    return await _get_registration_status(db)


@router.post("/setup-complete")
async def mark_setup_complete(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark hub setup as complete. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.setup_complete = True
    await db.commit()
    return {"ok": True}


@router.post("/registration-lock")
async def lock_registration(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lock registration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.registration_locked = True
    await db.commit()
    return {"locked": True}


@router.post("/registration-unlock")
async def unlock_registration(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Unlock registration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.registration_locked = False
    await db.commit()
    return {"locked": False}


@router.post("/tunnel-config", response_model=TunnelConfigResponse)
async def update_tunnel_config(
    config: TunnelConfigRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update tunnel configuration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.tunnel_domain = config.domain
    settings.tunnel_type = config.tunnel_type
    await db.commit()
    return TunnelConfigResponse(
        domain=settings.tunnel_domain,
        tunnel_type=settings.tunnel_type,
        active=settings.tunnel_domain is not None,
    )
```

**Note:** The `_require_admin` dependency reuses the existing `get_current_user` function from `auth.py`. Check how it's implemented — it likely extracts the JWT from the `Authorization` header and queries the user. If `get_current_user` doesn't exist as a standalone function, extract the auth logic from the login-required endpoints into a reusable dependency.

- [ ] **Step 4: Register hub router**

In `backend/app/api/v1/router.py`, add:

```python
from app.api.v1.endpoints import hub

api_router.include_router(
    hub.router,
    prefix="/hub",
    tags=["hub"],
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hub.py::TestHubEndpoints -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/hub.py backend/app/api/v1/router.py backend/tests/test_hub.py
git commit -m "feat: add hub status, registration lock, and tunnel config endpoints"
```

---

### Task 6: Rate Limiter — Real IP Behind Tunnel

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create shared utility for real IP extraction**

Create `backend/app/utils/request.py` (to avoid circular imports if auth.py needs it):

```python
"""Shared request utilities."""
from starlette.requests import Request


def get_real_ip(request: Request) -> str:
    """Extract real client IP, handling Cloudflare tunnel headers."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

Create `backend/app/utils/__init__.py` (empty file).

In `backend/app/main.py`, import from the utility:

```python
from app.utils.request import get_real_ip
```

Update the limiter initialization to use this function:

```python
limiter = Limiter(key_func=get_real_ip)
```

- [ ] **Step 2: Add dynamic CORS for tunnel domain**

In `backend/app/main.py`, in the CORS setup section, add after the existing origins list:

```python
from app.config import settings

# Add tunnel domain to CORS if configured
if hasattr(settings, 'tunnel_domain') and settings.tunnel_domain:
    origins.append(f"https://{settings.tunnel_domain}")
```

- [ ] **Step 3: Add `tunnel_domain` to config**

In `backend/app/config.py`, add to the `Settings` class:

```python
    tunnel_domain: Optional[str] = None
```

Add `from typing import Optional` import if not present.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/config.py
git commit -m "feat: add real-IP rate limiting for tunnel + dynamic CORS"
```

---

### Task 7: Device Service Async Rewrite

**Files:**
- Modify: `backend/app/services/device_service.py`
- Test: `backend/tests/test_hub.py` (append)

- [ ] **Step 1: Write the tests**

Append to `backend/tests/test_hub.py`:

```python
from app.models.device import Device, ApprovalStatus


class TestDeviceServiceDB:
    @pytest.mark.asyncio
    async def test_register_first_device_auto_approved(self, db_session: AsyncSession):
        """First device for a user should be auto-approved."""
        # Create a user first
        user = User(
            id="test-user-id",
            username="testuser",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        from app.services.device_service import get_device_service
        service = get_device_service()
        result = await service.register_device(
            db=db_session,
            device_id="device-001",
            device_name="My PC",
            device_type="desktop",
            platform="windows",
            user_id="test-user-id",
        )
        assert result["approval_status"] == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_register_second_device_pending(self, db_session: AsyncSession):
        """Second device should be pending approval."""
        user = User(
            id="test-user-id",
            username="testuser",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        # Add first device as already approved
        first_device = Device(
            id="device-001",
            device_name="First PC",
            device_type="desktop",
            platform="windows",
            user_id="test-user-id",
            approval_status=ApprovalStatus.APPROVED,
        )
        db_session.add(first_device)
        await db_session.commit()

        from app.services.device_service import get_device_service
        service = get_device_service()
        result = await service.register_device(
            db=db_session,
            device_id="device-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="test-user-id",
        )
        assert result["approval_status"] == ApprovalStatus.PENDING
        assert result.get("approval_code") is not None
        assert len(result["approval_code"]) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hub.py::TestDeviceServiceDB -v`
Expected: FAIL — current DeviceService doesn't accept `db` parameter

- [ ] **Step 3: Rewrite device_service.py**

Replace `backend/app/services/device_service.py` with an async, DB-backed implementation:

```python
"""Device registration and management service (DB-backed)."""
import secrets
import string
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, ApprovalStatus

logger = logging.getLogger(__name__)

# Characters for approval code (no ambiguous chars)
_CODE_CHARS = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in "0OI1L"
)


def _generate_approval_code() -> str:
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(6))


class DeviceService:
    async def register_device(
        self,
        db: AsyncSession,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: str,
        app_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a device. First device auto-approved; subsequent need approval."""
        # Check if device already exists
        existing = await db.get(Device, device_id)
        if existing:
            return {
                "device": existing,
                "approval_status": existing.approval_status,
                "message": "Device already registered",
            }

        # Check if this is the first device for the user
        count = await db.scalar(
            select(func.count(Device.id)).where(
                Device.user_id == user_id,
                Device.is_active == True,
                Device.approval_status == ApprovalStatus.APPROVED,
            )
        )
        is_first = count == 0

        device = Device(
            id=device_id,
            device_name=device_name,
            device_type=device_type,
            platform=platform,
            user_id=user_id,
            app_version=app_version,
            approval_status=ApprovalStatus.APPROVED if is_first else ApprovalStatus.PENDING,
            approval_code=None if is_first else _generate_approval_code(),
            approved_at=datetime.now(timezone.utc) if is_first else None,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)

        result = {
            "device": device,
            "approval_status": device.approval_status,
        }
        if device.approval_code:
            result["approval_code"] = device.approval_code
        if is_first:
            result["message"] = "First device — auto-approved"
        else:
            result["message"] = "Pending approval. Share the code with an approved device."

        return result

    async def approve_device(
        self, db: AsyncSession, device_id: str, code: str, approver_device_id: str
    ) -> Dict[str, Any]:
        """Approve a pending device using its 6-digit code."""
        device = await db.get(Device, device_id)
        if not device:
            raise ValueError("Device not found")
        if device.approval_status != ApprovalStatus.PENDING:
            raise ValueError(f"Device is already {device.approval_status}")
        if device.approval_code != code.upper():
            raise ValueError("Invalid approval code")

        device.approval_status = ApprovalStatus.APPROVED
        device.approved_at = datetime.now(timezone.utc)
        device.approved_by_device_id = approver_device_id
        device.approval_code = None
        await db.commit()

        return {"device": device, "approval_status": ApprovalStatus.APPROVED}

    async def get_device(self, db: AsyncSession, device_id: str) -> Optional[Device]:
        return await db.get(Device, device_id)

    async def list_devices(self, db: AsyncSession, user_id: str) -> List[Device]:
        result = await db.execute(
            select(Device).where(Device.user_id == user_id, Device.is_active == True)
        )
        return list(result.scalars().all())


_service: Optional[DeviceService] = None


def get_device_service() -> DeviceService:
    global _service
    if _service is None:
        _service = DeviceService()
    return _service
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hub.py::TestDeviceServiceDB -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/device_service.py backend/tests/test_hub.py
git commit -m "feat: rewrite device service with async DB-backed implementation"
```

---

### Task 8: Auth Endpoint — Rate Limiting + Registration Status

**Files:**
- Modify: `backend/app/api/v1/endpoints/auth.py`

- [ ] **Step 1: Add rate limiting to auth endpoints**

In `backend/app/api/v1/endpoints/auth.py`, add rate limiting decorators to login and register:

```python
from slowapi import Limiter
from app.utils.request import get_real_ip

limiter = Limiter(key_func=get_real_ip)

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...

@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, ...):
    ...
```

Note: Check how `slowapi` is already configured in `main.py`. The limiter may already be attached to the app. If so, use `request.app.state.limiter` or import the existing limiter instance.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/v1/endpoints/auth.py
git commit -m "feat: add rate limiting to auth endpoints (10/min login, 5/min register)"
```

---

### Task 9: Docker Entrypoint + Compose Updates

**Files:**
- Create: `backend/entrypoint.sh`
- Modify: `backend/Dockerfile`
- Modify: `backend/docker-compose.yml`

- [ ] **Step 1: Create entrypoint.sh**

Create `backend/entrypoint.sh`:

```bash
#!/bin/bash
set -e

echo "=== Aion Backend Startup ==="

# Validate SECRET_KEY
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "change-this-in-production" ]; then
    echo "ERROR: SECRET_KEY is not set or is using the default value."
    echo "The desktop app should generate and pass SECRET_KEY as an environment variable."
    exit 1
fi

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
while ! pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-aion}" -q 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

# Run database migrations
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

# Start the server
echo "Starting Aion backend on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Update Dockerfile to use entrypoint**

In `backend/Dockerfile`, find the `CMD` line and replace with:

```dockerfile
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

Remove any existing `CMD` line that starts uvicorn directly.

- [ ] **Step 3: Add health checks to docker-compose.yml**

In `backend/docker-compose.yml`, add health check to the `api` service:

```yaml
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

Add health check to the `qdrant` service:

```yaml
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Update `api` service to depend on qdrant health:

```yaml
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
```

- [ ] **Step 4: Commit**

```bash
git add backend/entrypoint.sh backend/Dockerfile backend/docker-compose.yml
git commit -m "feat: add Docker entrypoint with migration + health checks"
```

---

## Phase 2: Rust Commands

### Task 10: Docker Management Module

**Files:**
- Create: `desktop/src-tauri/src/docker.rs`
- Modify: `desktop/src-tauri/src/main.rs`

- [ ] **Step 1: Create docker.rs**

Create `desktop/src-tauri/src/docker.rs`:

```rust
use serde_json::{json, Value as JsonValue};
use std::process::Command;

#[tauri::command]
pub fn check_docker_installed() -> Result<JsonValue, String> {
    let version_output = Command::new("docker")
        .arg("--version")
        .output();

    let (installed, version) = match version_output {
        Ok(output) if output.status.success() => {
            (true, String::from_utf8_lossy(&output.stdout).trim().to_string())
        }
        _ => (false, String::new()),
    };

    let compose_installed = Command::new("docker")
        .args(["compose", "version"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    Ok(json!({
        "installed": installed && compose_installed,
        "version": version,
    }))
}

#[tauri::command]
pub fn check_docker_running() -> Result<JsonValue, String> {
    let running = Command::new("docker")
        .arg("info")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    Ok(json!({ "running": running }))
}

#[cfg(target_os = "windows")]
#[tauri::command]
pub fn install_docker() -> Result<JsonValue, String> {
    use std::env;
    use std::path::PathBuf;

    let temp_dir = env::temp_dir();
    let installer_path = temp_dir.join("DockerDesktopInstaller.exe");
    let url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe";

    // Download installer
    let download = Command::new("powershell")
        .args([
            "-Command",
            &format!(
                "Invoke-WebRequest -Uri '{}' -OutFile '{}'",
                url,
                installer_path.display()
            ),
        ])
        .output()
        .map_err(|e| format!("Download failed: {}", e))?;

    if !download.status.success() {
        return Ok(json!({
            "success": false,
            "error": String::from_utf8_lossy(&download.stderr).to_string(),
        }));
    }

    // Run installer with admin elevation
    let install = Command::new("powershell")
        .args([
            "-Command",
            &format!(
                "Start-Process '{}' -ArgumentList 'install','--quiet','--accept-license' -Verb RunAs -Wait",
                installer_path.display()
            ),
        ])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    let success = install.status.success();
    let error_msg = if success { None } else {
        Some(String::from_utf8_lossy(&install.stderr).to_string())
    };

    Ok(json!({
        "success": success,
        "error": error_msg,
    }))
}

#[cfg(not(target_os = "windows"))]
#[tauri::command]
pub fn install_docker() -> Result<JsonValue, String> {
    Ok(json!({
        "success": false,
        "error": "Auto-install is only supported on Windows. Please install Docker Desktop manually.",
    }))
}

#[tauri::command]
pub fn start_docker_compose(compose_path: String, env_vars: Option<std::collections::HashMap<String, String>>) -> Result<JsonValue, String> {
    let mut cmd = Command::new("docker");
    cmd.args(["compose", "-f", &compose_path, "up", "-d"]);

    if let Some(vars) = env_vars {
        for (key, value) in vars {
            cmd.env(key, value);
        }
    }

    let output = cmd.output().map_err(|e| format!("Failed to start: {}", e))?;
    let success = output.status.success();
    let error_msg = if success { None } else {
        Some(String::from_utf8_lossy(&output.stderr).to_string())
    };

    Ok(json!({
        "success": success,
        "error": error_msg,
    }))
}

#[tauri::command]
pub fn stop_docker_compose(compose_path: String) -> Result<JsonValue, String> {
    let output = Command::new("docker")
        .args(["compose", "-f", &compose_path, "down"])
        .output()
        .map_err(|e| format!("Failed to stop: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[tauri::command]
pub fn get_docker_compose_status(compose_path: String) -> Result<JsonValue, String> {
    let output = Command::new("docker")
        .args(["compose", "-f", &compose_path, "ps", "--format", "json"])
        .output()
        .map_err(|e| format!("Failed to get status: {}", e))?;

    if !output.status.success() {
        return Ok(json!({ "containers": [] }));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    // docker compose ps --format json outputs one JSON object per line
    let containers: Vec<JsonValue> = stdout
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect();

    Ok(json!({ "containers": containers }))
}

#[tauri::command]
pub async fn check_backend_health(url: Option<String>) -> Result<JsonValue, String> {
    let health_url = url.unwrap_or_else(|| "http://localhost:8000/health".to_string());

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    match client.get(&health_url).send().await {
        Ok(resp) if resp.status().is_success() => {
            let body: JsonValue = resp.json().await.unwrap_or(json!({}));
            Ok(json!({
                "healthy": true,
                "version": body.get("version").and_then(|v| v.as_str()).unwrap_or("unknown"),
            }))
        }
        Ok(resp) => Ok(json!({
            "healthy": false,
            "error": format!("HTTP {}", resp.status()),
        })),
        Err(e) => Ok(json!({
            "healthy": false,
            "error": e.to_string(),
        })),
    }
}
```

- [ ] **Step 2: Register docker commands in main.rs**

In `desktop/src-tauri/src/main.rs`:

1. Add at top: `mod docker;`
2. In the `invoke_handler` macro, add:
   ```rust
   docker::check_docker_installed,
   docker::check_docker_running,
   docker::install_docker,
   docker::start_docker_compose,
   docker::stop_docker_compose,
   docker::get_docker_compose_status,
   docker::check_backend_health,
   ```

- [ ] **Step 3: Verify compilation**

Run: `cd desktop && npm run tauri:dev` (or `cd desktop/src-tauri && cargo check`)
Expected: Compiles without errors

- [ ] **Step 4: Commit**

```bash
git add desktop/src-tauri/src/docker.rs desktop/src-tauri/src/main.rs
git commit -m "feat: add Rust Docker management commands"
```

---

### Task 11: Cloudflare Module

**Files:**
- Create: `desktop/src-tauri/src/cloudflare.rs`
- Modify: `desktop/src-tauri/src/main.rs`

- [ ] **Step 1: Create cloudflare.rs**

Create `desktop/src-tauri/src/cloudflare.rs`:

```rust
use serde_json::{json, Value as JsonValue};
use std::process::Command;

#[tauri::command]
pub fn check_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("cloudflared")
        .arg("--version")
        .output();

    match output {
        Ok(o) if o.status.success() => {
            let version = String::from_utf8_lossy(&o.stdout).trim().to_string();
            Ok(json!({ "installed": true, "version": version }))
        }
        _ => Ok(json!({ "installed": false, "version": "" })),
    }
}

#[cfg(target_os = "windows")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    use std::env;

    let temp_dir = env::temp_dir();
    let installer_path = temp_dir.join("cloudflared-windows-amd64.msi");
    let url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi";

    let download = Command::new("powershell")
        .args([
            "-Command",
            &format!(
                "Invoke-WebRequest -Uri '{}' -OutFile '{}'",
                url,
                installer_path.display()
            ),
        ])
        .output()
        .map_err(|e| format!("Download failed: {}", e))?;

    if !download.status.success() {
        return Ok(json!({
            "success": false,
            "error": String::from_utf8_lossy(&download.stderr).to_string(),
        }));
    }

    let install = Command::new("msiexec")
        .args(["/i", &installer_path.display().to_string(), "/quiet"])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    Ok(json!({ "success": install.status.success() }))
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("brew")
        .args(["install", "cloudflared"])
        .output()
        .map_err(|e| format!("brew install failed: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[cfg(target_os = "linux")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("bash")
        .args(["-c", "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && sudo apt-get update && sudo apt-get install -y cloudflared"])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[tauri::command]
pub async fn start_quick_tunnel(port: u16) -> Result<JsonValue, String> {
    use tokio::process::Command as AsyncCommand;
    use tokio::io::{AsyncBufReadExt, BufReader};

    let mut child = AsyncCommand::new("cloudflared")
        .args(["tunnel", "--url", &format!("http://localhost:{}", port)])
        .stderr(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start tunnel: {}", e))?;

    let stderr = child.stderr.take().ok_or("No stderr")?;
    let mut reader = BufReader::new(stderr).lines();

    // Parse the tunnel URL from cloudflared's stderr output
    let timeout = tokio::time::timeout(
        std::time::Duration::from_secs(30),
        async {
            while let Ok(Some(line)) = reader.next_line().await {
                // cloudflared prints the URL like: "... https://xxx.trycloudflare.com ..."
                if let Some(url_start) = line.find("https://") {
                    let url_part = &line[url_start..];
                    if let Some(url_end) = url_part.find(|c: char| c.is_whitespace() || c == '|') {
                        let url = &url_part[..url_end];
                        if url.contains("trycloudflare.com") {
                            return Ok::<String, String>(url.to_string());
                        }
                    } else if url_part.contains("trycloudflare.com") {
                        return Ok(url_part.trim().to_string());
                    }
                }
            }
            Err("Could not find tunnel URL in output".to_string())
        }
    ).await;

    match timeout {
        Ok(Ok(url)) => Ok(json!({ "url": url, "pid": child.id() })),
        Ok(Err(e)) => Err(e),
        Err(_) => Err("Tunnel startup timed out after 30 seconds".to_string()),
    }
}
```

- [ ] **Step 2: Register cloudflare commands in main.rs**

In `desktop/src-tauri/src/main.rs`:

1. Add: `mod cloudflare;`
2. In `invoke_handler`, add:
   ```rust
   cloudflare::check_cloudflared,
   cloudflare::install_cloudflared,
   cloudflare::start_quick_tunnel,
   ```

- [ ] **Step 3: Add proxy_request command in main.rs**

Add directly in `main.rs` (generic utility, not module-specific):

```rust
#[tauri::command]
async fn proxy_request(
    url: String,
    method: String,
    body: Option<String>,
    headers: Option<std::collections::HashMap<String, String>>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;

    let mut req = match method.to_uppercase().as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        "PATCH" => client.patch(&url),
        _ => return Err(format!("Unsupported method: {}", method)),
    };

    if let Some(hdrs) = headers {
        for (key, value) in hdrs {
            req = req.header(&key, &value);
        }
    }

    if let Some(b) = body {
        req = req.header("Content-Type", "application/json").body(b);
    }

    let resp = req.send().await.map_err(|e| e.to_string())?;
    let status = resp.status().as_u16();
    let resp_body: String = resp.text().await.map_err(|e| e.to_string())?;

    Ok(serde_json::json!({
        "status": status,
        "body": resp_body,
    }))
}
```

Register `proxy_request` in `invoke_handler`.

- [ ] **Step 4: Add tokio dependency if needed**

Check `desktop/src-tauri/Cargo.toml` — `tokio` should already be a dependency via Tauri. If `tokio::process` or `tokio::io` aren't available, add:

```toml
tokio = { version = "1", features = ["process", "io-util", "time"] }
```

- [ ] **Step 5: Verify compilation**

Run: `cd desktop/src-tauri && cargo check`
Expected: Compiles without errors

- [ ] **Step 6: Commit**

```bash
git add desktop/src-tauri/src/cloudflare.rs desktop/src-tauri/src/main.rs desktop/src-tauri/Cargo.toml
git commit -m "feat: add Cloudflare tunnel commands and proxy_request"
```

---

## Phase 3: JS Orchestration + Wizard UI

### Task 12: HubSetupService

**Files:**
- Create: `desktop/src/services/hub_setup.js`

- [ ] **Step 1: Create hub_setup.js**

Create `desktop/src/services/hub_setup.js`:

```javascript
/**
 * HubSetupService — Orchestrates the first-time hub setup wizard.
 * State machine that manages Docker, backend startup, account creation,
 * and optional Cloudflare tunnel setup.
 */

const STATES = {
    CHECKING: 'checking',
    WELCOME: 'welcome',
    DOCKER_CHECK: 'docker_check',
    DOCKER_INSTALL: 'docker_install',
    DOCKER_WAIT: 'docker_wait',
    STARTING_BACKEND: 'starting_backend',
    BACKEND_HEALTH_WAIT: 'backend_health_wait',
    NEEDS_ACCOUNT: 'needs_account',
    AI_SETUP: 'ai_setup',
    REMOTE_ACCESS: 'remote_access',
    QUICK_TUNNEL: 'quick_tunnel',
    PERMANENT_TUNNEL: 'permanent_tunnel',
    DONE: 'done',
    READY: 'ready',
    // Connect-to-hub path
    DISCOVER: 'discover',
    CONNECT: 'connect',
    DEVICE_APPROVE: 'device_approve',
    LOGIN: 'login',
};

const STORAGE_KEYS = {
    STATE: 'aion_hub_setup_state',
    HUB_MODE: 'aion_hub_mode',
    HUB_URL: 'aion_hub_url',
    TUNNEL_URL: 'aion_tunnel_url',
    SETUP_COMPLETE: 'aion_hub_setup_complete',
    COMPOSE_PATH: 'aion_compose_path',
    SECRET_KEY: 'aion_secret_key',
};

export class HubSetupService {
    constructor() {
        this.state = STATES.CHECKING;
        this.progress = { step: 0, totalSteps: 7, containerStatuses: {}, error: null };
        this._listeners = { stateChange: [], progress: [] };
        this._healthPollInterval = null;
        this._containerPollInterval = null;
    }

    // --- Event System ---

    onStateChange(callback) {
        this._listeners.stateChange.push(callback);
        return () => {
            this._listeners.stateChange = this._listeners.stateChange.filter(cb => cb !== callback);
        };
    }

    onProgress(callback) {
        this._listeners.progress.push(callback);
        return () => {
            this._listeners.progress = this._listeners.progress.filter(cb => cb !== callback);
        };
    }

    _setState(newState) {
        const oldState = this.state;
        this.state = newState;
        this.saveState();
        this._listeners.stateChange.forEach(cb => cb(newState, oldState));
    }

    _setProgress(updates) {
        Object.assign(this.progress, updates);
        this._listeners.progress.forEach(cb => cb(this.progress));
    }

    // --- Persistence ---

    saveState() {
        try {
            localStorage.setItem(STORAGE_KEYS.STATE, this.state);
        } catch (e) { /* ignore */ }
    }

    loadState() {
        try {
            return localStorage.getItem(STORAGE_KEYS.STATE);
        } catch (e) { return null; }
    }

    // --- Initialization ---

    async initialize() {
        // Check if setup was already completed
        const setupComplete = localStorage.getItem(STORAGE_KEYS.SETUP_COMPLETE);
        if (setupComplete === 'true') {
            this._setState(STATES.READY);
            return;
        }

        // Try to resume from saved state
        const savedState = this.loadState();
        if (savedState && savedState !== STATES.CHECKING) {
            this._setState(savedState);
            return;
        }

        // Fresh start — check if backend is reachable
        this._setState(STATES.CHECKING);
        const healthy = await this.checkBackendHealth();

        if (healthy) {
            // Backend running — check hub status
            const hubStatus = await this._fetchHubStatus();
            if (hubStatus && hubStatus.setup_complete) {
                this._setState(STATES.READY);
            } else {
                this._setState(STATES.NEEDS_ACCOUNT);
            }
        } else {
            this._setState(STATES.WELCOME);
        }
    }

    // --- Docker ---

    async checkDocker() {
        try {
            const result = await window.__TAURI__.core.invoke('check_docker_installed');
            return result;
        } catch (e) {
            return { installed: false, version: '' };
        }
    }

    async checkDockerRunning() {
        try {
            const result = await window.__TAURI__.core.invoke('check_docker_running');
            return result;
        } catch (e) {
            return { running: false };
        }
    }

    async installDocker(auto = false) {
        if (!auto) {
            // Open download page
            try {
                await window.__TAURI__.shell.open('https://www.docker.com/products/docker-desktop/');
            } catch (e) {
                window.open('https://www.docker.com/products/docker-desktop/', '_blank');
            }
            return { success: true };
        }

        this._setProgress({ error: null });
        try {
            const result = await window.__TAURI__.core.invoke('install_docker');
            return result;
        } catch (e) {
            this._setProgress({ error: `Docker install failed: ${e}` });
            return { success: false, error: String(e) };
        }
    }

    async startBackend() {
        this._setState(STATES.STARTING_BACKEND);
        this._setProgress({ containerStatuses: {
            postgres: 'waiting', qdrant: 'waiting', redis: 'waiting', api: 'waiting', migrations: 'waiting'
        }});

        // Get or generate SECRET_KEY — stored in OS keychain (secure storage), never in plaintext
        let secretKey = null;
        try {
            secretKey = await window.__TAURI__.core.invoke('secure_storage_get', { key: 'aion_secret_key' });
        } catch (e) { /* not stored yet */ }

        if (!secretKey) {
            const array = new Uint8Array(48);
            crypto.getRandomValues(array);
            secretKey = Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
            try {
                await window.__TAURI__.core.invoke('secure_storage_set', {
                    key: 'aion_secret_key', value: secretKey
                });
            } catch (e) {
                // Last resort fallback — should rarely happen
                localStorage.setItem(STORAGE_KEYS.SECRET_KEY, secretKey);
            }
        }

        const composePath = this._getComposePath();

        // Try pull first, fall back to build
        try {
            await window.__TAURI__.core.invoke('start_docker_compose', {
                composePath,
                envVars: { SECRET_KEY: secretKey },
            });
        } catch (e) {
            this._setProgress({ error: `Failed to start: ${e}` });
            return false;
        }

        // Start polling container status
        this._startContainerPolling(composePath);
        return true;
    }

    _getComposePath() {
        // Resolve path to backend/docker-compose.yml relative to the app
        const saved = localStorage.getItem(STORAGE_KEYS.COMPOSE_PATH);
        if (saved) return saved;
        // Default — will be set during setup
        return 'backend/docker-compose.yml';
    }

    _startContainerPolling(composePath) {
        if (this._containerPollInterval) clearInterval(this._containerPollInterval);
        this._containerPollInterval = setInterval(async () => {
            try {
                const result = await window.__TAURI__.core.invoke('get_docker_compose_status', { composePath });
                const containers = result.containers || [];
                const statuses = {};
                for (const c of containers) {
                    const name = (c.Name || c.Service || '').toLowerCase();
                    const state = (c.State || '').toLowerCase();
                    if (name.includes('postgres')) statuses.postgres = state === 'running' ? 'running' : 'starting';
                    if (name.includes('qdrant')) statuses.qdrant = state === 'running' ? 'running' : 'starting';
                    if (name.includes('redis')) statuses.redis = state === 'running' ? 'running' : 'starting';
                    if (name.includes('api') || name.includes('backend')) statuses.api = state === 'running' ? 'running' : 'starting';
                }
                this._setProgress({ containerStatuses: statuses });

                // Check if all services are running
                const allRunning = ['postgres', 'qdrant', 'redis', 'api']
                    .every(s => statuses[s] === 'running');
                if (allRunning) {
                    this._stopContainerPolling();
                    this._setProgress({ containerStatuses: { ...statuses, migrations: 'running' } });
                    // Wait for health check
                    this._setState(STATES.BACKEND_HEALTH_WAIT);
                    await this.waitForHealth();
                }
            } catch (e) { /* retry next tick */ }
        }, 2000);
    }

    _stopContainerPolling() {
        if (this._containerPollInterval) {
            clearInterval(this._containerPollInterval);
            this._containerPollInterval = null;
        }
    }

    async waitForHealth(timeoutMs = 120000) {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const healthy = await this.checkBackendHealth();
            if (healthy) {
                this._setProgress({ containerStatuses: {
                    postgres: 'running', qdrant: 'running', redis: 'running', api: 'running', migrations: 'done'
                }});
                this._setState(STATES.NEEDS_ACCOUNT);
                return true;
            }
            await new Promise(r => setTimeout(r, 3000));
        }
        this._setProgress({ error: 'Backend health check timed out after 2 minutes' });
        return false;
    }

    async checkBackendHealth() {
        try {
            const result = await window.__TAURI__.core.invoke('check_backend_health', { url: null });
            return result.healthy === true;
        } catch (e) {
            return false;
        }
    }

    async _fetchHubStatus() {
        try {
            const resp = await fetch(`${this._getApiBase()}/hub/status`);
            if (resp.ok) return await resp.json();
        } catch (e) { /* not reachable */ }
        return null;
    }

    _getApiBase() {
        return localStorage.getItem('aion_server_url') || 'http://localhost:8000/api/v1';
    }

    // --- Account ---

    async createAccount(username, password) {
        const resp = await fetch(`${this._getApiBase()}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Registration failed' }));
            throw new Error(err.detail || 'Registration failed');
        }

        const data = await resp.json();

        // Auto-login
        await this.login(username, password);
        return data;
    }

    async login(username, password) {
        const resp = await fetch(`${this._getApiBase()}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Login failed' }));
            throw new Error(err.detail || 'Login failed');
        }

        const tokens = await resp.json();

        // Store in secure storage
        try {
            const { SecureStorage } = await import('./secure_storage.js');
            await SecureStorage.saveAuthSession({
                accessToken: tokens.access_token,
                refreshToken: tokens.refresh_token,
                userId: tokens.user_id,
            });
        } catch (e) {
            // Fallback to localStorage
            localStorage.setItem('aion_access_token', tokens.access_token);
        }

        return tokens;
    }

    // --- Tunnel ---

    async checkCloudflared() {
        try {
            return await window.__TAURI__.core.invoke('check_cloudflared');
        } catch (e) {
            return { installed: false, version: '' };
        }
    }

    async installCloudflared() {
        try {
            return await window.__TAURI__.core.invoke('install_cloudflared');
        } catch (e) {
            return { success: false, error: String(e) };
        }
    }

    async startQuickTunnel() {
        this._setState(STATES.QUICK_TUNNEL);
        try {
            const result = await window.__TAURI__.core.invoke('start_quick_tunnel', { port: 8000 });
            localStorage.setItem(STORAGE_KEYS.TUNNEL_URL, result.url);
            return result;
        } catch (e) {
            this._setProgress({ error: `Tunnel failed: ${e}` });
            return { url: null, error: String(e) };
        }
    }

    // --- Discovery (Connect to Hub) ---

    async discoverHubs() {
        // Try mDNS discovery via a LAN scan
        // This calls the discovery endpoint on found services
        try {
            const resp = await fetch('http://localhost:8000/api/v1/discovery/info');
            if (resp.ok) {
                const info = await resp.json();
                return [{ url: 'http://localhost:8000', ...info }];
            }
        } catch (e) { /* not on localhost */ }
        return [];
    }

    async connectToHub(url) {
        // Validate the URL by checking health
        try {
            const resp = await fetch(`${url}/health`);
            if (resp.ok) {
                localStorage.setItem('aion_server_url', `${url}/api/v1`);
                localStorage.setItem(STORAGE_KEYS.HUB_URL, url);
                localStorage.setItem(STORAGE_KEYS.HUB_MODE, 'client');
                return true;
            }
        } catch (e) { /* unreachable */ }
        return false;
    }

    // --- Completion ---

    async markComplete() {
        localStorage.setItem(STORAGE_KEYS.SETUP_COMPLETE, 'true');
        try {
            await fetch(`${this._getApiBase()}/hub/setup-complete`, { method: 'POST' });
        } catch (e) { /* best effort */ }
        this._setState(STATES.READY);
    }

    destroy() {
        this._stopContainerPolling();
        if (this._healthPollInterval) clearInterval(this._healthPollInterval);
    }
}

export { STATES, STORAGE_KEYS };
```

**Implementation notes:**
- `fetch()` is used for localhost API calls (e.g., `localhost:8000/api/v1/auth/register`) — this is fine since CSP already allows localhost. The `proxy_request` Rust command is for remote/tunnel URLs only.
- `discoverHubs()` is a stub that only checks localhost. Full mDNS scanning via a Tauri command is deferred — for now, users rely on manual URL entry for non-localhost hubs.
- `setupPermanentTunnel()` is deferred to a follow-up task — the multi-step Cloudflare auth flow needs more design. Quick Tunnel works for v0.5.0.
- QR code generation on the Done screen is deferred — show the connection URL as copyable text for now.

- [ ] **Step 2: Commit**

```bash
git add desktop/src/services/hub_setup.js
git commit -m "feat: add HubSetupService state machine for setup wizard"
```

---

### Task 13: Wizard UI in index.html

**Files:**
- Modify: `desktop/index.html`
- Modify: `desktop/src/styles/overlay.css`

- [ ] **Step 1: Add wizard HTML to index.html**

Add a `#hub-wizard` overlay section near the top of `<body>` in `desktop/index.html`, before the existing content. This is a full-screen overlay that covers the app until setup is complete.

The wizard HTML should include:
- A container `<div id="hub-wizard" class="hub-wizard">` (hidden by default)
- Step progress bar (reusable component)
- Step 1: Welcome (logo, two buttons)
- Step 2: Docker Check (status, install options)
- Step 3: Start Backend (container status list)
- Step 4: Create Account (form)
- Step 5: AI Setup (placeholder — transitions to existing wizard)
- Step 6: Remote Access (three options)
- Step 7: Done (summary, QR placeholder)
- Each step is a `<div class="wizard-step" data-step="N">` shown/hidden by JS

Use the crystalline triangle SVG logo from the approved mockups (no emojis).

- [ ] **Step 2: Add wizard styles to overlay.css**

Add styles for `.hub-wizard`, `.wizard-step`, `.wizard-progress`, `.wizard-btn-primary`, `.wizard-btn-secondary`, status rows, and animations. Match the existing glassmorphism style (use `--glass`, `--accent`, `--border` CSS variables).

- [ ] **Step 3: Commit**

```bash
git add desktop/index.html desktop/src/styles/overlay.css
git commit -m "feat: add hub setup wizard HTML and styles"
```

---

### Task 14: Wire Wizard into main.js

**Files:**
- Modify: `desktop/src/main.js`

- [ ] **Step 1: Import HubSetupService**

At the top of `desktop/src/main.js`, add:

```javascript
import { HubSetupService, STATES } from './services/hub_setup.js';
```

- [ ] **Step 2: Add startup detection**

In the initialization section of `main.js` (after `load()` and `initEls()`), add:

```javascript
// Hub setup detection
const hubSetup = new HubSetupService();
hubSetup.onStateChange((newState) => renderWizardState(newState, hubSetup));
hubSetup.onProgress((progress) => renderWizardProgress(progress));
await hubSetup.initialize();
```

- [ ] **Step 3: Add wizard rendering functions**

Add `renderWizardState(state, service)` function that:
- Shows/hides the `#hub-wizard` overlay based on state
- Shows the correct step `div` based on state
- Updates the progress bar
- Handles button clicks (delegating to HubSetupService methods)
- When state is `READY`: hides wizard, shows main app

Add `renderWizardProgress(progress)` function that:
- Updates container status indicators
- Shows/hides error messages
- Updates the progress bar fill

- [ ] **Step 4: Wire up wizard button event handlers**

Connect all wizard buttons to HubSetupService methods:
- "Set up as Hub" → `hubSetup._setState(STATES.DOCKER_CHECK)`
- "Connect to Hub" → `hubSetup._setState(STATES.DISCOVER)`
- "Auto-Install Docker" → `hubSetup.installDocker(true)`
- "Download Manually" → `hubSetup.installDocker(false)`
- "Re-check" → `hubSetup.checkDocker()`
- "Create Account" → `hubSetup.createAccount(username, password)`
- "Quick Tunnel" → `hubSetup.startQuickTunnel()`
- "Skip" → `hubSetup._setState(STATES.DONE)`
- "Enter Aion" → `hubSetup.markComplete()`

- [ ] **Step 5: Test manually**

Run: `cd desktop && npm run dev`
Open: `http://localhost:1420`
Expected: Wizard overlay appears (backend not running), showing Welcome screen.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/main.js
git commit -m "feat: wire hub setup wizard into app startup flow"
```

---

## Phase 4: Integration + Version Bumps

### Task 15: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/xxx_add_system_settings.py` (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `cd backend && alembic revision --autogenerate -m "add system_settings table"`
Expected: New migration file created in `backend/alembic/versions/`

- [ ] **Step 2: Verify migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: add migration for system_settings table"
```

---

### Task 16: Version Bumps

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/src-tauri/tauri.conf.json`
- Modify: `desktop/src-tauri/Cargo.toml`
- Modify: `mobile/pubspec.yaml`

- [ ] **Step 1: Bump all versions from 0.4.3 to 0.5.0**

In each file, find the version string `0.4.3` and replace with `0.5.0`.

For `desktop/src-tauri/Cargo.toml`, the version is in `[package]` section.
For `desktop/src-tauri/tauri.conf.json`, check `version` field.
For `mobile/pubspec.yaml`, update `version: 0.5.0+14` (increment build number).

- [ ] **Step 2: Commit**

```bash
git add desktop/package.json desktop/src-tauri/tauri.conf.json desktop/src-tauri/Cargo.toml mobile/pubspec.yaml
git commit -m "chore: bump version to 0.5.0"
```

---

### Task 17: Integration Test

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify Rust compilation**

Run: `cd desktop/src-tauri && cargo check`
Expected: Compiles without errors

- [ ] **Step 3: Verify Vite build**

Run: `cd desktop && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Manual smoke test**

1. Start Docker Desktop
2. Run: `cd desktop && npm run tauri:dev`
3. Wizard should appear (no backend running)
4. Click "Set up as Hub"
5. Docker should be detected
6. Backend containers should start
7. Create account
8. Skip remote access
9. App should load

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: v0.5.0 hub auto-setup integration complete"
```
