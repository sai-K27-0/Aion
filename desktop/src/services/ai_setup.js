/**
 * AI Setup Wizard Service
 * Handles hardware detection, Ollama installation, model recommendations, and setup completion.
 */

// Use Tauri APIs via window.__TAURI__ (available at runtime in the WebView)
const invoke = (...args) => window.__TAURI__?.core?.invoke?.(...args);
const shellOpen = (url) => {
  if (window.__TAURI__?.shell?.open) return window.__TAURI__.shell.open(url);
  window.open(url, '_blank');
};

const OLLAMA_DOWNLOAD_URLS = {
  windows: 'https://ollama.com/download/windows',
  macos: 'https://ollama.com/download/mac',
  linux: 'https://ollama.com/download/linux',
};

export class AISetupWizard {
  constructor(apiBase) {
    this.apiBase = apiBase;
    this.hardware = null;
    this.ollamaStatus = null;
    this.recommendations = null;
    this.currentStep = 1;
    this.totalSteps = 5;
    this.selectedModels = { chat: null, embedding: null };
    this._abortController = null;
  }

  // ── Step 1: Detect Hardware ──────────────────────────────────────────

  async detectHardware() {
    try {
      this.hardware = await invoke('detect_hardware');
      return this.hardware;
    } catch (err) {
      console.error('[AISetup] Hardware detection failed:', err);
      // Return a minimal fallback so the wizard can continue
      this.hardware = {
        ram_gb: 0,
        available_ram_gb: 0,
        cpu_cores: 0,
        cpu_name: 'Unknown',
        gpu_name: null,
        gpu_vram_gb: null,
        free_disk_gb: 0,
        os_name: 'Unknown',
        device_model: 'Unknown',
      };
      return this.hardware;
    }
  }

  // ── Step 2: Check Ollama ─────────────────────────────────────────────

  async checkOllama(url = 'http://localhost:11434') {
    // First try the Tauri local check
    try {
      const local = await invoke('check_ollama_local');
      if (local && (local.installed || local.running)) {
        this.ollamaStatus = local;
        return this.ollamaStatus;
      }
    } catch (_) {
      // Tauri command unavailable — fall through to backend health check
    }

    // Fallback: ask the backend health endpoint
    try {
      const resp = await fetch(
        `${this.apiBase}/ai/setup/ollama/health?url=${encodeURIComponent(url)}`
      );
      if (resp.ok) {
        const data = await resp.json();
        this.ollamaStatus = {
          installed: true,
          running: data.healthy === true,
          version: data.version || null,
          models_installed: data.models || [],
        };
      } else {
        this.ollamaStatus = { installed: false, running: false, version: null, models_installed: [] };
      }
    } catch (_) {
      this.ollamaStatus = { installed: false, running: false, version: null, models_installed: [] };
    }

    return this.ollamaStatus;
  }

  // ── Step 2b: Install Ollama (opens download page) ────────────────────

  async installOllama() {
    const platform = this._detectPlatform();
    const url = OLLAMA_DOWNLOAD_URLS[platform] || OLLAMA_DOWNLOAD_URLS.windows;
    try {
      await shellOpen(url);
    } catch (_) {
      window.open(url, '_blank');
    }
    return { platform, url };
  }

  // ── Step 2c: Get install instructions from backend ───────────────────

  async getInstallInstructions() {
    const platform = this._detectPlatform();
    try {
      const resp = await fetch(
        `${this.apiBase}/ai/setup/ollama/install-instructions?platform=${platform}`
      );
      if (resp.ok) return await resp.json();
    } catch (_) { /* ignore */ }
    return this._fallbackInstructions(platform);
  }

  // ── Step 3: Get Model Recommendations ────────────────────────────────

  async getRecommendations() {
    if (!this.hardware) await this.detectHardware();

    try {
      const resp = await fetch(`${this.apiBase}/ai/setup/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ram_gb: this.hardware.ram_gb,
          available_ram_gb: this.hardware.available_ram_gb,
          cpu_cores: this.hardware.cpu_cores,
          cpu_name: this.hardware.cpu_name,
          gpu_name: this.hardware.gpu_name,
          gpu_vram_gb: this.hardware.gpu_vram_gb,
          free_disk_gb: this.hardware.free_disk_gb,
        }),
      });

      if (resp.ok) {
        this.recommendations = await resp.json();
        return this.recommendations;
      }
    } catch (err) {
      console.error('[AISetup] Recommendations fetch failed:', err);
    }

    // Fallback recommendations
    this.recommendations = this._fallbackRecommendations();
    return this.recommendations;
  }

  // ── Step 4: Pull / download a model with streaming progress ──────────

  async pullModel(modelName, ollamaUrl, onProgress) {
    this._abortController = new AbortController();

    try {
      const resp = await fetch(`${this.apiBase}/ai/setup/ollama/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName, ollama_url: ollamaUrl }),
        signal: this._abortController.signal,
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => 'Unknown error');
        throw new Error(`Pull failed (${resp.status}): ${errText}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (onProgress) {
              const percent =
                data.total > 0
                  ? Math.round((data.completed / data.total) * 100)
                  : 0;
              onProgress({
                status: data.status || 'downloading',
                completed: data.completed || 0,
                total: data.total || 0,
                percent,
                digest: data.digest || null,
              });
            }
          } catch (_) {
            // not JSON — ignore
          }
        }
      }

      return true;
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('[AISetup] Model pull aborted');
        return false;
      }
      throw err;
    } finally {
      this._abortController = null;
    }
  }

  cancelPull() {
    if (this._abortController) this._abortController.abort();
  }

  // ── Step 4b: Verify models ──────────────────────────────────────────

  async verifyModel(modelName) {
    try {
      const resp = await fetch(
        `${this.apiBase}/ai/setup/ollama/verify?model_name=${encodeURIComponent(modelName)}`,
        { method: 'POST' }
      );
      if (resp.ok) return await resp.json();
      return { success: false, error: `Verification failed (${resp.status})` };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }

  async verifyEmbeddingModel(modelName) {
    try {
      const resp = await fetch(
        `${this.apiBase}/ai/setup/ollama/verify-embedding?model_name=${encodeURIComponent(modelName)}`,
        { method: 'POST' }
      );
      if (resp.ok) return await resp.json();
      return { success: false, error: `Verification failed (${resp.status})` };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }

  // ── Step 5: Complete setup ──────────────────────────────────────────

  async completeSetup(deviceId, config) {
    try {
      const resp = await fetch(`${this.apiBase}/ai/setup/setup/complete/${deviceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (resp.ok) return await resp.json();
    } catch (err) {
      console.error('[AISetup] Complete setup failed:', err);
    }
    return { success: true }; // optimistic
  }

  // ── Utility: Device tier label ──────────────────────────────────────

  getDeviceTier() {
    if (!this.hardware) return { label: 'Unknown', class: 'tier-unknown' };
    const ram = this.hardware.ram_gb || 0;
    const gpu = this.hardware.gpu_vram_gb || 0;

    if (ram >= 32 || gpu >= 8) return { label: 'Great', class: 'tier-great' };
    if (ram >= 16 || gpu >= 4) return { label: 'Good', class: 'tier-good' };
    return { label: 'Limited', class: 'tier-limited' };
  }

  // ── Persistence helpers ─────────────────────────────────────────────

  saveState() {
    const data = {
      currentStep: this.currentStep,
      hardware: this.hardware,
      ollamaStatus: this.ollamaStatus,
      recommendations: this.recommendations,
      selectedModels: this.selectedModels,
      completedAt: null,
    };
    localStorage.setItem('aion_ai_setup', JSON.stringify(data));
  }

  loadState() {
    try {
      const raw = localStorage.getItem('aion_ai_setup');
      if (!raw) return false;
      const data = JSON.parse(raw);
      this.currentStep = data.currentStep || 1;
      this.hardware = data.hardware || null;
      this.ollamaStatus = data.ollamaStatus || null;
      this.recommendations = data.recommendations || null;
      this.selectedModels = data.selectedModels || { chat: null, embedding: null };
      return true;
    } catch (_) {
      return false;
    }
  }

  isSetupComplete() {
    try {
      const raw = localStorage.getItem('aion_ai_setup');
      if (!raw) return false;
      const data = JSON.parse(raw);
      return !!data.completedAt;
    } catch (_) {
      return false;
    }
  }

  markComplete() {
    try {
      const raw = localStorage.getItem('aion_ai_setup');
      const data = raw ? JSON.parse(raw) : {};
      data.completedAt = new Date().toISOString();
      data.selectedModels = this.selectedModels;
      localStorage.setItem('aion_ai_setup', JSON.stringify(data));
    } catch (_) { /* ignore */ }
  }

  // ── Private helpers ─────────────────────────────────────────────────

  _detectPlatform() {
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes('win')) return 'windows';
    if (ua.includes('mac')) return 'macos';
    return 'linux';
  }

  _fallbackInstructions(platform) {
    const instructions = {
      windows: {
        steps: [
          'Download from https://ollama.com/download/windows',
          'Run the installer (.exe)',
          'Ollama will start automatically in the system tray',
        ],
      },
      macos: {
        steps: [
          'Download from https://ollama.com/download/mac',
          'Open the .dmg and drag Ollama to Applications',
          'Launch Ollama from Applications',
        ],
      },
      linux: {
        steps: [
          'Run: curl -fsSL https://ollama.com/install.sh | sh',
          'Start the service: systemctl start ollama',
        ],
      },
    };
    return instructions[platform] || instructions.windows;
  }

  _fallbackRecommendations() {
    const ram = this.hardware?.ram_gb || 8;
    const models = [];

    if (ram >= 32) {
      models.push({
        name: 'llama3.2',
        size: '4.7 GB',
        speed: 'Fast',
        ram_needed: '8 GB',
        recommended: true,
        description: 'Best balance of quality and speed',
      });
      models.push({
        name: 'mistral',
        size: '4.1 GB',
        speed: 'Fast',
        ram_needed: '8 GB',
        recommended: false,
        description: 'Great for coding and reasoning',
      });
    } else if (ram >= 16) {
      models.push({
        name: 'llama3.2',
        size: '4.7 GB',
        speed: 'Moderate',
        ram_needed: '8 GB',
        recommended: true,
        description: 'Recommended for your hardware',
      });
    } else {
      models.push({
        name: 'llama3.2:1b',
        size: '1.3 GB',
        speed: 'Fast',
        ram_needed: '4 GB',
        recommended: true,
        description: 'Lightweight model for limited hardware',
      });
    }

    // Always include an embedding model
    const embedding = {
      name: 'nomic-embed-text',
      size: '274 MB',
      speed: 'Fast',
      ram_needed: '1 GB',
      recommended: true,
      description: 'Required for semantic search',
      is_embedding: true,
    };

    return { chat_models: models, embedding_models: [embedding] };
  }
}
