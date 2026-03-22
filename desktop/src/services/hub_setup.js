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

    async initialize() {
        const setupComplete = localStorage.getItem(STORAGE_KEYS.SETUP_COMPLETE);
        if (setupComplete === 'true') {
            this._setState(STATES.READY);
            return;
        }

        const savedState = this.loadState();
        if (savedState && savedState !== STATES.CHECKING) {
            this._setState(savedState);
            return;
        }

        this._setState(STATES.CHECKING);
        const healthy = await this.checkBackendHealth();

        if (healthy) {
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
                localStorage.setItem(STORAGE_KEYS.SECRET_KEY, secretKey);
            }
        }

        const composePath = this._getComposePath();

        try {
            await window.__TAURI__.core.invoke('start_docker_compose', {
                composePath,
                envVars: { SECRET_KEY: secretKey },
            });
        } catch (e) {
            this._setProgress({ error: `Failed to start: ${e}` });
            return false;
        }

        this._startContainerPolling(composePath);
        return true;
    }

    _getComposePath() {
        const saved = localStorage.getItem(STORAGE_KEYS.COMPOSE_PATH);
        if (saved) return saved;
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

                const allRunning = ['postgres', 'qdrant', 'redis', 'api']
                    .every(s => statuses[s] === 'running');
                if (allRunning) {
                    this._stopContainerPolling();
                    this._setProgress({ containerStatuses: { ...statuses, migrations: 'running' } });
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
            const resp = await fetch(`${this._getApiBase()}/hub/status/public`);
            if (resp.ok) return await resp.json();
        } catch (e) { /* not reachable */ }
        return null;
    }

    _getApiBase() {
        return localStorage.getItem('aion_server_url') || 'http://localhost:8000/api/v1';
    }

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

        try {
            const { SecureStorage } = await import('./secure_storage.js');
            await SecureStorage.saveAuthSession({
                accessToken: tokens.access_token,
                refreshToken: tokens.refresh_token,
                userId: tokens.user_id,
            });
        } catch (e) {
            localStorage.setItem('aion_access_token', tokens.access_token);
        }

        return tokens;
    }

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

    async discoverHubs() {
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
