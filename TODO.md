# Aion — Project TODO

> Tracks pending features, fixes, and improvements across all platforms.  
> Sources: `docs/plans/2026-03-09-aion-major-update-plan.md`, `docs/superpowers/plans/2026-03-22-hub-auto-setup.md`

---

## Priority Order

### P1 — Fix now (bugs / security / data integrity)

1. ~~**Block hard deletes**~~ — soft-delete + cascade already implemented ✓
2. ~~**Logout + token blacklist**~~ — Redis-backed blacklist + `/auth/logout` implemented ✓
3. ~~**Auth rate limiting**~~ — slowapi 10/min login, 5/min register via `get_real_ip` ✓
4. ~~**Ghost mode race condition**~~ — Rust is single source of truth; JS only updates visuals ✓
5. ~~**Settings tab navigation**~~ — `.active` class switching implemented ✓

### P2 — Backend foundations

6. ~~**SystemSettings model + migration**~~ — implemented (`20260322_0001`) ✓
7. ~~**Registration lock logic**~~ — first-user superuser + auto-lock in `register_user_with_lock` ✓
8. ~~**Hub endpoints**~~ — `/hub/status`, `/hub/registration-status`, `/hub/setup-complete`, lock/unlock, tunnel-config ✓
9. ~~**Real-IP utility**~~ — `backend/app/utils/request.py` with CF-Connecting-IP support ✓
10. ~~**Redis URL config property**~~ — `settings.redis_url` computed property ✓
11. ~~**Device service async rewrite**~~ — full async DB-backed implementation with 6-char approval codes ✓
12. ~~**Docker entrypoint**~~ — `entrypoint.sh` validates SECRET_KEY, waits for PG, runs migrations ✓

### P3 — Core user-facing features

13. ~~**Multi-method auth fields**~~ — `auth_provider`, `email_verified`, `oauth_provider_id` on User model ✓
14. ~~**First-time sign-in overlay**~~ — `#auth-overlay` in HTML, `showAuthOverlay`/`checkAuth` in JS ✓
15. ~~**Docker management Rust commands**~~ — `docker.rs`: check, install, start/stop compose, health ✓
16. ~~**Cloudflare tunnel Rust commands**~~ — `cloudflare.rs`: check, install, `start_quick_tunnel` ✓
17. ~~**HubSetupService state machine**~~ — `desktop/src/services/hub_setup.js` state machine ✓
18. ~~**Wizard HTML + CSS + main.js wiring**~~ — `#hub-wizard` overlay wired into startup ✓
19. ~~**AIBlockService + `/ai/smart-action`**~~ — backend service + endpoint implemented ✓
20. ~~**Desktop AI input → smart-action**~~ — `getSmartActionOrOllama()` tries backend then Ollama ✓

### P4 — Polish & infrastructure

21. ~~**Ghost mode exit button + visual feedback**~~ — `#ghost-exit-btn` SVG + `opacity:0.25` CSS ✓
22. ~~**AI provider settings UI**~~ — `#settings-pane-ai` with provider/model/key inputs ✓
23. ~~**Account settings pane**~~ — `#settings-pane-account` with sign out + manage devices ✓
24. ~~**Sync status bar**~~ — `#sync-status-bar` with `updateSyncStatus()` function ✓
25. ~~**Triangle logo in orb**~~ — faceted triangle SVG in `#orb` ✓
26. ~~**Crystallize theme blur**~~ — `backdrop-filter: blur(20px) saturate(1.5)` in overlay.css ✓
27. ~~**Native vibrancy**~~ — `window-vibrancy` crate applied in Rust setup for macOS + Windows ✓
28. ~~**Desktop updater signing**~~ — `createUpdaterArtifacts: true` in tauri.conf.json ✓
29. **Dynamic CORS for tunnel** — currently reads `tunnel_domain` from env var; could also read from `SystemSettings` DB row at runtime for live config changes without restart
30. ~~**Data reset button**~~ — `#btn-clear-data` → `clearData()` implemented ✓

### P5 — Testing & mobile

31. ~~**Hub tests**~~ — `tests/test_hub.py` (210 lines): SystemSettings, blacklist, registration lock, hub endpoints ✓
32. **Device service tests** — auto-approve first device, pending + 6-char code for second
33. **Auth endpoint tests** — rate limit headers present on login/register responses
34. **Tablet layout** — full two-panel Flutter implementation (`mobile/lib/features/home/tablet_home_screen.dart`)
35. **Background sync observer** — verify `sync_on_background_observer.dart` fires on foreground return

---

## Remaining Work

Only **5 items** remain open:

| # | Item | File | Effort |
|---|---|---|---|
| 29 | Dynamic CORS from DB | `backend/app/main.py` | Small |
| 32 | Device service tests | `backend/tests/` | Small |
| 33 | Auth endpoint rate-limit tests | `backend/tests/` | Small |
| 34 | Tablet two-panel layout | `mobile/lib/features/home/tablet_home_screen.dart` | Large |
| 35 | Background sync observer | `mobile/lib/core/widgets/sync_on_background_observer.dart` | Small |

### 29 — Dynamic CORS from DB

In `backend/app/main.py`, the CORS tunnel domain is read from env var at startup. To support live config changes, also read from `SystemSettings` via a middleware that adds the current `tunnel_domain` to allowed origins on each request.

### 32 — Device service tests

```python
# backend/tests/test_device_service.py
async def test_first_device_auto_approved(db_session):
    ...

async def test_second_device_pending_with_code(db_session):
    ...
```

### 33 — Auth endpoint rate-limit tests

```python
# backend/tests/test_auth_rate_limits.py
async def test_login_rate_limit_headers(client):
    # POST /auth/login → check X-RateLimit-* headers present

async def test_register_rate_limit_headers(client):
    # POST /auth/register → check X-RateLimit-* headers present
```

### 34 — Tablet two-panel layout

Per `docs/TABLET_UI_PLAN.md`: left rail (block tree), right panel (block detail), both visible simultaneously on landscape tablets. `tablet_home_screen.dart` currently has a stub.

### 35 — Background sync observer

Verify `sync_on_background_observer.dart` correctly calls the sync service when `AppLifecycleState.resumed` fires. May need to ensure a debounce so rapid foreground/background cycles don't spam the API.

---

## Integration Checklist (v0.5.0 release gate)

- [x] Auth overlay appears on first launch
- [x] Can create account and sign in
- [x] Ghost mode toggle reliable (Rust SSOT)
- [x] Ghost exit button works
- [x] AI orb sends to `/ai/smart-action` → renders created blocks
- [x] All settings tabs navigate correctly
- [x] Crystallize theme has blur effects
- [x] Triangle logo shows in orb
- [x] Sync status bar shows correct state
- [ ] Backend tests pass: `pytest tests/ -v`
- [ ] Rust compiles: `cargo check` in `desktop/src-tauri/`
- [ ] Vite build succeeds: `npm run build` in `desktop/`
