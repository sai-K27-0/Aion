# Aion Major Update — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical bugs (ghost mode, updater, sync), add multi-method auth with first-time sign-in overlay, build AI smart assistant for autonomous block creation, and polish themes/icons/settings.

**Architecture:** Fix-first approach — ghost mode → account system → updater → AI smart assistant → macOS transparency → icon → settings → improvements. Each task builds on the previous. Backend uses existing FastAPI layered architecture (endpoint → service → model). Desktop is Tauri 2 + vanilla JS.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL, Tauri 2 (Rust), Vite, vanilla JS, IndexedDB, Ollama/OpenAI/Anthropic APIs, OAuth2 (authlib)

---

## Task 1: Fix Ghost Mode — Single Source of Truth in Rust

**Files:**
- Modify: `desktop/src-tauri/src/main.rs:112-162` (click-through commands)
- Modify: `desktop/src/main.js:1676-1711` (toggleClickThroughMode)
- Modify: `desktop/src/styles/overlay.css:5065-5068` (click-through styles)
- Modify: `desktop/index.html` (add ghost mode exit button)

**Step 1: Fix Rust click-through to be the single source of truth**

In `main.rs`, the `toggle_click_through` function (line 112) should:
1. Toggle the `CLICK_THROUGH_ENABLED` AtomicBool
2. Call `window.set_ignore_cursor_events(enabled)` directly
3. Emit `click-through-changed` event with the new state

Current issue: The function toggles state and emits event, but the JS frontend ALSO calls `setIgnoreCursorEvents` independently, causing race conditions.

Fix `toggle_click_through` (line 112-146):
```rust
#[tauri::command]
async fn toggle_click_through(window: tauri::Window) -> Result<bool, String> {
    let was_enabled = CLICK_THROUGH_ENABLED.load(Ordering::SeqCst);
    let new_state = !was_enabled;
    CLICK_THROUGH_ENABLED.store(new_state, Ordering::SeqCst);

    // Rust is the ONLY place that controls cursor events
    window.set_ignore_cursor_events(new_state)
        .map_err(|e| format!("Failed to set cursor events: {}", e))?;

    // Notify frontend for visual updates only
    window.emit("click-through-changed", new_state)
        .map_err(|e| format!("Failed to emit event: {}", e))?;

    Ok(new_state)
}
```

Fix `set_click_through` (line 149-156) similarly — it should also call `set_ignore_cursor_events`.

**Step 2: Simplify frontend ghost mode handler**

In `main.js` at line 1676, replace `toggleClickThroughMode()` to be a pure visual handler that NEVER calls Tauri's `setIgnoreCursorEvents`:

```javascript
async function toggleClickThroughMode() {
    try {
        // Let Rust handle the actual cursor event toggling
        const newState = await invoke('toggle_click_through');
        applyGhostModeVisuals(newState);
    } catch (e) {
        console.error('Ghost mode toggle failed:', e);
    }
}

function applyGhostModeVisuals(enabled) {
    const toggle = document.getElementById('click-through-toggle');
    if (enabled) {
        document.body.classList.add('click-through-mode');
        if (toggle) toggle.classList.add('active');
        showToast('Ghost mode enabled', 'info');
    } else {
        document.body.classList.remove('click-through-mode');
        if (toggle) toggle.classList.remove('active');
        showToast('Ghost mode disabled', 'info');
    }
}
```

Update the `toggle-ghost` event listener (line 5027) to call `toggleClickThroughMode()`.

Update the `click-through-changed` Tauri event listener to call `applyGhostModeVisuals(payload)`.

**Step 3: Add ghost mode exit button**

In `index.html`, add a small always-clickable triangle icon in the bottom-left corner:

```html
<div id="ghost-exit-btn" class="ghost-exit-btn hidden" style="pointer-events: auto !important;">
    <svg width="24" height="24" viewBox="0 0 24 24">
        <polygon points="12,2 22,20 2,20" fill="var(--accent-color)" opacity="0.8"/>
    </svg>
</div>
```

In `overlay.css`, add:
```css
.ghost-exit-btn {
    position: fixed;
    bottom: 16px;
    left: 16px;
    z-index: 99999;
    cursor: pointer;
    pointer-events: auto !important;
    opacity: 0.7;
    transition: opacity 0.2s;
}
.ghost-exit-btn:hover { opacity: 1; }
body.click-through-mode .ghost-exit-btn { display: block; }
body:not(.click-through-mode) .ghost-exit-btn { display: none; }
```

Update ghost mode visuals in JS to show/hide this button.

**Step 4: Improve ghost mode visual feedback**

Update the click-through CSS (overlay.css line 5065):
```css
body.click-through-mode {
    pointer-events: none;
}
body.click-through-mode * {
    pointer-events: none;
}
body.click-through-mode .ghost-exit-btn,
body.click-through-mode .ghost-exit-btn * {
    pointer-events: auto !important;
}
body.click-through-mode .panel-view,
body.click-through-mode .focus-panel,
body.click-through-mode .orb {
    opacity: 0.25;
    transition: opacity 0.3s ease;
}
```

**Step 5: Test ghost mode**

Manual test in Vite dev server:
1. Open app in browser → press Alt+G (or click toggle) → panels should dim to 25%
2. Ghost exit button should appear in bottom-left
3. Click ghost exit button → should disable ghost mode
4. All panels return to full opacity

**Step 6: Commit**

```bash
git add desktop/src-tauri/src/main.rs desktop/src/main.js desktop/src/styles/overlay.css desktop/index.html
git commit -m "fix: ghost mode — single source of truth in Rust, reliable click-through"
```

---

## Task 2: Account System — Backend Auth Enhancements

**Files:**
- Modify: `backend/app/models/user.py:16-43` (add auth_provider, email_verified fields)
- Modify: `backend/app/services/auth_service.py:25-228` (add OAuth, logout, password reset)
- Modify: `backend/app/api/v1/endpoints/auth.py:21-162` (add new endpoints)
- Modify: `backend/app/schemas/auth.py` (add OAuth schemas)
- Modify: `backend/app/config.py:89-92` (add OAuth config)
- Modify: `backend/app/api/v1/router.py:12-16` (already registered)
- Create: `backend/alembic/versions/xxxx_add_auth_provider.py` (migration)

**Step 1: Add auth_provider and email_verified fields to User model**

In `backend/app/models/user.py`, add after line 37:
```python
    # Auth provider: "local", "google", "github"
    auth_provider: Mapped[str] = mapped_column(
        String(20), default="local", server_default="local"
    )
    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # OAuth provider user ID (for Google/GitHub)
    oauth_provider_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
```

**Step 2: Add OAuth and logout config**

In `backend/app/config.py`, add after line 92:
```python
    # OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    oauth_redirect_base_url: str = "http://localhost:8000"

    # Token blacklist (in-memory for now, Redis later)
    # relay_url for optional cloud sync
    relay_url: Optional[str] = None
```

**Step 3: Add auth schemas**

In `backend/app/schemas/auth.py`, add:
```python
class OAuthInitRequest(BaseModel):
    provider: str  # "google" or "github"
    redirect_uri: Optional[str] = None

class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: Optional[str] = None

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
```

**Step 4: Add logout endpoint with token blacklist**

In `auth_service.py`, add a simple in-memory blacklist (upgrade to Redis later):

```python
# Module-level token blacklist (in-memory)
_token_blacklist: set[str] = set()

class AuthService:
    # ... existing code ...

    @staticmethod
    def blacklist_token(jti: str):
        """Add a token JTI to the blacklist."""
        _token_blacklist.add(jti)

    @staticmethod
    def is_token_blacklisted(jti: str) -> bool:
        """Check if a token is blacklisted."""
        return jti in _token_blacklist

    async def logout(self, token: str) -> bool:
        """Blacklist the current access token."""
        payload = self.decode_token(token)
        if payload and payload.jti:
            self.blacklist_token(payload.jti)
            return True
        return False
```

Update `decode_token` (line 80) to check blacklist:
```python
    @staticmethod
    def decode_token(token: str) -> Optional[TokenPayload]:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
            token_data = TokenPayload(**payload)
            # Check blacklist
            if token_data.jti and AuthService.is_token_blacklisted(token_data.jti):
                return None
            return token_data
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None
```

**Step 5: Add logout and OAuth stubs to auth endpoints**

In `backend/app/api/v1/endpoints/auth.py`, add:
```python
@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Logout and blacklist the current token."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "")
    auth_service = AuthService(db)
    await auth_service.logout(token)
    return Response(status_code=204)

@router.post("/oauth/{provider}")
async def oauth_init(
    provider: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Initiate OAuth flow (Google/GitHub). Returns redirect URL."""
    # TODO: Implement with authlib when OAuth credentials are configured
    raise HTTPException(status_code=501, detail=f"OAuth with {provider} not yet configured. Set GOOGLE_CLIENT_ID/GITHUB_CLIENT_ID in environment.")

@router.post("/oauth/callback/{provider}")
async def oauth_callback(
    provider: str,
    body: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Handle OAuth callback. Creates/links user account."""
    raise HTTPException(status_code=501, detail=f"OAuth with {provider} not yet configured.")
```

**Step 6: Generate migration**

```bash
cd backend
alembic revision --autogenerate -m "add auth_provider email_verified oauth_provider_id to user"
alembic upgrade head
```

**Step 7: Commit**

```bash
git add backend/app/models/user.py backend/app/services/auth_service.py backend/app/api/v1/endpoints/auth.py backend/app/schemas/ backend/app/config.py backend/alembic/
git commit -m "feat: add multi-method auth — logout, OAuth stubs, auth_provider field"
```

---

## Task 3: Account System — Desktop Auth Overlay

**Files:**
- Modify: `desktop/index.html:807+` (add auth overlay before settings)
- Modify: `desktop/src/main.js:4971+` (add auth check on init)
- Modify: `desktop/src/styles/overlay.css` (add auth overlay styles)
- Modify: `desktop/src/services/secure_storage.js:114-142` (use existing auth methods)

**Step 1: Add auth overlay HTML**

In `desktop/index.html`, add before the settings panel (before line 807):

```html
<!-- Auth Overlay - shown on first launch -->
<div id="auth-overlay" class="auth-overlay hidden">
    <div class="auth-card">
        <div class="auth-logo">
            <svg width="64" height="64" viewBox="0 0 512 512">
                <!-- Triangle logo from icon.svg -->
                <defs>
                    <linearGradient id="auth-grad-1" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#00D9FF"/>
                        <stop offset="100%" style="stop-color:#3A7BC8"/>
                    </linearGradient>
                </defs>
                <polygon points="256,60 460,420 52,420" fill="url(#auth-grad-1)" opacity="0.9"/>
                <polygon points="256,60 460,420 256,350" fill="#5BA3E6" opacity="0.7"/>
                <polygon points="256,60 52,420 256,350" fill="#00D9FF" opacity="0.5"/>
            </svg>
            <h1>Aion</h1>
        </div>

        <div class="auth-tabs">
            <button class="auth-tab active" data-tab="signin">Sign In</button>
            <button class="auth-tab" data-tab="signup">Create Account</button>
            <button class="auth-tab" data-tab="pair">Pair Device</button>
        </div>

        <!-- Sign In -->
        <div id="auth-signin" class="auth-pane">
            <input type="text" id="auth-username" placeholder="Username or email" autocomplete="username">
            <input type="password" id="auth-password" placeholder="Password" autocomplete="current-password">
            <button id="auth-signin-btn" class="auth-btn primary">Sign In</button>
            <div class="auth-divider"><span>or</span></div>
            <button id="auth-google-btn" class="auth-btn social" disabled>
                <span>Sign in with Google</span>
            </button>
            <button id="auth-github-btn" class="auth-btn social" disabled>
                <span>Sign in with GitHub</span>
            </button>
        </div>

        <!-- Create Account -->
        <div id="auth-signup" class="auth-pane hidden">
            <input type="text" id="auth-new-username" placeholder="Username" autocomplete="username">
            <input type="email" id="auth-new-email" placeholder="Email" autocomplete="email">
            <input type="password" id="auth-new-password" placeholder="Password" autocomplete="new-password">
            <input type="password" id="auth-confirm-password" placeholder="Confirm password" autocomplete="new-password">
            <button id="auth-signup-btn" class="auth-btn primary">Create Account</button>
        </div>

        <!-- Pair Device -->
        <div id="auth-pair" class="auth-pane hidden">
            <p class="auth-hint">Enter the 6-character code from your other device:</p>
            <input type="text" id="auth-pair-code" placeholder="ABC123" maxlength="6" class="auth-code-input">
            <button id="auth-pair-btn" class="auth-btn primary">Pair Device</button>
        </div>

        <div id="auth-error" class="auth-error hidden"></div>
        <div id="auth-loading" class="auth-loading hidden">Connecting...</div>
    </div>
</div>
```

**Step 2: Add auth overlay CSS**

In `overlay.css`, add auth overlay styles:

```css
/* Auth Overlay */
.auth-overlay {
    position: fixed;
    inset: 0;
    z-index: 100000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(20px);
    animation: authFadeIn 0.5s ease;
}
.auth-overlay.hidden { display: none; }
.auth-overlay.fade-out {
    animation: authFadeOut 0.5s ease forwards;
}

@keyframes authFadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes authFadeOut { from { opacity: 1; } to { opacity: 0; } }

.auth-card {
    width: 380px;
    padding: 40px;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
}

.auth-logo {
    text-align: center;
    margin-bottom: 32px;
}
.auth-logo h1 {
    color: #fff;
    font-size: 28px;
    margin-top: 12px;
    letter-spacing: 4px;
}

.auth-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 24px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 4px;
}
.auth-tab {
    flex: 1;
    padding: 8px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.5);
    cursor: pointer;
    border-radius: 6px;
    font-size: 13px;
    transition: all 0.2s;
}
.auth-tab.active {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
}

.auth-pane input {
    width: 100%;
    padding: 12px 16px;
    margin-bottom: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.05);
    color: #fff;
    font-size: 14px;
    outline: none;
    box-sizing: border-box;
}
.auth-pane input:focus {
    border-color: var(--accent-color, #00D9FF);
}
.auth-pane input::placeholder {
    color: rgba(255, 255, 255, 0.3);
}

.auth-btn {
    width: 100%;
    padding: 12px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    margin-bottom: 8px;
    transition: all 0.2s;
}
.auth-btn.primary {
    background: var(--accent-color, #00D9FF);
    color: #000;
    font-weight: 600;
}
.auth-btn.primary:hover { opacity: 0.9; }
.auth-btn.social {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.1);
}
.auth-btn.social:hover { background: rgba(255, 255, 255, 0.15); }
.auth-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.auth-divider {
    text-align: center;
    margin: 16px 0;
    position: relative;
}
.auth-divider::before,
.auth-divider::after {
    content: '';
    position: absolute;
    top: 50%;
    width: 40%;
    height: 1px;
    background: rgba(255, 255, 255, 0.1);
}
.auth-divider::before { left: 0; }
.auth-divider::after { right: 0; }
.auth-divider span { color: rgba(255, 255, 255, 0.3); font-size: 12px; }

.auth-code-input {
    text-align: center;
    font-size: 24px !important;
    letter-spacing: 8px;
    text-transform: uppercase;
}

.auth-error {
    color: #ff6b6b;
    font-size: 13px;
    text-align: center;
    margin-top: 12px;
}
.auth-error.hidden { display: none; }

.auth-loading { text-align: center; color: rgba(255, 255, 255, 0.5); margin-top: 12px; }
.auth-loading.hidden { display: none; }

.auth-hint {
    color: rgba(255, 255, 255, 0.6);
    font-size: 13px;
    margin-bottom: 16px;
    text-align: center;
}
```

**Step 3: Add auth logic to main.js**

Add auth initialization to `init()` function (around line 4971):

```javascript
// Auth state
let isAuthenticated = false;

async function checkAuth() {
    const token = await SecureStorage.getAccessToken();
    if (token) {
        // Verify token is still valid by calling /auth/me
        try {
            const headers = await syncService.getAuthHeaders();
            const resp = await fetch(`${state.serverUrl}/auth/me`, { headers });
            if (resp.ok) {
                isAuthenticated = true;
                return true;
            }
        } catch (e) {
            // Server not reachable — allow offline mode if we have tokens
            isAuthenticated = true;
            return true;
        }
    }
    return false;
}

async function showAuthOverlay() {
    const overlay = document.getElementById('auth-overlay');
    overlay.classList.remove('hidden');

    // Tab switching
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.auth-pane').forEach(p => p.classList.add('hidden'));
            tab.classList.add('active');
            document.getElementById(`auth-${tab.dataset.tab}`).classList.remove('hidden');
        });
    });

    // Sign In
    document.getElementById('auth-signin-btn').addEventListener('click', handleSignIn);
    document.getElementById('auth-password').addEventListener('keydown', e => {
        if (e.key === 'Enter') handleSignIn();
    });

    // Create Account
    document.getElementById('auth-signup-btn').addEventListener('click', handleSignUp);

    // Pair Device
    document.getElementById('auth-pair-btn').addEventListener('click', handlePairDevice);
}

async function handleSignIn() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');
    const loadingEl = document.getElementById('auth-loading');

    if (!username || !password) {
        errorEl.textContent = 'Please enter username and password';
        errorEl.classList.remove('hidden');
        return;
    }

    errorEl.classList.add('hidden');
    loadingEl.classList.remove('hidden');

    try {
        const resp = await fetch(`${state.serverUrl}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || 'Login failed');
        }

        const data = await resp.json();
        await SecureStorage.setAccessToken(data.access_token);
        await SecureStorage.setRefreshToken(data.refresh_token);
        if (data.user_id) await SecureStorage.setUserId(data.user_id);

        isAuthenticated = true;
        dismissAuthOverlay();
    } catch (e) {
        errorEl.textContent = e.message || 'Connection failed. Is the server running?';
        errorEl.classList.remove('hidden');
    } finally {
        loadingEl.classList.add('hidden');
    }
}

async function handleSignUp() {
    const username = document.getElementById('auth-new-username').value.trim();
    const email = document.getElementById('auth-new-email').value.trim();
    const password = document.getElementById('auth-new-password').value;
    const confirm = document.getElementById('auth-confirm-password').value;
    const errorEl = document.getElementById('auth-error');
    const loadingEl = document.getElementById('auth-loading');

    if (!username || !password) {
        errorEl.textContent = 'Username and password required';
        errorEl.classList.remove('hidden');
        return;
    }
    if (password !== confirm) {
        errorEl.textContent = 'Passwords do not match';
        errorEl.classList.remove('hidden');
        return;
    }

    errorEl.classList.add('hidden');
    loadingEl.classList.remove('hidden');

    try {
        const resp = await fetch(`${state.serverUrl}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email: email || undefined, password })
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || 'Registration failed');
        }

        // Auto-login after registration
        await handleSignIn();
    } catch (e) {
        errorEl.textContent = e.message || 'Connection failed';
        errorEl.classList.remove('hidden');
        loadingEl.classList.add('hidden');
    }
}

async function handlePairDevice() {
    const code = document.getElementById('auth-pair-code').value.trim().toUpperCase();
    const errorEl = document.getElementById('auth-error');

    if (code.length !== 6) {
        errorEl.textContent = 'Please enter a 6-character code';
        errorEl.classList.remove('hidden');
        return;
    }

    // Use existing device approval service
    try {
        const deviceId = await SecureStorage.getOrCreateDeviceId();
        const resp = await fetch(`${state.serverUrl}/sync/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, approval_code: code })
        });

        if (!resp.ok) throw new Error('Invalid code or device not found');

        const data = await resp.json();
        if (data.access_token) {
            await SecureStorage.setAccessToken(data.access_token);
            await SecureStorage.setRefreshToken(data.refresh_token);
            isAuthenticated = true;
            dismissAuthOverlay();
        }
    } catch (e) {
        errorEl.textContent = e.message;
        errorEl.classList.remove('hidden');
    }
}

function dismissAuthOverlay() {
    const overlay = document.getElementById('auth-overlay');
    overlay.classList.add('fade-out');
    setTimeout(() => {
        overlay.classList.add('hidden');
        overlay.classList.remove('fade-out');
        // Initialize sync after auth
        initOfflineSync();
    }, 500);
}
```

Update `init()` to check auth:
```javascript
async function init() {
    initEls();
    load();
    await initSecurity();
    initEvents();
    applyTheme(state.theme);

    // Check auth — show overlay if not authenticated
    const authed = await checkAuth();
    if (!authed) {
        showAuthOverlay();
    } else {
        initOfflineSync();
    }

    document.body.classList.add('overlay-ready');
}
```

**Step 4: Commit**

```bash
git add desktop/index.html desktop/src/main.js desktop/src/styles/overlay.css
git commit -m "feat: add auth overlay — sign in, create account, pair device"
```

---

## Task 4: Fix Updater — Generate Signing Key + Re-enable

**Files:**
- Modify: `desktop/src-tauri/tauri.conf.json` (set createUpdaterArtifacts: true, update pubkey)

**Step 1: Generate signing keypair**

```bash
cd desktop
npx tauri signer generate -w ../tauri-signing-key.key
```

This outputs a public key. Copy it.

**Step 2: Update tauri.conf.json**

Set `createUpdaterArtifacts` to `true` and update the `pubkey`:
```json
"createUpdaterArtifacts": true
```

Update `plugins.updater.pubkey` with the new public key.

**Step 3: Note for user**

The private key must be added to GitHub Secrets as `TAURI_SIGNING_PRIVATE_KEY` and the password as `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` before CI will work. This is a manual step.

**Step 4: Commit**

```bash
git add desktop/src-tauri/tauri.conf.json
git commit -m "fix: re-enable updater artifacts with new signing key"
```

---

## Task 5: AI Smart Assistant — Backend AIBlockService

**Files:**
- Create: `backend/app/services/ai_block_service.py`
- Create: `backend/app/schemas/ai_block.py`
- Modify: `backend/app/api/v1/endpoints/ai.py` (add smart-action endpoint)
- Modify: `backend/app/config.py:89-92` (already has API key fields)

**Step 1: Create AI block schemas**

Create `backend/app/schemas/ai_block.py`:
```python
from pydantic import BaseModel
from typing import Optional

class SmartActionRequest(BaseModel):
    message: str
    context_block_id: Optional[str] = None

class CreatedBlockInfo(BaseModel):
    id: str
    name: str
    parent_name: Optional[str] = None
    block_type: str = "default"
    depth: int = 0

class SmartActionResponse(BaseModel):
    action_taken: str
    blocks_created: list[CreatedBlockInfo] = []
    summary: str
```

**Step 2: Create AIBlockService**

Create `backend/app/services/ai_block_service.py`:
```python
"""AI-powered autonomous block creation service."""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIService
from app.services.block_service import BlockService
from app.models.block import Block
from app.schemas.ai_block import SmartActionResponse, CreatedBlockInfo

logger = logging.getLogger(__name__)

BLOCK_PLANNING_PROMPT = """You are Aion's AI assistant. The user wants you to create blocks (tasks/items) in their life management system.

Analyze the user's request and return a JSON plan for blocks to create.

Current date/time: {now}

Existing top-level blocks:
{existing_blocks}

Return ONLY valid JSON in this format:
{{
    "action": "create_blocks",
    "summary": "Brief description of what you're creating",
    "blocks": [
        {{
            "name": "Block name",
            "parent_name": "Name of existing parent block to put this under (or null for root)",
            "block_type": "task|note|project|default",
            "description": "Optional description",
            "children": [
                {{
                    "name": "Child block name",
                    "block_type": "task",
                    "description": "Optional"
                }}
            ]
        }}
    ]
}}

Think about:
- Where this logically belongs in the user's block hierarchy
- Whether to create a new parent or use an existing one
- Breaking work into sensible sub-tasks
- Using appropriate block types
"""


class AIBlockService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIService()
        self.block_service = BlockService(db)

    async def smart_action(
        self, user_id: str, message: str, context_block_id: Optional[str] = None
    ) -> SmartActionResponse:
        """Process a natural language request and create blocks autonomously."""

        # Get existing blocks for context
        existing_blocks = await self._get_block_context(user_id, context_block_id)

        # Ask AI to plan the block creation
        prompt = BLOCK_PLANNING_PROMPT.format(
            now=datetime.now().strftime("%Y-%m-%d %H:%M"),
            existing_blocks=existing_blocks
        )

        ai_response = await self.ai_service.chat(
            message=message,
            system_prompt=prompt,
            user_id=user_id
        )

        # Parse the AI's JSON plan
        plan = self._parse_plan(ai_response)
        if not plan:
            return SmartActionResponse(
                action_taken="chat",
                summary=ai_response,
                blocks_created=[]
            )

        # Execute the plan — create blocks
        created = await self._execute_plan(user_id, plan, context_block_id)

        return SmartActionResponse(
            action_taken="create_blocks",
            blocks_created=created,
            summary=plan.get("summary", f"Created {len(created)} blocks")
        )

    async def _get_block_context(
        self, user_id: str, context_block_id: Optional[str] = None
    ) -> str:
        """Get existing blocks as context for the AI."""
        try:
            from sqlalchemy import select
            query = select(Block).where(
                Block.depth <= 1,
                Block.is_deleted == False
            ).order_by(Block.position).limit(50)

            result = await self.db.execute(query)
            blocks = result.scalars().all()

            if not blocks:
                return "No existing blocks yet."

            lines = []
            for b in blocks:
                prefix = "  " * b.depth
                lines.append(f"{prefix}- {b.name} (type: {b.block_type}, id: {b.id})")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting block context: {e}")
            return "Could not load existing blocks."

    def _parse_plan(self, ai_response: str) -> Optional[dict]:
        """Extract JSON plan from AI response."""
        try:
            # Try direct JSON parse
            return json.loads(ai_response)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        match = re.search(r'\{[^{}]*"blocks"[^{}]*\[.*?\]\s*\}', ai_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    async def _execute_plan(
        self, user_id: str, plan: dict, context_block_id: Optional[str] = None
    ) -> list[CreatedBlockInfo]:
        """Create blocks according to the AI's plan."""
        created = []

        for block_spec in plan.get("blocks", []):
            parent_id = context_block_id

            # Find or use existing parent
            if block_spec.get("parent_name") and not parent_id:
                parent_id = await self._find_block_by_name(block_spec["parent_name"])

            # Create the block
            block = await self.block_service.create_block(
                name=block_spec["name"],
                block_type=block_spec.get("block_type", "default"),
                description=block_spec.get("description"),
                parent_id=parent_id,
                properties={"created_by": "ai"}
            )

            created.append(CreatedBlockInfo(
                id=block.id,
                name=block.name,
                parent_name=block_spec.get("parent_name"),
                block_type=block.block_type,
                depth=block.depth
            ))

            # Create children
            for child_spec in block_spec.get("children", []):
                child = await self.block_service.create_block(
                    name=child_spec["name"],
                    block_type=child_spec.get("block_type", "task"),
                    description=child_spec.get("description"),
                    parent_id=block.id,
                    properties={"created_by": "ai"}
                )
                created.append(CreatedBlockInfo(
                    id=child.id,
                    name=child.name,
                    parent_name=block.name,
                    block_type=child.block_type,
                    depth=child.depth
                ))

        await self.db.commit()
        return created

    async def _find_block_by_name(self, name: str) -> Optional[str]:
        """Find a block ID by name (case-insensitive)."""
        from sqlalchemy import select, func
        query = select(Block.id).where(
            func.lower(Block.name) == name.lower(),
            Block.is_deleted == False
        ).limit(1)
        result = await self.db.execute(query)
        row = result.scalar_one_or_none()
        return row if row else None
```

**Step 3: Add smart-action endpoint**

In `backend/app/api/v1/endpoints/ai.py`, add:
```python
from app.services.ai_block_service import AIBlockService
from app.schemas.ai_block import SmartActionRequest, SmartActionResponse

@router.post("/smart-action", response_model=SmartActionResponse)
async def smart_action(
    body: SmartActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """AI autonomous action — creates blocks from natural language."""
    service = AIBlockService(db)
    return await service.smart_action(
        user_id=current_user.id,
        message=body.message,
        context_block_id=body.context_block_id
    )
```

**Step 4: Update desktop AI input to use smart-action**

In `desktop/src/main.js`, update the `sendAiQuery()` function to call `/ai/smart-action`:

```javascript
async function sendAiQuery() {
    const text = els.aiInput.value.trim();
    if (!text) return;

    els.aiInput.value = '';
    els.aiOutputBox.classList.remove('hidden');
    els.aiThinking.classList.remove('hidden');
    els.aiResponse.textContent = '';

    try {
        const headers = await syncService.getAuthHeaders();
        headers['Content-Type'] = 'application/json';

        const resp = await fetch(`${state.serverUrl}/ai/smart-action`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ message: text })
        });

        if (!resp.ok) throw new Error('AI request failed');

        const data = await resp.json();

        els.aiThinking.classList.add('hidden');

        if (data.blocks_created && data.blocks_created.length > 0) {
            els.aiResponse.innerHTML = `
                <strong>${data.summary}</strong><br>
                <ul style="margin-top: 8px; padding-left: 16px;">
                    ${data.blocks_created.map(b =>
                        `<li>${b.name} <span style="opacity:0.5">(${b.block_type})</span></li>`
                    ).join('')}
                </ul>
            `;
            showToast(`Created ${data.blocks_created.length} blocks`, 'success');
            // Refresh blocks display
            if (typeof refreshBlocks === 'function') refreshBlocks();
        } else {
            els.aiResponse.textContent = data.summary;
        }
    } catch (e) {
        els.aiThinking.classList.add('hidden');
        els.aiResponse.textContent = 'AI unavailable. ' + (e.message || '');
    }
}
```

**Step 5: Add AI provider settings to settings panel**

In `desktop/index.html`, update the AI settings pane (around line 911):

```html
<div id="settings-pane-ai" class="settings-pane hidden">
    <h3>AI Configuration</h3>

    <label class="settings-label">AI Provider</label>
    <select id="ai-provider-select" class="settings-select">
        <option value="ollama">Ollama (Local / Free)</option>
        <option value="openai">OpenAI (API Key)</option>
        <option value="anthropic">Anthropic (API Key)</option>
    </select>

    <div id="ai-ollama-settings">
        <label class="settings-label">Ollama URL</label>
        <input type="text" id="ollama-url-input" placeholder="http://localhost:11434" class="settings-input">
        <label class="settings-label">Model</label>
        <select id="ai-model-select" class="settings-select">
            <option value="llama3.2">llama3.2</option>
            <option value="mistral">mistral</option>
            <option value="codellama">codellama</option>
        </select>
    </div>

    <div id="ai-openai-settings" class="hidden">
        <label class="settings-label">OpenAI API Key</label>
        <input type="password" id="openai-key-input" placeholder="sk-..." class="settings-input">
        <label class="settings-label">Model</label>
        <select id="openai-model-select" class="settings-select">
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>
        </select>
    </div>

    <div id="ai-anthropic-settings" class="hidden">
        <label class="settings-label">Anthropic API Key</label>
        <input type="password" id="anthropic-key-input" placeholder="sk-ant-..." class="settings-input">
        <label class="settings-label">Model</label>
        <select id="anthropic-model-select" class="settings-select">
            <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
            <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
        </select>
    </div>

    <span id="ai-status-indicator" class="settings-status">Not connected</span>
</div>
```

**Step 6: Commit**

```bash
git add backend/app/services/ai_block_service.py backend/app/schemas/ai_block.py backend/app/api/v1/endpoints/ai.py desktop/src/main.js desktop/index.html
git commit -m "feat: AI smart assistant — autonomous block creation from natural language"
```

---

## Task 6: macOS Transparency — Native Vibrancy

**Files:**
- Modify: `desktop/src-tauri/src/main.rs:630-651` (add vibrancy effect)
- Modify: `desktop/src-tauri/Cargo.toml` (add window-vibrancy crate)
- Modify: `desktop/src/styles/overlay.css:66-77` (enhance crystallize theme)

**Step 1: Add window-vibrancy dependency**

In `desktop/src-tauri/Cargo.toml`, add:
```toml
[dependencies]
window-vibrancy = "0.5"
```

**Step 2: Apply native vibrancy in Rust**

In `main.rs`, in the setup callback (after line 631, after window maximize), add:

```rust
// Apply native blur/vibrancy for transparent overlay
#[cfg(target_os = "macos")]
{
    use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};
    if let Err(e) = apply_vibrancy(&window, NSVisualEffectMaterial::UnderWindowBackground, None, None) {
        eprintln!("Failed to apply macOS vibrancy: {}", e);
    }
}

#[cfg(target_os = "windows")]
{
    use window_vibrancy::apply_acrylic;
    if let Err(e) = apply_acrylic(&window, Some((0, 0, 0, 1))) {
        eprintln!("Failed to apply Windows acrylic: {}", e);
    }
}
```

**Step 3: Enhance crystallize theme CSS**

Update `overlay.css` crystallize theme (lines 66-77):
```css
[data-theme="crystallize"] {
    --accent-h: 200;
    --accent-s: 30%;
    --accent-l: 85%;
    --glass-bg: rgba(255, 255, 255, 0.08);
    --glass-border: rgba(255, 255, 255, 0.15);
    --panel-bg: rgba(15, 17, 32, 0.4);
}

[data-theme="crystallize"] .panel-view,
[data-theme="crystallize"] .focus-panel,
[data-theme="crystallize"] .floating-panel {
    backdrop-filter: blur(20px) saturate(1.5);
    -webkit-backdrop-filter: blur(20px) saturate(1.5);
    background: var(--panel-bg) !important;
    border: 1px solid var(--glass-border);
}

[data-theme="crystallize"] .orb {
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
}
```

**Step 4: Commit**

```bash
git add desktop/src-tauri/src/main.rs desktop/src-tauri/Cargo.toml desktop/src/styles/overlay.css
git commit -m "feat: native vibrancy for macOS/Windows + enhanced crystallize theme"
```

---

## Task 7: Icon/Logo Consistency — Triangle Everywhere

**Files:**
- Modify: `desktop/index.html:59+` (replace orb SVG with triangle)
- Modify: `desktop/src/styles/overlay.css` (update orb styles for triangle)

**Step 1: Replace orb icon with triangle**

In `desktop/index.html`, find the orb SVG (around line 59) and replace the inner icon with the faceted triangle:

```html
<div id="orb" class="orb">
    <div class="orb-glow"></div>
    <svg class="orb-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="tri-g1" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#00D9FF"/>
                <stop offset="100%" style="stop-color:#3A7BC8"/>
            </linearGradient>
            <linearGradient id="tri-g2" x1="100%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#5BA3E6"/>
                <stop offset="100%" style="stop-color:#2A6BB8"/>
            </linearGradient>
        </defs>
        <!-- Main triangle faces -->
        <polygon points="50,12 88,82 12,82" fill="url(#tri-g1)" opacity="0.9"/>
        <polygon points="50,12 88,82 50,68" fill="url(#tri-g2)" opacity="0.75"/>
        <polygon points="50,12 12,82 50,68" fill="#00D9FF" opacity="0.5"/>
        <!-- Edge highlights -->
        <line x1="50" y1="12" x2="88" y2="82" stroke="rgba(255,255,255,0.15)" stroke-width="0.5"/>
        <line x1="50" y1="12" x2="12" y2="82" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>
        <line x1="50" y1="12" x2="50" y2="68" stroke="rgba(0,217,255,0.3)" stroke-width="0.5"/>
    </svg>
</div>
```

**Step 2: Commit**

```bash
git add desktop/index.html desktop/src/styles/overlay.css
git commit -m "feat: replace orb icon with faceted triangle logo"
```

---

## Task 8: Settings Panel Fix + Account Management

**Files:**
- Modify: `desktop/index.html:807-948` (fix settings tabs, add account section)
- Modify: `desktop/src/main.js:4117+` (fix settings save/load)

**Step 1: Fix settings tab navigation**

In `main.js`, ensure the settings tab click handlers properly show/hide panes:

```javascript
function initSettingsTabs() {
    document.querySelectorAll('.settings-nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            // Deactivate all
            document.querySelectorAll('.settings-nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.settings-pane').forEach(p => p.classList.add('hidden'));

            // Activate selected
            btn.classList.add('active');
            const paneId = `settings-pane-${btn.dataset.pane}`;
            const pane = document.getElementById(paneId);
            if (pane) pane.classList.remove('hidden');
        });
    });
}
```

**Step 2: Add account management section**

In `desktop/index.html`, add a new settings pane for Account:

```html
<div id="settings-pane-account" class="settings-pane hidden">
    <h3>Account</h3>
    <div id="account-info">
        <p>Signed in as: <strong id="account-username">-</strong></p>
        <p>Auth method: <span id="account-provider">-</span></p>
    </div>
    <button id="btn-change-password" class="settings-btn">Change Password</button>
    <button id="btn-manage-devices" class="settings-btn">Manage Devices</button>
    <button id="btn-logout" class="settings-btn danger">Sign Out</button>
</div>
```

Add "Account" to the settings nav bar.

**Step 3: Add data reset functionality**

In `main.js`, ensure the "Clear Data" button in settings works:

```javascript
async function resetAllData() {
    if (!confirm('This will delete ALL local data including blocks, settings, and auth. Continue?')) return;

    // Clear IndexedDB
    await localDb.clearAll();

    // Clear localStorage
    localStorage.clear();

    // Clear secure storage
    await SecureStorage.clearAuthSession();

    showToast('All data cleared. Reloading...', 'info');
    setTimeout(() => location.reload(), 1000);
}
```

**Step 4: Commit**

```bash
git add desktop/index.html desktop/src/main.js
git commit -m "fix: settings panel navigation, add account management + data reset"
```

---

## Task 9: Improvements — Sync Status, Soft Deletes, Token Refresh

**Files:**
- Modify: `desktop/src/main.js` (sync status display)
- Modify: `desktop/src/services/sync.js` (better status reporting)
- Modify: `backend/app/models/block.py:34+` (enforce soft deletes)
- Modify: `backend/app/services/block_service.py:201-215` (soft delete instead of hard delete)

**Step 1: Improve sync status indicator**

Replace the simple "Sync failed" toast with a persistent status widget:

In `index.html`, add a sync status bar (near the bottom of the body):
```html
<div id="sync-status-bar" class="sync-status-bar">
    <span id="sync-icon" class="sync-icon">⟳</span>
    <span id="sync-text">Offline</span>
</div>
```

**Step 2: Fix block soft delete**

In `backend/app/services/block_service.py`, change `delete_block` (line 201) from hard delete to soft delete:

```python
async def delete_block(self, block_id: str) -> bool:
    """Soft-delete a block and all its descendants."""
    block = await self.get_block_by_id(block_id)
    if not block:
        return False

    # Soft-delete descendants
    from sqlalchemy import update
    path_prefix = f"{block.path}.{block.id}" if block.path else block.id
    await self.db.execute(
        update(Block)
        .where(Block.path.like(f"{path_prefix}%"))
        .values(is_deleted=True)
    )

    # Soft-delete the block itself
    block.is_deleted = True
    await self.db.commit()
    return True
```

**Step 3: Commit**

```bash
git add desktop/index.html desktop/src/main.js desktop/src/services/sync.js backend/app/services/block_service.py
git commit -m "fix: improve sync status, enforce block soft deletes"
```

---

## Task 10: Final Integration Test + Preview

**Step 1: Start backend**

```bash
cd backend
docker-compose up -d
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Step 2: Start desktop dev**

```bash
cd desktop
npm run dev
```

**Step 3: Test checklist**

- [ ] Auth overlay appears on first launch
- [ ] Can create account with username/password
- [ ] Can sign in after creating account
- [ ] Auth overlay fades out after login
- [ ] Ghost mode toggles with Alt+G (in Tauri dev)
- [ ] Ghost exit button appears in ghost mode
- [ ] Panels dim in ghost mode
- [ ] AI orb chat sends to /ai/smart-action
- [ ] AI creates blocks from natural language
- [ ] Settings tabs all work
- [ ] Theme switching works (all 10 themes)
- [ ] Crystallize theme has blur effects
- [ ] Triangle logo shows in orb
- [ ] Sync status shows correct state
- [ ] Data reset clears everything

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: integration fixes after testing"
```
