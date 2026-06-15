"""Tests for auth endpoint rate limiting (slowapi 5/min register, 10/min login)."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def http_client(test_engine):
    """
    AsyncClient backed by an in-memory SQLite database.
    Each test gets a fresh client; the DB override is torn down afterwards.
    """
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)


def _fresh_ip() -> str:
    """Unique string used as a rate-limit key so tests don't share counters."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Login rate limit — 10 requests/minute
# ---------------------------------------------------------------------------

class TestLoginRateLimit:
    async def test_rate_limit_triggers_after_10_requests(self, http_client: AsyncClient):
        """11 requests from the same IP should yield at least one 429."""
        ip = _fresh_ip()
        payload = {"username": "nobody", "password": "wrongpassword1"}

        responses = []
        for _ in range(11):
            r = await http_client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": ip},
            )
            responses.append(r)

        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, (
            f"Expected at least one 429 within 11 requests but got: {status_codes}"
        )

    async def test_rate_limit_429_has_retry_after_header(self, http_client: AsyncClient):
        """The 429 response from the login endpoint includes a Retry-After header."""
        ip = _fresh_ip()
        payload = {"username": "nobody", "password": "wrongpassword2"}

        last = None
        for _ in range(11):
            last = await http_client.post(
                "/api/v1/auth/login",
                json=payload,
                headers={"X-Forwarded-For": ip},
            )

        assert last.status_code == 429
        lower_keys = {k.lower() for k in last.headers}
        assert "retry-after" in lower_keys, (
            f"429 response missing Retry-After header. Headers: {dict(last.headers)}"
        )

    async def test_different_ips_have_independent_limits(self, http_client: AsyncClient):
        """A fresh IP should not be rate-limited by a previous test's requests."""
        payload = {"username": "nobody", "password": "wrongpassword3"}

        ip = _fresh_ip()
        r = await http_client.post(
            "/api/v1/auth/login",
            json=payload,
            headers={"X-Forwarded-For": ip},
        )
        # A fresh IP gets 401 (bad credentials), not 429
        assert r.status_code != 429


# ---------------------------------------------------------------------------
# Register rate limit — 5 requests/minute
# ---------------------------------------------------------------------------

class TestRegisterRateLimit:
    async def test_rate_limit_triggers_after_5_requests(self, http_client: AsyncClient):
        """6 requests from the same IP should yield at least one 429."""
        ip = _fresh_ip()
        payload = {"username": "testuser", "password": "testpassword123"}

        responses = []
        for _ in range(6):
            r = await http_client.post(
                "/api/v1/auth/register",
                json=payload,
                headers={"X-Forwarded-For": ip},
            )
            responses.append(r)

        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, (
            f"Expected at least one 429 within 6 requests but got: {status_codes}"
        )

    async def test_rate_limit_429_has_retry_after_header(self, http_client: AsyncClient):
        """The 429 response from the register endpoint includes a Retry-After header."""
        ip = _fresh_ip()
        payload = {"username": "testuser2", "password": "testpassword123"}

        last = None
        for _ in range(6):
            last = await http_client.post(
                "/api/v1/auth/register",
                json=payload,
                headers={"X-Forwarded-For": ip},
            )

        assert last.status_code == 429
        lower_keys = {k.lower() for k in last.headers}
        assert "retry-after" in lower_keys, (
            f"429 response missing Retry-After header. Headers: {dict(last.headers)}"
        )

    async def test_different_ips_have_independent_limits(self, http_client: AsyncClient):
        """A fresh IP on /register is not affected by other test counters."""
        ip = _fresh_ip()
        r = await http_client.post(
            "/api/v1/auth/register",
            json={"username": "newuser", "password": "newpassword123"},
            headers={"X-Forwarded-For": ip},
        )
        assert r.status_code != 429
