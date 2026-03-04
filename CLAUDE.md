# CLAUDE.md — Aion Codebase Guide

Aion is a **privacy-centric, AI-powered personal life management system** built as a monorepo with three platforms:

- **`backend/`** — FastAPI (Python 3.11+) REST API
- **`desktop/`** — Tauri 2 (Rust) + Vite (JavaScript) overlay app
- **`mobile/`** — Flutter (Dart) Android/iOS client
- **`docs/`** — Architecture and deployment documentation

All data stays on the local machine by default. Cloud access is optional via Cloudflare Tunnel.

---

## Project Structure

```
Aion/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point, middleware, health checks
│   │   ├── config.py            # Pydantic-settings config (env vars)
│   │   ├── api/v1/
│   │   │   ├── router.py        # Aggregates all endpoint routers
│   │   │   └── endpoints/       # auth, blocks, ai, ai_enhanced, voice, sync, devices, discovery
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business logic (25+ services)
│   │   └── db/                  # base.py (mixins), session.py (asyncpg)
│   ├── alembic/                 # DB migrations
│   ├── tests/                   # pytest test suite
│   ├── docker-compose.yml       # PostgreSQL, Qdrant, Redis
│   ├── Dockerfile               # Production container
│   └── requirements.txt
├── desktop/
│   ├── src-tauri/
│   │   ├── src/main.rs          # Rust: tray, screen capture, secure storage, shortcuts
│   │   ├── Cargo.toml
│   │   └── tauri.conf.json      # Window config, bundling, updater endpoints
│   ├── src/
│   │   ├── main.js              # Frontend entry point
│   │   └── services/            # audio, sync, local_db, secure_storage, screen_capture
│   └── package.json             # Vite + Tauri scripts
├── mobile/
│   ├── lib/
│   │   ├── main.dart            # App entry point
│   │   ├── app.dart             # MaterialApp + router setup
│   │   ├── core/                # API client, config, router, shared services
│   │   ├── data/                # Repository pattern + Isar models
│   │   └── features/            # auth, home, tasks (screen-by-screen)
│   └── pubspec.yaml
├── docs/                        # HTTPS, updater, Cloudflare, Android guides
└── .github/workflows/
    └── build-release.yml        # CI: Windows MSI, macOS DMG, Android APK
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Python 3.11, asyncio, Pydantic v2 |
| SQL Database | PostgreSQL 16 (asyncpg + SQLAlchemy 2 async) |
| Vector Database | Qdrant (semantic search, embeddings) |
| Local AI | Ollama (`llama3.2`, `nomic-embed-text`) |
| Database Migrations | Alembic |
| Desktop Framework | Tauri 2 (Rust backend, Vite JS frontend) |
| Mobile Framework | Flutter 3.22 + Riverpod + Isar |
| Voice | Whisper (STT), Edge TTS (TTS), openwakeword (wake detection) |
| Browser Automation | browser-use + Playwright |
| Service Discovery | zeroconf (mDNS) |
| Auth | JWT (PyJWT), bcrypt, optional Fernet field encryption |

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

### Database Models

All models inherit mixins from `app/db/base.py`:

- `UUIDMixin` — UUID string primary key (`id`)
- `TimestampMixin` — `created_at`, `updated_at` (auto-managed)
- `SyncMixin` — `sync_id`, `sync_version`, `local_updated_at`, `is_deleted`, `device_id` for offline-first multi-device sync

Always use soft deletes (`is_deleted = True`) for synced entities, never hard-delete.

### The Block Model

`Block` is the **core entity**. Everything in Aion is organized as nested Blocks.

- **Hierarchy**: dual approach — `parent_id` (adjacency list) + `path` (materialized path string, dot-separated IDs)
- **Depth**: tracked explicitly in `depth` column
- Sub-entities: `BlockField` (custom columns), `BlockEntry` (rows), `BlockContent` (rich text)
- Path updates for descendants must be done in the **service layer**, not model event listeners.

### Configuration

All configuration lives in `app/config.py` via `pydantic-settings`. Values come from environment variables or `.env`. Use the `settings` singleton imported from `app.config`.

Key settings to be aware of:
- `settings.ollama_url` — local Ollama endpoint
- `settings.qdrant_url` — vector DB URL
- `settings.database_url` — async PostgreSQL URL
- `settings.production` + `settings.require_https` — gate HTTPS enforcement
- `settings.data_encryption_key` — optional Fernet key for at-rest field encryption

### API Routes (all under `/api/v1`)

| Prefix | Module | Purpose |
|---|---|---|
| `/auth` | `auth.py` | Register, login, token refresh |
| `/blocks` | `blocks.py` | CRUD, tree, hierarchy, fields, entries |
| `/ai` | `ai.py` | Chat, search, automation |
| `/ai/v2` | `ai_enhanced.py` | Advanced AI features |
| `/voice` | `voice.py` | Speech input/output |
| `/sync` | `sync.py` | Device sync |
| `/devices` | `devices.py` | Device registration/management |
| `/discovery` | `discovery.py` | mDNS service discovery |

Special endpoints added directly to `main.py` (bypassing the router):
- `GET /api/v1/ai/graph` — Neural graph visualization
- `GET /api/v1/ai/graph-direct` — Duplicate path to avoid router caching issues

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
docker-compose up -d        # PostgreSQL, Qdrant, Redis
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

## Desktop — Key Conventions

### Architecture

The desktop is a **Tauri 2** app:
- **Rust backend** (`src-tauri/src/main.rs`): system integrations — OS keychain, screen capture, global shortcuts, tray icon, click-through overlay
- **JavaScript frontend** (`src/main.js`, `src/services/`): UI, communicates with Rust via Tauri IPC commands

### Tauri Commands (Rust → JS)

Rust `#[tauri::command]` functions exposed to JS:
- `secure_storage_get/set/delete/exists` — OS keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service)
- Screen capture commands
- Window management commands

Keyring service name: `com.aion.desktop`

### Window Configuration

The window is configured as a **transparent, decoration-less overlay** (see `tauri.conf.json`):
- Transparent, no decorations, skip taskbar
- Click-through mode can be toggled via global shortcut
- Tray-only when minimized

### Development

```bash
cd desktop
npm install
npm run tauri:dev      # Start dev mode with hot reload
```

### Build

```bash
npm run tauri:build                           # Current platform
npm run tauri:build:windows                  # x86_64 Windows MSI/NSIS
npm run tauri:build:macos-arm                # aarch64 macOS DMG
npm run tauri:build:linux                    # x86_64 Linux
```

Build artifacts land in `desktop/src-tauri/target/release/bundle/`.

---

## Mobile — Key Conventions

### Architecture

Flutter app using **feature-first** directory layout:

```
lib/
├── core/           # Shared: API client, router, services, widgets
├── data/           # Repository pattern + Isar offline models
└── features/       # auth/, home/, tasks/ — each has screens + widgets
```

### State Management

- **Riverpod** (`flutter_riverpod`, `riverpod_annotation`, code-gen via `riverpod_generator`)
- Use `ConsumerStatefulWidget` / `ConsumerWidget` in screens
- Providers live in service files or alongside their feature

### Local Database

**Isar 4.0.0-dev** for offline-first storage. Run code generation after modifying Isar models:

```bash
dart run build_runner build --delete-conflicting-outputs
```

### Networking

- **Dio** HTTP client wrapped in `core/api/api_client.dart`
- Server URL is persisted via `SharedPreferences` and configurable at runtime (for LAN vs. Cloudflare Tunnel)
- Android emulator connects via `10.0.2.2`; physical devices use the actual LAN IP
- WebSocket URL is auto-derived from the HTTP URL

### Code Generation

Required after modifying:
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

| Job | Runner | Output |
|---|---|---|
| `build-windows` | windows-latest | `.msi`, `.exe` (NSIS) |
| `build-macos` | macos-latest | `.dmg`, `.app` (aarch64) |
| `build-android` | ubuntu-latest | `.apk` (universal + split ABI) |
| `create-release` | ubuntu-latest | GitHub Release with all artifacts |

**Triggers**:
- Tag push (`v*`) — all jobs run automatically
- Manual dispatch — select which platforms to build

Releases require a `GITHUB_TOKEN` with `contents: write` permission (set in workflow).

---

## Key Architectural Decisions

1. **Local-first, privacy-first**: No mandatory cloud. PostgreSQL, Qdrant, and Ollama all run locally.

2. **Offline sync with `SyncMixin`**: Every synced entity has `sync_id`, `sync_version`, `is_deleted`, `device_id`. Soft deletes are mandatory for synced records.

3. **Materialized path for Block hierarchy**: `Block.path` stores dot-separated ancestor IDs. Always update descendant paths when reparenting a block.

4. **Ollama proxy in Rust**: The desktop's Rust backend proxies requests to Ollama to avoid CORS issues in Tauri's WebView.

5. **mDNS discovery**: `zeroconf` enables devices on the same LAN to auto-discover the backend server without manual IP configuration.

6. **Transparent overlay**: The desktop window is a fullscreen transparent overlay, primarily accessed via tray icon or global keyboard shortcut.

7. **Dual AI endpoint versions**: `/api/v1/ai` (v1) and `/api/v1/ai/v2` (enhanced) coexist to allow incremental migration.

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

# Ollama
OLLAMA_HOST=localhost        # Use 0.0.0.0 for LAN access
OLLAMA_PORT=11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Security
SECRET_KEY=change-this-in-production
DATA_ENCRYPTION_KEY=          # Optional Fernet key for at-rest encryption

# Production
PRODUCTION=false
REQUIRE_HTTPS=false
```

In production, `SECRET_KEY` must be set to a random value or startup fails. Generate with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Service Inventory (Backend)

| Service | Purpose |
|---|---|
| `ai_service.py` | Ollama chat, embeddings, vision |
| `auth_service.py` | User registration, JWT tokens, bcrypt |
| `block_service.py` | Block CRUD, tree operations, materialized paths |
| `browser_service.py` | Playwright browser automation |
| `device_service.py` | Device registration, management |
| `discovery_service.py` | mDNS/zeroconf service advertisement |
| `enhanced_voice_service.py` | Enhanced voice pipeline |
| `evaluation_service.py` | AI output evaluation |
| `field_encryption.py` | Fernet-based at-rest field encryption |
| `intent_service.py` | Natural language intent parsing |
| `memory_service.py` | Long-term memory / knowledge graph |
| `model_router.py` | Route requests to appropriate Ollama models |
| `persona_service.py` | AI persona management |
| `planning_service.py` | Goal and plan management |
| `proactive_service.py` | Background proactive AI suggestions |
| `prompt_service.py` | Prompt template management |
| `rag_service.py` | Retrieval-augmented generation |
| `realtime_conversation_service.py` | Streaming conversation |
| `realtime_voice_service.py` | Real-time voice streaming |
| `search_service.py` | Full-text + semantic hybrid search |
| `smart_model_router.py` | Intelligent model selection |
| `stt_service.py` | Speech-to-text (Whisper) |
| `study_service.py` | Learning and study tracking |
| `sync_service.py` | Multi-device data synchronization |
| `trigger_service.py` | Automation trigger execution |
| `user_profile_service.py` | User preference management |
| `vector_service.py` | Qdrant vector storage and semantic search |
| `voice_assistant_service.py` | Wake-word + full voice assistant pipeline |
| `voice_service.py` | Edge TTS, audio playback |

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

1. Add a `#[tauri::command]` function in `desktop/src-tauri/src/main.rs`
2. Register it in the `.invoke_handler(tauri::generate_handler![...])` builder
3. Call it from JavaScript via `import { invoke } from '@tauri-apps/api/core'`

### New Flutter screen

1. Create `mobile/lib/features/<feature>/<feature>_screen.dart`
2. Add the route in `mobile/lib/core/router.dart`
3. Add state via a Riverpod provider
4. Run `dart run build_runner build` if any generated code was changed

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
