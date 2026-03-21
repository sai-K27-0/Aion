# Aion v0.5.0 — Auto Hub Setup + Remote Access — Design Spec

## Overview

Build a seamless first-time setup experience so that when a user installs Aion and opens it, the app detects no backend is running, walks them through setup (Docker, backend services, account creation, AI configuration, optional remote access), and delivers a fully functional personal AI hub — without the user ever opening a terminal.

**Version:** 0.5.0
**Date:** 2026-03-22

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Full v0.5.0 — all 5 phases | Delivers complete "install and it works" vision |
| Docker install | User chooses auto-install or manual download | Auto-install is convenient; manual respects user control. Both options presented. |
| Wizard options | Two: "Set up as Hub" / "Connect to existing Hub" | Simpler than three options. "Connect to Hub" handles both LAN and tunnel URLs. |
| Cloudflare Tunnel | Quick Tunnel (instant, no account) + Permanent Domain (Cloudflare account) | Quick Tunnel lowers the barrier; permanent domain is for power users. |
| Backend startup | Hybrid: try pull pre-built image, fall back to local build | Best of both: fast when registry available, self-contained when not. |
| Architecture | Desktop Orchestrator + Backend Security Layer (Approach C) | Desktop manages infrastructure (Docker, cloudflared). Backend owns ALL security. Clean separation. |
| Wizard layout | Linear Stepper with progress bar | Matches existing AI Setup Wizard pattern. Clear progress indication. |
| Logo | Unified crystalline triangle SVG | One logo across all screens. No emojis in wizard UI. |

---

## 1. Security Architecture

Security is the top priority. Defense in depth with the backend as the single security boundary.

### Security Layers

```
Internet → Cloudflare (DDoS, WAF) → cloudflared tunnel → localhost:8000
                                                               │
                                                        ┌──────┴──────┐
                                                        │   Backend   │
                                                        │  Rate Limit │  100 req/min global, 10 req/min auth
                                                        │  CORS       │  Whitelist: tauri://, tunnel domain
                                                        │  JWT Auth   │  Every request except /health, /auth
                                                        │  Device     │  X-Device-ID + 6-digit approval
                                                        │  Approval   │
                                                        └─────────────┘
```

### Tunnel Security

- Cloudflared tunnel encrypts traffic end-to-end (TLS between Cloudflare edge and origin).
- Tunnel only exposes port 8000 — no database ports, no Redis, no Qdrant.
- Backend CORS whitelist updated to include the user's tunnel domain.
- Cloudflare's built-in DDoS protection and WAF apply automatically.
- Tunnel credentials stored in OS keychain (not in a config file on disk).

### Authentication Hardening

- Rate limit auth endpoints: 10 requests/minute (prevents brute force).
- Token blacklist moved from in-memory `set()` to Redis (survives restarts).
- Access tokens: 30 minutes. Refresh tokens: 7 days, stored in OS keychain only.
- First registered user becomes admin automatically (no approval code needed).
- Subsequent users must be approved by admin.

### Registration Lock

- After the first user registers, registration is locked by default.
- Admin can unlock registration temporarily (for inviting family members, etc.).
- When locked, `POST /auth/register` returns `403 Forbidden`.
- Critical for tunnel security — prevents random internet users from creating accounts.

### Credential Storage

- JWT tokens → OS keychain (existing, via Rust `secure_storage_*` commands).
- Cloudflare tunnel credentials → OS keychain (new).
- `SECRET_KEY` generated once by the desktop app on first hub setup, stored in OS keychain, and passed to Docker as an environment variable. Never written to files inside the container. Persists across container restarts because the desktop app always passes it when starting Docker Compose.
- Database passwords stay in Docker volumes, never exposed.

### Security Headers (existing, verified)

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Content-Security-Policy` (restrictive)
- `Strict-Transport-Security` when accessed via tunnel

---

## 2. Setup Wizard Flow

### State Machine

```
DETECT → (backend reachable?)
  ├── YES → (check /hub/status)
  │   ├── setup_complete → LOGIN → main app
  │   └── not complete → NEEDS_ACCOUNT (skip to Step 4)
  └── NO → WELCOME
      ├── "Set up as Hub" → DOCKER_CHECK → START_BACKEND → CREATE_ACCOUNT → AI_SETUP → REMOTE_ACCESS → DONE
      └── "Connect to Hub" → DISCOVER_HUBS → APPROVE_DEVICE → LOGIN → main app
```

### Steps (Linear Stepper with progress bar)

**Step 1 — Welcome**
- Crystalline triangle logo + "A I O N" title.
- Two options: [Set up as Hub] and [Connect to existing Hub].

**Step 2 — Docker Check** (Hub path only)
- Detect Docker Desktop: installed? running?
- If not installed: two options — [Auto-Install] (downloads + runs installer with admin elevation) or [Download Manually] (opens download page).
- If installed but not running: prompt to start Docker Desktop.
- [Re-check] button.
- Auto-advance when Docker is detected and running.

**Step 3 — Start Backend** (Hub path only)
- Hybrid image strategy: try `docker compose pull` first, fall back to `docker compose up -d --build`.
- Live status per container: PostgreSQL, Qdrant, Redis, Backend API, Database Migrations.
- Each shows: Waiting → Starting (spinner) → Running (checkmark).
- Health check poll every 3s. Auto-advance when `/health` returns OK.

**Step 4 — Create Account**
- Username, password, confirm password fields.
- "Lock registration after this account" checkbox (checked by default).
- Calls `POST /api/v1/auth/register`.
- First user gets `is_superuser = True`.
- Auto-login after registration: tokens stored in OS keychain.

**Step 5 — AI Setup**
- Transition to the existing AI Setup Wizard (v0.4.3).
- Hardware detection → Ollama check → model recommendations → download → verify.
- Already built — no changes needed.

**Step 6 — Remote Access** (Optional)
- Three options: [Quick Tunnel], [Permanent Domain], [Skip — LAN only].
- Quick Tunnel: `cloudflared tunnel --url localhost:8000` → instant `*.trycloudflare.com` URL. **Warning displayed: "This URL is temporary and changes every time Aion restarts. Use Permanent Domain for a stable URL."**
- Permanent Domain: `cloudflared tunnel login` (browser auth) → create tunnel → route DNS → start.
- Test connection before completing.

Note: Quick Tunnel URLs are ephemeral — if the desktop app restarts, the URL changes and mobile devices lose connectivity until they reconnect via LAN. The wizard and the Done screen both warn about this. Mobile devices should fall back to mDNS discovery when the tunnel URL becomes unreachable.

**Step 7 — Done**
- Hub summary: LAN address, tunnel URL (if set up), QR code for phone.
- [Enter Aion] button → transition to main app.

### Smart Skipping

Each step checks preconditions:
- Docker installed + running → skip Step 2.
- Containers already running + healthy → skip Step 3.
- User exists → show Login instead of Create Account.
- AI setup already done → skip Step 5.
- Tunnel already configured → skip Step 6.

### Resumability

Setup state persisted to `localStorage` at each step. If app closes mid-setup, it resumes from the last completed step.

### "Connect to Hub" Alternate Path

From Step 1:
1. Scan LAN for `_aion._tcp.local.` mDNS services.
2. Show discovered hubs with one-click connect.
3. Manual URL entry field (for tunnel URLs or non-discoverable IPs).
4. Enter 6-digit device approval code.
5. Login with existing account → straight to main app.

---

## 3. Rust Commands (Desktop — src-tauri)

### New Module: `src-tauri/src/docker.rs`

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `check_docker_installed` | — | `{ installed: bool, version: String }` | Runs `docker --version` + `docker compose version` |
| `check_docker_running` | — | `{ running: bool }` | Runs `docker info`, returns false on error |
| `install_docker` | — | `{ success: bool, error?: String }` | Downloads Docker Desktop installer, runs with admin elevation (UAC on Windows) |
| `start_docker_compose` | `compose_path: String, env_vars: Option<HashMap<String, String>>` | `{ success: bool, error?: String }` | Runs `docker compose -f <path> up -d` with optional env vars (used to pass SECRET_KEY from keychain) |
| `stop_docker_compose` | `compose_path: String` | `{ success: bool }` | Runs `docker compose -f <path> down` |
| `get_docker_compose_status` | `compose_path: String` | `Vec<ContainerStatus>` | Runs `docker compose ps --format json` |
| `check_backend_health` | `url: Option<String>` | `{ healthy: bool, version?: String }` | HTTP GET to `localhost:8000/health`, 5s timeout |

### New Module: `src-tauri/src/cloudflare.rs`

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `check_cloudflared` | — | `{ installed: bool, version: String }` | Runs `cloudflared --version` |
| `install_cloudflared` | — | `{ success: bool }` | Platform-specific install (Windows: MSI, macOS: brew, Linux: curl) |
| `start_quick_tunnel` | `port: u16` | `{ url: String }` | Runs `cloudflared tunnel --url localhost:<port>`, parses URL from stderr |

### In `main.rs` (not a separate module)

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `proxy_request` | `url: String, method: String, body: Option<String>, headers: HashMap<String, String>` | `{ status: u16, body: String, headers: HashMap }` | Forwards HTTP requests from JS through Rust. Validates target URL against configured hub/tunnel URL. |

### Security in Rust

- `install_docker` uses `ShellExecute` with `runas` verb on Windows (triggers UAC prompt).
- Cloudflare tunnel credentials stored in OS keychain via `secure_storage_set`.
- All commands use `std::process::Command` with explicit argument lists (no shell injection).
- Timeouts: 5s for health checks, 30s for Docker operations, 120s for tunnel startup.

### File Organization

```
src-tauri/src/
├── main.rs          # Existing — registers new commands in invoke_handler
├── docker.rs        # NEW — Docker management commands
└── cloudflare.rs    # NEW — Cloudflare tunnel commands
```

---

## 4. Backend Changes

### 4A: Auth System Fixes

**Token blacklist → Redis** — New file: `app/services/token_blacklist_service.py`

```python
class TokenBlacklistService:
    async def blacklist_token(token: str, expires_in: int) -> None
        # Redis SET token_blacklist:{jti} 1 EX {expires_in}
    async def is_blacklisted(token: str) -> bool
        # Redis EXISTS token_blacklist:{jti}
```

- Uses Redis TTL for auto-expiry.
- Falls back to in-memory set if Redis unavailable.

**Device service → Database** — Update `app/services/device_service.py` to use the existing `Device` SQLAlchemy model + `DeviceApprovalService` instead of in-memory dicts.

**Auth rate limiting** — Add 10 req/min rate limit on `/api/v1/auth/*` endpoints.

### 4B: Registration Lock

**Endpoints:**

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/v1/auth/registration-status` | No | Returns `{ open: bool }` |
| `POST /api/v1/auth/registration-lock` | Admin | Lock registration |
| `POST /api/v1/auth/registration-unlock` | Admin | Unlock registration |

**Logic in `POST /auth/register`:**
1. No users exist → allow (first user bootstrap).
2. Users exist + registration locked → `403 Forbidden`.
3. First user → `is_superuser = True`.
4. Registration auto-locks after first user.

### 4C: Hub Status Endpoints

New file: `app/api/v1/endpoints/hub.py`

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/v1/hub/status` | No | `{ setup_complete, registration_open }` |
| `GET /api/v1/hub/status` | Admin | `{ setup_complete, registration_open, user_count, tunnel_active, version }` |
| `POST /api/v1/hub/setup-complete` | Admin | Marks setup as done |

`GET /hub/status` is unauthenticated but returns only `{ setup_complete, registration_open }` — no user count, version, or tunnel status. When called with a valid admin JWT, returns the full response with `user_count`, `tunnel_active`, and `version`. This prevents unauthenticated attackers from probing operational details via the tunnel.

### 4D: CORS Updates

Add tunnel domain to allowed origins dynamically:

```python
if settings.tunnel_domain:
    allowed_origins.append(f"https://{settings.tunnel_domain}")
```

New env var: `TUNNEL_DOMAIN` — set by desktop app after tunnel setup.

### 4E: Docker Configuration

**New file: `backend/entrypoint.sh`**
- Run `alembic upgrade head` on startup.
- `SECRET_KEY` is NOT generated here — it is passed as an environment variable by the desktop app (which stores it in the OS keychain). The entrypoint validates that `SECRET_KEY` is set and non-default, refusing to start if missing.
- Start `uvicorn` on `0.0.0.0:8000`.

**`backend/docker-compose.yml` updates:**
- Add health check on backend container and Qdrant.
- Existing health checks on PostgreSQL and Redis are retained.

### 4F: Pydantic Schemas

New file: `app/schemas/hub.py`

```python
class HubStatusPublicResponse(BaseModel):
    setup_complete: bool
    registration_open: bool

class HubStatusAdminResponse(HubStatusPublicResponse):
    user_count: int
    tunnel_active: bool
    version: str

class RegistrationStatusResponse(BaseModel):
    open: bool

class RegistrationLockRequest(BaseModel):
    locked: bool
```

Update `app/schemas/auth.py` — make `email` explicitly optional in `UserCreate` (username-only registration for hub setup).

### 4G: SystemSettings Model

New file: `app/models/system_settings.py`

Singleton row pattern (one row, queried by fixed ID):

```python
class SystemSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    registration_locked: bool = True        # Default: locked after first user
    setup_complete: bool = False            # Set to True after wizard finishes
    tunnel_domain: Optional[str] = None     # e.g. "aion.sam0sa.me"
    tunnel_type: Optional[str] = None       # "quick" | "permanent" | None
```

Requires migration: `alembic revision --autogenerate -m "add system_settings"`

### 4H: Device Service Rewrite

The current `DeviceService` is synchronous with in-memory storage. It must be rewritten to:
- Use `async` methods with `AsyncSession`
- Use the existing `Device` SQLAlchemy model (`app/models/device.py`)
- Integrate with the existing approval logic in `DeviceApprovalService` (which already exists at `app/services/device_approval_service.py`)
- Remove the in-memory `_devices` dict and `_tokens` dict entirely

### 4I: Rate Limiting Behind Tunnel

When behind cloudflared, all traffic appears to come from `127.0.0.1`. The rate limiter must use `CF-Connecting-IP` or `X-Forwarded-For` headers for the real client IP:

```python
def get_real_ip(request: Request) -> str:
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.client.host
    )
```

Configure `slowapi` to use this function as the key function instead of `get_remote_address`.

### 4J: Tunnel Domain Communication

The desktop app communicates the tunnel domain to the containerized backend via an **admin API endpoint**, not an environment variable (which would require a container restart):

```
POST /api/v1/hub/tunnel-config   (Admin only)
Body: { domain: "aion.sam0sa.me", type: "permanent" }
```

This updates `SystemSettings.tunnel_domain` in the database and dynamically reconfigures CORS allowed origins at runtime. The `TUNNEL_DOMAIN` env var in `config.py` serves as an initial/fallback value only.

### 4K: New Backend Files

```
app/
├── api/v1/endpoints/
│   └── hub.py                     # NEW — hub status endpoints
├── schemas/
│   └── hub.py                     # NEW — hub request/response schemas
├── services/
│   └── token_blacklist_service.py # NEW — Redis token blacklist
├── models/
│   └── system_settings.py         # NEW — registration lock, hub config
```

Migration: `alembic revision --autogenerate -m "add system_settings"`

---

## 5. JS Orchestration Layer

### New File: `desktop/src/services/hub_setup.js`

**HubSetupService** — State machine that drives the wizard UI.

```
States: CHECKING → WELCOME → DOCKER_CHECK → DOCKER_INSTALL → DOCKER_WAIT
        → STARTING_BACKEND → BACKEND_HEALTH_WAIT → NEEDS_ACCOUNT
        → AI_SETUP → REMOTE_ACCESS → DONE → READY
```

**Key Methods:**

```javascript
class HubSetupService {
    // State
    state              // current wizard state
    progress           // { step, totalSteps, containerStatuses, error }

    // Lifecycle
    async initialize()          // Run initial detection, determine starting state
    saveState() / loadState()   // localStorage persistence

    // Docker
    async checkDocker()         // invoke('check_docker_installed')
    async checkDockerRunning()  // invoke('check_docker_running')
    async installDocker(auto)   // auto=true: invoke('install_docker'), false: open page
    async startBackend()        // invoke('start_docker_compose', { composePath })
    async pollContainerStatus() // invoke('get_docker_compose_status') on 2s interval
    async waitForHealth()       // poll check_backend_health every 3s, timeout 120s

    // Account
    async createAccount(username, password)  // POST /auth/register
    async login(username, password)          // POST /auth/login → keychain

    // Tunnel
    async checkCloudflared()      // invoke('check_cloudflared')
    async installCloudflared()    // invoke('install_cloudflared')
    async startQuickTunnel()      // invoke('start_quick_tunnel', { port: 8000 })
    async setupPermanentTunnel()  // multi-step: login → create → route → start

    // Discovery
    async discoverHubs()       // GET /api/v1/discovery/info on mDNS services
    async connectToHub(url)    // set API_BASE, verify health
    async approveDevice(code)  // POST /api/v1/devices/approve

    // Events
    onStateChange(callback)
    onProgress(callback)
}
```

### App Startup Flow (main.js changes)

```
Current:  load() → initEls() → render UI → try to sync
New:      load() → initEls() → HubSetupService.initialize()
            ├── READY → hide wizard, show main app
            └── NOT READY → show wizard overlay (#hub-wizard)
                → wizard completes → fade out wizard, show main app
```

The wizard is a full-screen overlay in `index.html` (`#hub-wizard`) that sits on top of the existing app. Existing login screen tabs remain but are only shown post-setup.

### CSP Strategy

Use the **Rust proxy pattern** exclusively (like the existing Ollama proxy):
- Add a `proxy_request` Tauri command in `main.rs` that forwards HTTP from JS → Rust → remote URL.
- Avoids CSP issues entirely — no CSP changes needed for tunnel domains.
- All network traffic goes through Rust where we control timeouts, headers, and error handling.
- The proxy validates that the target URL matches the configured hub URL or tunnel URL before forwarding.

The `proxy_request` command is registered in `main.rs` (not in a separate module, since it's a single generic command).

### localStorage Keys

```javascript
const HUB_SETUP_KEYS = {
    STATE: 'aion_hub_setup_state',
    HUB_MODE: 'aion_hub_mode',           // 'hub' or 'client'
    HUB_URL: 'aion_hub_url',
    TUNNEL_URL: 'aion_tunnel_url',
    SETUP_COMPLETE: 'aion_hub_setup_complete',
    COMPOSE_PATH: 'aion_compose_path',
};
```

### Error Handling

Every wizard step has specific failure modes with recovery paths:

| Step | Failure | Recovery |
|------|---------|----------|
| Docker Check | Not installed | Show install options (auto/manual) |
| Docker Check | Installed but not running | "Start Docker Desktop" button + re-check |
| Start Backend | Container fails | Show error log, retry button |
| Start Backend | Health check timeout (120s) | Extend timeout or show logs |
| Create Account | Registration locked | "Hub already has an owner" message |
| Create Account | Weak password | Client-side validation: min 8 chars |
| Tunnel | cloudflared install fails | Fall back to manual download |
| Tunnel | Quick tunnel fails | Retry or skip |
| Connect to Hub | No hubs on LAN | Manual URL entry |
| Connect to Hub | Device not approved | "Waiting for approval..." with polling |

Every error shows Retry and Back buttons. No dead ends.

---

## Scope Notes

### Mobile App (Out of Scope for v0.5.0)

The mobile app version bump to 0.5.0 is for consistency only. The mobile "Connect to Hub" flow (entering tunnel URLs, storing them, device approval from mobile) is deferred to v0.5.1. Mobile already supports manual server URL entry and device pairing via the existing UI — it will continue to work with a manually configured hub URL.

### Docker Auto-Install (Windows Only for v0.5.0)

The `install_docker` Rust command auto-installs Docker Desktop on Windows only (via MSI + UAC). macOS and Linux show the "Download Manually" option with platform-specific instructions. Cross-platform auto-install is deferred.

---

## File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `desktop/src-tauri/src/docker.rs` | Rust Docker management commands |
| `desktop/src-tauri/src/cloudflare.rs` | Rust Cloudflare tunnel commands |
| `desktop/src/services/hub_setup.js` | JS setup orchestration service |
| `backend/app/api/v1/endpoints/hub.py` | Hub status endpoints |
| `backend/app/services/token_blacklist_service.py` | Redis token blacklist |
| `backend/app/models/system_settings.py` | System settings model |
| `backend/app/schemas/hub.py` | Hub request/response Pydantic schemas |
| `backend/entrypoint.sh` | Docker entrypoint (migrations + server start) |
| `backend/alembic/versions/xxx_add_system_settings.py` | Migration for SystemSettings model |

### Modified Files

| File | Changes |
|------|---------|
| `desktop/src-tauri/src/main.rs` | Register new commands from docker.rs + cloudflare.rs modules |
| `desktop/src-tauri/Cargo.toml` | Add module declarations |
| `desktop/src-tauri/tauri.conf.json` | Version bump (CSP unchanged — proxy pattern avoids CSP changes) |
| `desktop/index.html` | Add `#hub-wizard` overlay section with wizard HTML |
| `desktop/src/main.js` | Add startup detection flow, wizard state management |
| `desktop/src/styles/overlay.css` | Add wizard step styles |
| `backend/app/api/v1/router.py` | Register hub router |
| `backend/app/api/v1/endpoints/auth.py` | Add registration lock check, rate limiting |
| `backend/app/schemas/auth.py` | Make email explicitly optional in UserCreate |
| `backend/app/services/auth_service.py` | Use Redis token blacklist, registration lock logic |
| `backend/app/services/device_service.py` | Full async rewrite: use Device DB model + DeviceApprovalService |
| `backend/app/main.py` | Add CORS for tunnel domain, auth rate limiting |
| `backend/app/config.py` | Add `tunnel_domain` setting |
| `backend/docker-compose.yml` | Add backend + Qdrant health checks |
| `backend/Dockerfile` | Use entrypoint.sh |

### Version Bumps

| File | From | To |
|------|------|----|
| `desktop/package.json` | 0.4.3 | 0.5.0 |
| `desktop/src-tauri/tauri.conf.json` | 0.4.3 | 0.5.0 |
| `desktop/src-tauri/Cargo.toml` | 0.4.3 | 0.5.0 |
| `mobile/pubspec.yaml` | 0.4.3 | 0.5.0 |

---

## Success Criteria

1. Fresh install → opens → detects no backend → walks through setup → backend running → account created → AI configured → app fully functional.
2. Second device on same WiFi → opens → finds hub via mDNS → enters approval code → syncs.
3. Phone on mobile data → connects via tunnel URL → syncs (if tunnel set up).
4. Everything works without the user ever opening a terminal.
5. Registration is locked after first user — no unauthorized account creation via tunnel.
6. All credentials stored in OS keychain, never in plaintext files.
