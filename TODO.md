# Aion — Project TODO

> Tracks pending features, fixes, and improvements across all platforms.  
> Sources: `docs/plans/2026-03-09-aion-major-update-plan.md`, `docs/superpowers/plans/2026-03-22-hub-auto-setup.md`

---

## Critical Fixes

- [ ] **Ghost mode race condition** — `toggle_click_through` in Rust must be the single source of truth; JS frontend must NOT call `setIgnoreCursorEvents` independently (`desktop/src-tauri/src/main.rs:112-162`, `desktop/src/main.js:1676-1711`)
- [ ] **Ghost mode exit button** — Add always-clickable triangle button in bottom-left so users can exit click-through mode without a keyboard shortcut (`desktop/index.html`, `desktop/src/styles/overlay.css`)
- [ ] **Block hard deletes** — `block_service.delete_block` currently hard-deletes; must soft-delete (`is_deleted = True`) and cascade to all descendants (`backend/app/services/block_service.py:201`)
- [ ] **Settings tab navigation** — Tab click handlers in settings panel don't reliably show/hide panes (`desktop/src/main.js:4117+`)

---

## Auth & Account System

- [ ] **Multi-method auth backend** — Add `auth_provider`, `email_verified`, `oauth_provider_id` fields to `User` model + migration (`backend/app/models/user.py`)
- [ ] **Logout with token blacklist** — Implement `POST /auth/logout` that blacklists the JWT JTI; Redis-backed with in-memory fallback (`backend/app/services/token_blacklist_service.py`)
- [ ] **OAuth stubs** — Add `POST /auth/oauth/{provider}` and callback endpoints (return 501 until credentials are configured) (`backend/app/api/v1/endpoints/auth.py`)
- [ ] **Auth rate limiting** — Add `slowapi` limits to `/auth/login` (10/min) and `/auth/register` (5/min) using real IP from `CF-Connecting-IP` header
- [ ] **First-time sign-in overlay** — Desktop auth overlay with sign-in / create account / pair device tabs; shows on startup if no token stored (`desktop/index.html`, `desktop/src/main.js`)
- [ ] **Account settings pane** — Show signed-in username, auth method, buttons for change password / manage devices / sign out (`desktop/index.html`)
- [ ] **Data reset** — "Clear all data" button that wipes IndexedDB, localStorage, and secure storage then reloads

---

## Hub Auto-Setup Wizard

- [ ] **SystemSettings model** — Singleton DB row: `registration_locked`, `setup_complete`, `tunnel_domain`, `tunnel_type` (`backend/app/models/system_settings.py`, migration `20260322_0001` already exists — verify fields match)
- [ ] **Hub endpoints** — `GET /hub/status`, `GET /hub/registration-status`, `POST /hub/setup-complete`, `POST /hub/registration-lock/unlock`, `POST /hub/tunnel-config` (`backend/app/api/v1/endpoints/hub.py`)
- [ ] **Registration lock logic** — First registered user becomes superuser and auto-locks registration; subsequent registrations require `registration_locked = false` (`backend/app/services/auth_service.py`)
- [ ] **Real-IP rate limiting** — Extract `CF-Connecting-IP` / `X-Forwarded-For` headers in a shared `get_real_ip()` utility for `slowapi` key function (`backend/app/utils/request.py`)
- [ ] **Docker management commands** — Rust Tauri commands: `check_docker_installed`, `check_docker_running`, `install_docker` (Windows auto-install via PowerShell), `start/stop_docker_compose`, `get_docker_compose_status`, `check_backend_health` (`desktop/src-tauri/src/docker.rs`)
- [ ] **Cloudflare tunnel commands** — Rust Tauri commands: `check_cloudflared`, `install_cloudflared` (per-platform), `start_quick_tunnel` (parse URL from stderr) (`desktop/src-tauri/src/cloudflare.rs`)
- [ ] **Generic proxy command** — `proxy_request(url, method, body, headers)` Tauri command to avoid CSP issues when calling tunnel/remote URLs from JS (`desktop/src-tauri/src/main.rs`)
- [ ] **HubSetupService state machine** — JS service orchestrating: checking → welcome → docker check → start backend → create account → AI setup → remote access → done (`desktop/src/services/hub_setup.js`)
- [ ] **Wizard HTML + CSS** — Full-screen overlay with 7-step progress, container status rows, glassmorphism styling (`desktop/index.html`, `desktop/src/styles/overlay.css`)
- [ ] **Wire wizard into startup** — On app init, run `HubSetupService.initialize()`; show wizard if backend not running or setup not complete; hide when state is `READY` (`desktop/src/main.js`)
- [ ] **Docker entrypoint** — `entrypoint.sh` that validates `SECRET_KEY`, waits for PostgreSQL, runs `alembic upgrade head`, then starts uvicorn (`backend/entrypoint.sh`, `backend/Dockerfile`)
- [ ] **Docker health checks** — Add `healthcheck` to `api` and `qdrant` services in `docker-compose.yml`; make `api` depend on all services being healthy

---

## AI Smart Assistant

- [ ] **AIBlockService** — Service that takes a natural language message, asks Ollama/OpenAI to plan block creation as JSON, then executes the plan (`backend/app/services/ai_block_service.py`)
- [ ] **`POST /ai/smart-action` endpoint** — Routes to `AIBlockService.smart_action()`; returns created blocks list + summary (`backend/app/api/v1/endpoints/ai.py`)
- [ ] **Desktop AI input → smart-action** — Update `sendAiQuery()` to call `/ai/smart-action` instead of plain chat; render created blocks in the response area (`desktop/src/main.js`)
- [ ] **AI provider settings UI** — Settings pane showing provider selector (Ollama / OpenAI / Anthropic), model dropdown, and API key input per provider; save to backend via `/ai/setup` (`desktop/index.html`)

---

## Desktop Polish

- [ ] **Triangle logo in orb** — Replace current orb SVG icon with the faceted triangle logo matching `src-tauri/icons/` (`desktop/index.html`)
- [ ] **Native vibrancy** — Apply `window-vibrancy` crate for macOS `NSVisualEffectMaterial::UnderWindowBackground` and Windows Acrylic in Rust setup (`desktop/src-tauri/src/main.rs`, `Cargo.toml`)
- [ ] **Crystallize theme blur** — Update `overlay.css` crystallize theme to use `backdrop-filter: blur(20px) saturate(1.5)` on panels
- [ ] **Sync status bar** — Replace sync error toasts with a persistent status widget showing ⟳ icon + "Syncing / Online / Offline" text
- [ ] **Ghost mode visual feedback** — Panels should dim to 25% opacity in ghost mode; ghost exit button should be the only clickable element

---

## Desktop Updater

- [ ] **Generate signing keypair** — Run `npx tauri signer generate` and update `pubkey` in `tauri.conf.json`; store private key in `TAURI_SIGNING_PRIVATE_KEY` GitHub secret
- [ ] **Enable updater artifacts** — Set `createUpdaterArtifacts: true` in `tauri.conf.json`

---

## Mobile

- [ ] **Tablet layout** — `tablet_home_screen.dart` needs full two-panel implementation per `docs/TABLET_UI_PLAN.md`
- [ ] **Background sync observer** — Ensure `sync_on_background_observer.dart` correctly triggers sync when app returns to foreground

---

## Backend Infrastructure

- [ ] **Dynamic CORS for tunnel** — Read `tunnel_domain` from `SystemSettings` DB row (not just env var) and add to CORS origins at runtime (`backend/app/main.py`)
- [ ] **Redis URL config property** — Add `redis_url` computed property to `Settings` (`backend/app/config.py`)
- [ ] **Device service async rewrite** — `device_service.py` must accept `db: AsyncSession`; first device auto-approved, subsequent devices get 6-char approval code (`backend/app/services/device_service.py`)

---

## Testing

- [ ] **Hub tests** — `tests/test_hub.py`: `SystemSettings` creation, `TokenBlacklistService` Redis/fallback, registration lock (first-user superuser, lock after first, unlock by admin), hub endpoint responses
- [ ] **Device service tests** — First device auto-approved, second device pending with 6-char code
- [ ] **Auth endpoint tests** — Rate limit headers present on login/register responses

---

## Integration Checklist (before v0.5.0 release)

- [ ] Auth overlay appears on first launch
- [ ] Can create account and sign in
- [ ] Ghost mode toggle reliable (no race condition)
- [ ] Ghost exit button works
- [ ] AI orb sends to `/ai/smart-action` and renders created blocks
- [ ] All settings tabs navigate correctly
- [ ] Crystallize theme has blur effects
- [ ] Triangle logo shows in orb
- [ ] Sync status bar shows correct state
- [ ] Backend tests pass: `pytest tests/ -v`
- [ ] Rust compiles: `cargo check` in `desktop/src-tauri/`
- [ ] Vite build succeeds: `npm run build` in `desktop/`
