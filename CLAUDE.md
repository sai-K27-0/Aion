# CLAUDE.md — Aion Codebase Guide

Aion is a **privacy-centric, AI-powered personal life management system** built as a monorepo with three platforms:

- **`backend/`** — FastAPI (Python 3.11+) REST API
- **`desktop/`** — Tauri 2 (Rust) + Vite (JavaScript) transparent overlay app
- **`mobile/`** — Flutter (Dart) Android/iOS client
- **`docs/`** — Architecture and deployment documentation

All data stays on the local machine by default. Cloud access is optional via Cloudflare Tunnel.  
Current version: **0.5.0** (consistent across all platforms).

---

## Project Structure

```
Aion/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point, middleware, health checks
│   │   ├── config.py            # Pydantic-settings config (env vars), version 0.5.0
│   │   ├── api/v1/
│   │   │   ├── router.py        # Aggregates all 10 endpoint routers
│   │   │   ├── deps.py          # Dependency injection for services
│   │   │   └── endpoints/       # 11 modules: auth, blocks, ai, ai_enhanced, voice,
│   │   │                        #   sync, devices, discovery, ai_setup, hub
│   │   ├── models/              # 8 SQLAlchemy ORM models
│   │   ├── schemas/             # 6 Pydantic request/response schema files
│   │   ├── services/            # 38 service files (~11,350 LOC of business logic)
│   │   ├── db/                  # base.py (mixins), session.py (asyncpg)
│   │   └── utils/               # request.py (real IP extraction)
│   ├── alembic/                 # DB migrations (9 versions)
│   │   └── versions/            # 20260201 → 20260322 (chronological)
│   ├── tests/                   # pytest test suite
│   ├── docker-compose.yml       # PostgreSQL 16, Qdrant, Redis 7
│   ├── Dockerfile               # Production container
│   ├── entrypoint.sh            # Container startup script
│   ├── Caddyfile                # Reverse proxy / TLS termination config
│   └── requirements.txt
├── desktop/
│   ├── src-tauri/
│   │   ├── src/
│   │   │   ├── main.rs          # Rust: tray, ghost mode, keychain, window, Ollama proxy
│   │   │   ├── docker.rs        # Docker management integration
│   │   │   └── cloudflare.rs    # Cloudflare Tunnel control
│   │   ├── capabilities/        # Tauri 2 capability definitions
│   │   ├── icons/               # Platform-specific app icons
│   │   ├── entitlements.plist   # macOS sandbox entitlements
│   │   ├── Cargo.toml
│   │   └── tauri.conf.json      # Window (1920×1080, transparent, always-on-top),
│   │                            #   bundling, updater endpoints
│   ├── src/
│   │   ├── main.js              # Frontend entry point
│   │   ├── services/            # 8 JS service modules (see Desktop section)
│   │   └── styles/              # main.css, calendar.css, overlay.css
│   ├── vite.config.js
│   ├── index.html
│   └── package.json             # Tauri 2, Vite 5
├── mobile/
│   ├── lib/
│   │   ├── main.dart            # App entry point
│   │   ├── app.dart             # MaterialApp + GoRouter setup
│   │   ├── core/                # API client, config, router, shared services
│   │   ├── data/                # Repository pattern + Isar offline models
│   │   └── features/            # auth/, home/, tasks/ (screen-by-screen)
│   ├── android/                 # Android Gradle config + build flavors
│   └── pubspec.yaml
├── docs/
│   ├── OLLAMA_AND_AI_SETUP.md
│   ├── HTTPS_AND_TLS_SETUP.md
│   ├── CLOUDFLARE_TUNNEL_SETUP.md
│   ├── DESKTOP_UPDATER.md
│   ├── RUN_ON_ANDROID_TAB_S10_FE.md
│   ├── TABLET_UI_PLAN.md
│   ├── plans/                   # Implementation roadmaps (2026-03-09 major update)
│   └── superpowers/             # Hub auto-setup specs and design docs
├── .github/
│   └── workflows/
│       └── build-release.yml    # CI: Windows MSI, macOS DMG, Android APK
├── start_aion.bat               # Windows one-click startup script
└── README.md
```

---

## Technology Stack

| Layer | Technology | Details |
|---|---|---|
| Backend API | FastAPI + Python 3.11+ | asyncio, Pydantic v2 |
| SQL Database | PostgreSQL 16 | asyncpg + SQLAlchemy 2 async |
| Vector Database | Qdrant | semantic search, embeddings |
| Cache / Queue | Redis 7 | session state, rate limiting |
| Local AI | Ollama | `llama3.2` (chat), `nomic-embed-text` (embeddings) |
| Cloud AI (optional) | OpenAI / Anthropic | API keys, switchable via `ai_provider` setting |
| Database Migrations | Alembic | auto-generated from SQLAlchemy models |
| Desktop Framework | Tauri 2 | Rust backend + Vite 5 JS frontend |
| Mobile Framework | Flutter 3.22+ | Riverpod state, Isar local DB |
| Voice (STT) | faster-whisper | local transcription |
| Voice (TTS) | Edge TTS / ElevenLabs | `en-US-AndrewNeural` default voice |
| Wake Detection | openwakeword | always-listening wake word |
| Browser Automation | browser-use + Playwright | Chromium-based automation |
| Web Search | DuckDuckGo + trafilatura | privacy-first search + scraping |
| Service Discovery | zeroconf (mDNS) | automatic LAN device discovery |
| Auth | JWT (PyJWT) + bcrypt | optional Fernet field encryption |
| Reverse Proxy / TLS | Caddy | configured via `backend/Caddyfile` |

---

## Backend — Key Conventions

### Architecture

The backend follows a strict layered pattern:

```
HTTP Request → Endpoint (api/v1/endpoints/) → Service (services/) → Model/DB
                                                     ↑
                                              Schema validation (schemas/)
```

- **Endpoints** handle routing, auth, rate limiting, and HTTP concerns only.
- **Services** contain all business logic. Never put business logic in endpoints.
- **Models** are SQLAlchemy ORM classes — one file per domain entity.
- **Schemas** are Pydantic models for input validation and response serialization.
- **`api/v1/deps.py`** provides dependency-injected service instances for endpoints.

### Database Models

All models inherit mixins from `app/db/base.py`:

- `UUIDMixin` — UUID string primary key (`id`)
- `TimestampMixin` — `created_at`, `updated_at` (auto-managed)
- `SyncMixin` — `sync_id`, `sync_version`, `local_updated_at`, `is_deleted`, `device_id` for offline-first multi-device sync

Always use soft deletes (`is_deleted = True`) for synced entities, never hard-delete.

**Current models (8 files):**

| Model | Key Fields |
|---|---|
| `user.py` | `email`, `username`, `hashed_password`, `auth_provider` (local/google/github), `email_verified`, `oauth_provider_id` |
| `block.py` | `name`, `parent_id`, `path` (materialized), `depth`, `position`, `block_type`, `properties` (JSONB) |
| `device.py` | `name`, `device_type`, `os`, `os_version`, `is_approved`, `user_id` |
| `conversation.py` | `user_id`, `messages` (JSON array) |
| `plan.py` | `title`, `goals`, `milestones` |
| `trigger.py` | `name`, `condition`, `action` |
| `device_ai_config.py` | Per-device AI provider / model configuration |
| `system_settings.py` | Global system-level settings |

### The Block Model

`Block` is the **core entity**. Everything in Aion is organized as nested Blocks.

- **Hierarchy**: dual approach — `parent_id` (adjacency list) + `path` (materialized path string, dot-separated IDs)
- **Depth**: tracked explicitly in `depth` column
- **Block types**: `default`, `database`, `document`, `folder`
- **Properties**: stored as JSONB for flexible schema
- Sub-entities: `BlockField` (custom columns), `BlockEntry` (rows), `BlockContent` (rich text)
- Path updates for descendants must be done in the **service layer**, not model event listeners.

### Configuration (`app/config.py`)

All configuration lives in `app/config.py` via `pydantic-settings`. Values come from environment variables or `.env`. Use the `settings` singleton imported from `app.config`.

Key settings groups:

| Group | Key Settings |
|---|---|
| App | `app_name`, `app_version = "0.5.0"`, `debug` |
| PostgreSQL | `postgres_host/port/user/password/db` |
| Qdrant | `qdrant_host/port`, `qdrant_collection = "aion_embeddings"` |
| Ollama | `ollama_host/port`, `ollama_model`, `ollama_embedding_model` |
| AI provider | `ai_provider` (`ollama`/`openai`/`anthropic`), `openai_api_key`, `anthropic_api_key` |
| OAuth | `google_client_id/secret`, `github_client_id/secret`, `oauth_redirect_base_url` |
| Security | `secret_key`, `access_token_expire_minutes = 30`, `refresh_token_expire_days = 7`, `data_encryption_key` |
| Networking | `cors_origins`, `tunnel_domain` (Cloudflare), `relay_url` (cross-network sync) |
| Redis | `redis_host/port` |
| Voice | `edge_tts_voice`, `elevenlabs_api_key`, `elevenlabs_voice_id` |
| Deployment | `production`, `require_https`, `data_dir`, `max_file_size_mb` |

### API Routes (all under `/api/v1`)

| Prefix | Module | Purpose |
|---|---|---|
| `/auth` | `auth.py` | Register, login, token refresh, logout, password change |
| `/blocks` | `blocks.py` | CRUD, tree, hierarchy, fields, entries |
| `/ai` | `ai.py` | Chat, search, automation, model management |
| `/ai/v2` | `ai_enhanced.py` | Advanced AI features |
| `/voice` | `voice.py` | STT, TTS, real-time WebSocket streaming |
| `/sync` | `sync.py` | Push/pull device sync, conflict resolution |
| `/devices` | `devices.py` | Device registration, approval, management |
| `/discovery` | `discovery.py` | mDNS service status |
| `/ai/setup` | `ai_setup.py` | Ollama status, model pull, AI provider config |
| `/hub` | `hub.py` | Hub orchestration / auto-setup flows |

Special endpoints registered directly in `main.py` (bypass router to avoid caching):
- `GET /api/v1/ai/graph` — Neural graph visualization via Qdrant
- `GET /api/v1/ai/graph-direct` — Duplicate path workaround for router caching

### Middleware Stack (`main.py`)

Applied in order:
1. `SecurityHeadersMiddleware` — X-Frame-Options, X-Content-Type-Options, CSP, HSTS
2. `HTTPSRedirectMiddleware` — HTTP → HTTPS in production
3. `CORSMiddleware` — Allows `localhost:1420/1421/3000/5173/8000`, `tauri://localhost`, configured Cloudflare domain
4. Rate limiting — 100 requests/minute default via `slowapi`

### Health Check Endpoints

- `GET /health` — Overall status + DB/Qdrant/Ollama component details
- `GET /health/ready` — Kubernetes readiness probe
- `GET /health/live` — Kubernetes liveness probe

### Naming Conventions (Python)

- Classes: `PascalCase` (`BlockService`, `AIService`)
- Functions/variables: `snake_case` (`create_block`, `get_ai_service`)
- Constants: `UPPER_SNAKE_CASE` (`KEYRING_SERVICE`)
- Private attributes: leading underscore (`_client`, `_cache`)
- Async functions for all I/O operations

### Code Quality Tools

```bash
black .           # Format
ruff check .      # Lint
mypy app/         # Type check
```

---

## Backend — Development Workflow

### Initial Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Edit with your settings
```

### Start Dependencies

```bash
docker-compose up -d        # PostgreSQL 16, Qdrant, Redis 7
```

### Run Migrations

```bash
alembic upgrade head
```

### Start the API

```bash
# Development (hot reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Create a New Migration

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

### Run Tests

```bash
pytest                              # All tests
pytest --cov=app --cov-report=html  # With coverage
pytest tests/test_ai_features.py -v # Specific file
```

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`

---

## Backend — Service Inventory (38 services)

| Service | Purpose |
|---|---|
| **Core AI** | |
| `ai_service.py` | Ollama chat, embeddings, vision; supports OpenAI/Anthropic fallback |
| `ai_block_service.py` | Smart block creation from natural language |
| `smart_model_router.py` | Intelligent model selection based on task complexity |
| `model_router.py` | Route requests to appropriate Ollama models |
| `model_recommendation_service.py` | Recommend optimal models for given tasks |
| **Voice Pipeline** | |
| `voice_service.py` | Edge TTS synthesis, audio playback |
| `stt_service.py` | Speech-to-text via faster-whisper |
| `enhanced_voice_service.py` | Enhanced multi-step voice pipeline |
| `voice_assistant_service.py` | Wake-word detection + full voice assistant pipeline |
| `realtime_voice_service.py` | Real-time streaming voice I/O |
| **Memory & Knowledge** | |
| `vector_service.py` | Qdrant vector storage and semantic search |
| `memory_service.py` | Long-term memory / knowledge graph |
| `persona_service.py` | AI persona management and context |
| **Search & RAG** | |
| `rag_service.py` | Retrieval-augmented generation |
| `search_service.py` | Full-text + semantic hybrid search |
| `intent_service.py` | Natural language intent parsing |
| **Automation** | |
| `action_executor.py` | Execute AI-suggested system actions |
| `action_service.py` | Action orchestration and queuing |
| `trigger_service.py` | Automation rule evaluation and execution |
| `planning_service.py` | Goal decomposition and plan management |
| `proactive_service.py` | Background proactive AI suggestions |
| `evaluation_service.py` | AI output quality evaluation |
| `browser_service.py` | Playwright browser automation |
| **Auth & Security** | |
| `auth_service.py` | User registration, JWT tokens, bcrypt, OAuth flows |
| `token_blacklist_service.py` | Revoked token tracking |
| `field_encryption.py` | Fernet-based at-rest field encryption |
| `device_approval_service.py` | Multi-device trust management |
| **Data Sync** | |
| `sync_service.py` | Multi-device sync, conflict resolution |
| **Infrastructure** | |
| `discovery_service.py` | mDNS/zeroconf service advertisement |
| `device_service.py` | Device registration and management |
| `ollama_setup_service.py` | Ollama installation, model pulling, health |
| `user_profile_service.py` | User preferences and profile |
| `realtime_conversation_service.py` | WebSocket streaming conversation |
| `prompt_service.py` | Prompt template management |
| `study_service.py` | Learning / spaced repetition tracking |
| `block_service.py` | Block CRUD, tree operations, materialized path updates |

---

## Backend — Schemas (6 files)

| File | Contents |
|---|---|
| `auth.py` | `UserRegister`, `UserLogin`, `Token`, `RefreshToken`, `ChangePassword` |
| `ai.py` | `ChatRequest`, `SearchRequest`, `PlanRequest`, chat/search responses |
| `ai_block.py` | `SmartActionRequest`, `SmartActionResponse` |
| `block.py` | `BlockCreate`, `BlockUpdate`, `BlockResponse`, `BlockFieldCreate`, `BlockEntryCreate` |
| `device.py` | `DeviceRegister`, `DeviceResponse` |
| `hub.py` | Hub setup request/response |

---

## Backend — Database Migrations (Alembic)

9 chronological versions in `backend/alembic/versions/`:

| Migration | Change |
|---|---|
| `20260201_0001` | Create `users` table |
| `20260201_0002` | Create AI tables (`conversations`, etc.) |
| `20260205_0001` | Create `devices` table |
| `20260209_0001` | Make `user.email` nullable (for OAuth) |
| `20260304_0001` | Add `device_approval` table |
| `20260309_1439` | Add OAuth fields (`auth_provider`, `email_verified`) |
| `20260310_1210` | Create `blocks` + related tables (`block_fields`, `block_entries`, etc.) |
| `20260321_1209` | Add `device_ai_config` table |
| `20260322_0001` | Add `system_settings` table |

Migration strategy: always auto-generate from models, never hand-write SQL.

---

## Desktop — Key Conventions

### Architecture

The desktop is a **Tauri 2** app consisting of:
- **Rust backend** (`src-tauri/src/`): system integrations — OS keychain, ghost/click-through mode, screen capture, tray icon, Docker management, Cloudflare Tunnel
- **JavaScript frontend** (`src/main.js`, `src/services/`): UI panels, communicates with Rust via Tauri IPC `invoke()`

**Rust source modules:**
- `main.rs` — Core: keychain, ghost mode, window management, Ollama proxy, tray
- `docker.rs` — Docker container lifecycle management
- `cloudflare.rs` — Cloudflare Tunnel start/stop control

### Tauri Commands (Rust → JS via `invoke()`)

**Secure Storage (OS Keychain):**
- `secure_storage_get(key)` → `Option<String>`
- `secure_storage_set(key, value)` → `Result<()>`
- `secure_storage_delete(key)` → `Result<()>`
- `secure_storage_exists(key)` → `Result<bool>`
- Keyring service name: `com.aion.desktop`

**Ghost / Click-Through Mode:**
- `toggle_click_through()` → `Result<bool>` — single source of truth stored in `static CLICK_THROUGH_ENABLED: AtomicBool`
- `set_click_through(enabled: bool)` → `Result<bool>`
- `get_click_through_state()` → `bool`
- Emits `click-through-changed` event to frontend on change

**Window Management:**
- `minimize_to_tray()`, `show_from_tray()`, `is_window_visible()`, `close_window()`, `exit_app()`

**Ollama Proxy:**
- Proxies Ollama at `http://127.0.0.1:11434` to avoid CORS in Tauri WebView
- Handles `/api/chat` with system + user message

### Window Configuration (`tauri.conf.json`)

The window is a **transparent, fullscreen, always-on-top overlay**:
- `1920×1080`, `transparent: true`, `decorations: false`, `skipTaskbar: true`, `alwaysOnTop: true`
- Starts without focus (`focus: false`); accessed via tray or global shortcut
- CSP allows `self`, `data:`, `blob:`, local HTTP/WebSocket
- Tray: right-click only; left-click ignored

### Desktop Frontend Services (`src/services/`)

| Module | Purpose |
|---|---|
| `local_db.js` | IndexedDB for offline block storage |
| `hub_setup.js` | Initial hub configuration flow |
| `secure_storage.js` | Wraps Tauri keyring `invoke()` calls |
| `audio_recorder.js` | Microphone capture |
| `audio_player.js` | Audio playback |
| `sync.js` | Multi-device sync logic |
| `screen_capture.js` | Screenshot functionality |
| `ai_setup.js` | Ollama/provider configuration UI logic |

### Desktop Styles

- `main.css` — Core application styles
- `calendar.css` — Calendar widget
- `overlay.css` — Glassmorphism, ghost mode, transparent panel styling

### Development

```bash
cd desktop
npm install
npm run tauri:dev      # Starts Vite dev server (port 1420) + Tauri
```

### Build

```bash
npm run tauri:build                           # Current platform
npm run tauri:build:windows                  # x86_64 Windows (.msi, .exe)
npm run tauri:build:macos                    # universal-apple-darwin (.dmg)
npm run tauri:build:linux                    # x86_64 Linux
```

Build artifacts: `desktop/src-tauri/target/release/bundle/`

---

## Mobile — Key Conventions

### Architecture

Flutter app using **feature-first** directory layout:

```
lib/
├── main.dart                # Bootstrap
├── app.dart                 # MaterialApp + GoRouter
├── core/
│   ├── api/api_client.dart  # Dio HTTP wrapper
│   ├── config.dart          # App config (server URL, etc.)
│   ├── router.dart          # GoRouter route definitions
│   ├── services/            # intent, isar, secure_storage, sync, voice
│   └── widgets/             # sync_on_background_observer.dart
├── data/
│   ├── models/              # block_model.dart (Isar @Collection)
│   └── repositories/        # block_repository.dart
└── features/
    ├── auth/server_connection_screen.dart   # Backend URL config
    ├── home/
    │   ├── home_screen.dart                 # Main UI (phone)
    │   └── tablet_home_screen.dart          # Tablet variant
    └── tasks/tasks_screen.dart
```

### State Management

- **Riverpod** (`flutter_riverpod: ^2.4.9`, `riverpod_annotation`, code-gen via `riverpod_generator`)
- Use `ConsumerStatefulWidget` / `ConsumerWidget` in screens
- Providers live in service files or alongside their feature

### Local Database

**Isar 3.1.0+** for offline-first storage. Run code generation after modifying any Isar `@Collection` model:

```bash
dart run build_runner build --delete-conflicting-outputs
```

### Networking

- **Dio** (`^5.4.0`) HTTP client wrapped in `core/api/api_client.dart`
- Server URL persisted via `SharedPreferences`; configurable at runtime (LAN IP vs. Cloudflare Tunnel)
- Android emulator: `10.0.2.2`; physical devices: LAN IP or tunnel domain
- WebSocket URL is auto-derived from the HTTP base URL
- Secure tokens stored via `flutter_secure_storage`

### Code Generation

Required after modifying any of:
- Isar models (`@Collection`)
- Freezed models (`@freezed`)
- JSON serializable models (`@JsonSerializable`)
- Riverpod providers (`@riverpod`)

```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs
```

### Build

```bash
flutter pub get
flutter build apk --release --flavor production --no-tree-shake-icons
flutter build apk --release --flavor production --split-per-abi   # Per ABI
```

---

## CI/CD

**GitHub Actions** (`.github/workflows/build-release.yml`):

| Job | Runner | Output | Requires |
|---|---|---|---|
| `build-windows` | windows-latest | `.msi`, `.exe` (NSIS), `.msi.zip` + `.sig` | `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` |
| `build-macos` | macos-latest | `.dmg`, `.app` (aarch64 + universal) | Same signing secrets |
| `build-android` | ubuntu-latest | `.apk` (universal + split ABI) | Android keystore secrets |
| `create-release` | ubuntu-latest | GitHub Release with all artifacts | `GITHUB_TOKEN` (contents: write) |

**Triggers**:
- Tag push (`v*`) — all jobs run automatically
- Manual dispatch — select which platforms to build

---

## Key Architectural Decisions

1. **Local-first, privacy-first**: No mandatory cloud. PostgreSQL, Qdrant, Redis, and Ollama all run locally via Docker Compose.

2. **Offline sync with `SyncMixin`**: Every synced entity has `sync_id`, `sync_version`, `is_deleted`, `device_id`. Soft deletes are mandatory — never hard-delete synced records.

3. **Materialized path for Block hierarchy**: `Block.path` stores dot-separated ancestor IDs for O(1) subtree queries. Always update descendant paths in the **service layer** when reparenting.

4. **Ollama proxy in Rust**: The desktop Rust backend proxies requests to Ollama at `127.0.0.1:11434` to avoid CORS restrictions in Tauri's WebView.

5. **mDNS discovery**: `zeroconf` enables devices on the same LAN to auto-discover the backend without manual IP configuration.

6. **Transparent overlay (Ghost Mode)**: The desktop window is a fullscreen transparent overlay with togglable click-through. Ghost mode state is the single source of truth in Rust (`AtomicBool`), not the JS frontend.

7. **Dual AI endpoint versions**: `/api/v1/ai` (v1) and `/api/v1/ai/v2` (enhanced) coexist to allow incremental migration.

8. **Multi-provider AI**: `ai_provider` setting switches between Ollama (local), OpenAI, or Anthropic. Per-device AI config supported via `DeviceAIConfig` model.

9. **Hub orchestration**: `/api/v1/hub` + `hub_setup.js` provide a guided first-run setup flow (Ollama install, model pull, user creation).

10. **Docker + Cloudflare managed from desktop**: `docker.rs` and `cloudflare.rs` allow the Tauri app to start/stop backend services and the tunnel directly from the tray.

---

## Environment Variables (Backend)

Copy `backend/.env.example` to `backend/.env`. Key variables:

```env
DEBUG=true

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=aion
POSTGRES_PASSWORD=aion_local_secret
POSTGRES_DB=aion

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Ollama
OLLAMA_HOST=localhost        # Use 0.0.0.0 for LAN access
OLLAMA_PORT=11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# AI Provider (ollama | openai | anthropic)
AI_PROVIDER=ollama
OPENAI_API_KEY=              # Optional
ANTHROPIC_API_KEY=           # Optional

# OAuth (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Security
SECRET_KEY=change-this-in-production
DATA_ENCRYPTION_KEY=          # Optional Fernet key for at-rest encryption

# Networking
TUNNEL_DOMAIN=                # Optional Cloudflare tunnel domain

# Production
PRODUCTION=false
REQUIRE_HTTPS=false
```

In production, `SECRET_KEY` must be set to a random value or startup fails. Generate with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Adding New Features — Checklist

### New API endpoint

1. Create or update a schema in `app/schemas/`
2. Add business logic to an existing service or create `app/services/<name>_service.py`
3. Add the endpoint in `app/api/v1/endpoints/<name>.py`
4. Register the router in `app/api/v1/router.py`
5. If a new model is needed, create it in `app/models/` and generate a migration:
   ```bash
   alembic revision --autogenerate -m "add <model>"
   alembic upgrade head
   ```

### New Tauri command

1. Add a `#[tauri::command]` function in `desktop/src-tauri/src/main.rs` (or in `docker.rs`/`cloudflare.rs` if appropriate)
2. Register it in the `.invoke_handler(tauri::generate_handler![...])` builder in `main.rs`
3. Call it from JavaScript via `import { invoke } from '@tauri-apps/api/core'`

### New Flutter screen

1. Create `mobile/lib/features/<feature>/<feature>_screen.dart`
2. Add the route in `mobile/lib/core/router.dart`
3. Add state via a Riverpod provider
4. Run `dart run build_runner build` if any generated code was changed

### New desktop JS service

1. Create `desktop/src/services/<name>.js`
2. Import and initialize in `desktop/src/main.js`

---

## Ports Reference

| Service | Port |
|---|---|
| Backend API | 8000 |
| PostgreSQL | 5432 |
| Qdrant REST | 6333 |
| Qdrant gRPC | 6334 |
| Redis | 6379 |
| Ollama | 11434 |
| Vite dev server | 1420 |

---

## Documentation (`docs/`)

| File | Contents |
|---|---|
| `OLLAMA_AND_AI_SETUP.md` | Ollama install, model pull, OpenAI/Anthropic switching, per-device AI config |
| `HTTPS_AND_TLS_SETUP.md` | Caddy TLS termination, certificate setup, `REQUIRE_HTTPS` flag |
| `CLOUDFLARE_TUNNEL_SETUP.md` | Cross-network access via Cloudflare Tunnel, `TUNNEL_DOMAIN` config |
| `DESKTOP_UPDATER.md` | Tauri updater setup, signing key generation, GitHub releases |
| `RUN_ON_ANDROID_TAB_S10_FE.md` | Android tablet deployment walkthrough |
| `TABLET_UI_PLAN.md` | Tablet-optimized layout strategy for Flutter |
| `plans/2026-03-09-aion-major-update-plan.md` | Ghost mode, OAuth, AI assistant, UI polish roadmap |
| `plans/2026-03-09-aion-major-update-design.md` | Technical design for the major update |
| `superpowers/plans/2026-03-22-hub-auto-setup.md` | Hub orchestration implementation plan |
| `superpowers/specs/2026-03-22-hub-auto-setup-design.md` | Hub technical design spec |
