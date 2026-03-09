# Aion Major Update — Design Document

**Date**: 2026-03-09
**Status**: Approved
**Scope**: Updater fix, multi-method auth, AI smart assistant, ghost mode fix, macOS transparency, icon consistency, settings fix, improvements

---

## 1. Updater Fix + CI

**Problem**: `createUpdaterArtifacts: false` in `tauri.conf.json` because the signing key is invalid.

**Solution**:
1. Generate a fresh minisign keypair locally via `npm run tauri signer generate`
2. Store private key as `TAURI_SIGNING_PRIVATE_KEY` GitHub secret
3. Update `tauri.conf.json`: set `createUpdaterArtifacts: true`, update `pubkey`
4. Existing CI pipeline already handles `.sig` generation and `latest.json` upload — no workflow changes

**Result**: Push a tag → CI builds → `latest.json` on GitHub → in-app updater works.

---

## 2. Account System — Multi-Method Auth

### First-Time Experience

Full-screen auth overlay with the Aion triangle logo. Three auth methods:

1. **Username + Password** — Create account or sign in. Self-hosted on backend PostgreSQL.
2. **Sign in with Google/GitHub** — OAuth2 flow via `authlib`. Backend handles callback.
3. **Pair Device** — Enter 6-character code from existing device. Uses `DeviceApprovalService`.

### Backend Changes

- Add `auth_provider` field to `User` model: `local` | `google` | `github`
- Add `email_verified` field + verification flow for local accounts
- Add `POST /auth/oauth/{provider}` — initiate OAuth flow
- Add `POST /auth/oauth/callback/{provider}` — handle OAuth callback, create/link user
- Add `POST /auth/logout` — JWT blacklist (Redis-backed, TTL = token remaining life)
- Add `POST /auth/forgot-password` + `POST /auth/reset-password`
- Fix device approval check at login (currently bypassed)
- Add `relay_url` config option for optional Cloudflare Tunnel cloud relay
- Sync service tries LAN first, falls back to relay URL

### Desktop Changes

- New `#auth-overlay` full-screen div, visible until authenticated
- Three cards/tabs: Local Auth, Social Login, Device Pair
- After successful auth: smooth fade-out → main overlay revealed
- Auth state in secure storage (OS keychain via Tauri)
- Token refresh on 401 responses

### Dependencies

- Backend: `authlib`, `httpx` (for OAuth), `redis` (for token blacklist)
- No new desktop dependencies

---

## 3. Ghost Mode — Reliable Click-Through

### Problem

Click-through toggle is unreliable. Race condition between CSS `pointer-events`, Tauri `setIgnoreCursorEvents`, and Rust `CLICK_THROUGH_ENABLED` state.

### Solution

**Single source of truth**: Rust `AtomicBool` is the master state.

**Sequence**:
1. User presses Alt+G (or clicks toggle)
2. Rust toggles `CLICK_THROUGH_ENABLED`
3. Rust calls `window.set_ignore_cursor_events(enabled)`
4. Rust emits `click-through-changed` event with new state
5. Frontend receives event → updates CSS class + visual indicators
6. Frontend NEVER directly calls `setIgnoreCursorEvents` — only Rust does

**Visual feedback**:
- Panels dim to 30% opacity in ghost mode
- Small triangle icon in corner with `pointer-events: auto` for exit

**Remove**:
- Frontend's duplicate `toggleClickThroughMode()` state management
- Direct `setIgnoreCursorEvents` calls from JS

---

## 4. macOS Transparency + Crystallize Theme

### macOS White Background Fix

Use Tauri 2's `window.set_effects()` API:
- macOS: `WindowEffect::Vibrancy` with `NSVisualEffectMaterialUnderWindowBackground`
- Windows: `Acrylic` effect (Windows 10+) or `Mica` (Windows 11)

### Crystallize Theme Enhancement

- All panels: `backdrop-filter: blur(20px) saturate(1.5)`
- Background colors: semi-transparent rgba (0.15-0.3 alpha)
- Panel borders: subtle glass edge effect (1px white @ 15% opacity)
- Native vibrancy provides true desktop blur-through

---

## 5. AI Smart Assistant — Autonomous Block Management

### Capabilities

1. **Context-aware**: Reads existing blocks, knows schedule, recognizes patterns
2. **Autonomous**: Creates blocks without confirmation, places in correct parent
3. **Scheduling**: Creates recurring blocks, sets timers, adds reminders

### Example

Input: "I have math homework every hour for 20 minutes, 10 sums"
AI: Checks blocks → finds/creates "Math" → creates "Homework - Mar 9" → creates 10 sub-blocks → sets recurring schedule

### Backend

- New `AIBlockService` integrating `AIService` + `BlockService` + `PlanningService`
- New endpoint `POST /api/v1/ai/smart-action`:
  - Input: `{ "message": "...", "context_block_id": optional }`
  - AI uses RAG to read existing blocks for context
  - Structured output (JSON mode) for block hierarchy planning
  - Creates blocks, sets schedules, returns summary
- New `BlockSchedule` model for recurring schedules (cron-like expressions)
- Provider-agnostic: Ollama, OpenAI, or Anthropic per user config

### Desktop

- AI orb chat sends to `/ai/smart-action`
- Response shows toast: "Created X blocks under [parent]"
- No confirmation dialog — acts and reports

### Settings

- AI Provider selector: Ollama (local/free) | OpenAI (API key) | Anthropic (API key)
- API key fields stored in OS keychain (secure storage)
- Model selection dropdown per provider

---

## 6. Icon/Logo Consistency

- Replace orb's snowflake/asterisk with the faceted triangle from `icons/icon.svg`
- Use same triangle in: auth overlay, tray icon, about screen
- Triangle recolors per theme via CSS filters or SVG fill variables

---

## 7. Settings Panel Fix

- Fix tab navigation between all panes (General, Pomodoro, Sync, AI, Updates, Data)
- Fix value persistence: write to localStorage AND sync to server
- Add new "AI Provider" pane with provider selector + API key fields
- Add "Account" section: change password, manage devices, logout
- Add account management for OAuth-linked accounts

---

## 8. Improvements

1. **Data reset tool**: "Reset All Data" in Settings → Data (clears IndexedDB + localStorage + secure storage)
2. **Sync status**: Replace "Sync failed" with informative status (last sync, pending count, retry timer)
3. **Block soft delete enforcement**: Fix Block model to use soft deletes (SyncMixin requires it)
4. **Token refresh reliability**: Fix automatic 401 → refresh → retry flow
5. **Keyboard shortcuts help**: Update `?` panel with all current shortcuts

---

## Architecture Summary

```
User opens Aion
  → Auth overlay (first time) or auto-login (returning user)
  → Main overlay with panels
  → AI orb: natural language → smart-action → blocks created
  → Sync: LAN first → Cloudflare Tunnel fallback
  → Ghost mode: Alt+G → Rust-driven click-through
  → Updater: checks GitHub releases → auto-update
```

## Priority Order

1. Ghost mode fix (unblocks daily use)
2. Account system (enables sync)
3. Updater fix (enables updates)
4. AI smart assistant (core feature)
5. macOS transparency (cross-platform polish)
6. Icon consistency (branding)
7. Settings fix (UX)
8. Improvements (maintenance)
