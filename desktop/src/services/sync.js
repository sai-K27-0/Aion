/**
 * Sync Service - Handles synchronization with the server.
 *
 * Features:
 * - Automatic sync when online
 * - Offline change queuing
 * - Conflict resolution
 * - Retry logic with exponential backoff
 * - Auth: sends Bearer token; on 401 tries refresh once and retries
 */

import { getLocalDb } from './local_db.js';
import SecureStorage from './secure_storage.js';

const SYNC_INTERVAL = 30000; // 30 seconds
const RETRY_DELAYS = [1000, 2000, 5000, 10000, 30000]; // Exponential backoff

class SyncService {
    constructor(serverUrl) {
        this.serverUrl = serverUrl;
        this.localDb = null;
        this.deviceId = null;
        this.isOnline = navigator.onLine;
        this.isSyncing = false;
        this.syncInterval = null;
        this.retryCount = 0;
        this.listeners = new Set();

        // Listen for online/offline events
        window.addEventListener('online', () => this._handleOnline());
        window.addEventListener('offline', () => this._handleOffline());
    }

    /**
     * Initialize the sync service.
     */
    async init() {
        this.localDb = getLocalDb();
        await this.localDb.init();
        this.deviceId = this.localDb.deviceId;

        // Check if user is authenticated before attempting sync
        const token = await SecureStorage.getAccessToken();
        if (!token) {
            console.log('[Sync] No auth token found - sync will start after login');
            this._notify('sync_status', { status: 'not_logged_in' });
            // Still start auto-sync so it picks up when user logs in later
            this._startAutoSync();
            return;
        }

        // Register device with server
        await this._registerDevice();

        // Start automatic sync
        this._startAutoSync();

        console.log('[Sync] Initialized');
    }

    /**
     * Add a sync event listener.
     */
    addListener(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    /**
     * Notify all listeners of a sync event.
     */
    _notify(event, data) {
        for (const listener of this.listeners) {
            try {
                listener(event, data);
            } catch (e) {
                console.error('[Sync] Listener error:', e);
            }
        }
    }

    /**
     * Get auth headers (Bearer token) for API calls.
     * Public so desktop can use for backend AI chat etc.
     */
    async _getAuthHeaders() {
        const token = await SecureStorage.getAccessToken();
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return headers;
    }

    /** Public: get auth headers for backend requests (e.g. AI chat). */
    async getAuthHeaders() {
        return this._getAuthHeaders();
    }

    /** Base URL of the server (no /api/v1). */
    getServerBaseUrl() {
        return this.serverUrl || '';
    }

    /**
     * Refresh access token using refresh token; returns true if successful.
     */
    async _refreshTokens() {
        const refreshToken = await SecureStorage.getRefreshToken();
        if (!refreshToken) return false;
        try {
            const response = await fetch(`${this.serverUrl}/api/v1/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            if (!response.ok) return false;
            const data = await response.json();
            if (data.access_token) await SecureStorage.setAccessToken(data.access_token);
            if (data.refresh_token) await SecureStorage.setRefreshToken(data.refresh_token);
            if (data.user_id) await SecureStorage.setUserId(data.user_id);
            return true;
        } catch (e) {
            console.warn('[Sync] Token refresh failed:', e);
            return false;
        }
    }

    /**
     * Register device with the server (requires auth).
     */
    async _registerDevice() {
        if (!this.isOnline) return;

        try {
            const headers = await this._getAuthHeaders();
            const response = await fetch(`${this.serverUrl}/api/v1/sync/register`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    device_id: this.deviceId,
                    device_name: this._getDeviceName(),
                    device_type: this._getDeviceType(),
                    platform: this._getPlatform(),
                }),
            });

            if (response.status === 401) {
                const refreshed = await this._refreshTokens();
                if (refreshed) return this._registerDevice();
            }
            if (response.ok) {
                const data = await response.json();
                console.log('[Sync] Device registered:', data);
            }
        } catch (error) {
            console.warn('[Sync] Failed to register device:', error);
        }
    }

    /**
     * Get device name.
     */
    _getDeviceName() {
        // Try to get from localStorage or generate
        let name = localStorage.getItem('aion_device_name');
        if (!name) {
            const platform = this._getPlatform();
            const type = this._getDeviceType();
            name = `${platform} ${type}`;
            localStorage.setItem('aion_device_name', name);
        }
        return name;
    }

    /**
     * Detect device type.
     */
    _getDeviceType() {
        const ua = navigator.userAgent.toLowerCase();
        if (/tablet|ipad/i.test(ua)) return 'tablet';
        if (/mobile|phone/i.test(ua)) return 'phone';
        return 'desktop';
    }

    /**
     * Detect platform.
     */
    _getPlatform() {
        const ua = navigator.userAgent.toLowerCase();
        if (ua.includes('win')) return 'windows';
        if (ua.includes('mac')) return 'macos';
        if (ua.includes('android')) return 'android';
        if (ua.includes('iphone') || ua.includes('ipad')) return 'ios';
        if (ua.includes('linux')) return 'linux';
        return 'unknown';
    }

    /**
     * Start automatic sync interval.
     */
    _startAutoSync() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
        }

        this.syncInterval = setInterval(() => {
            if (this.isOnline && !this.isSyncing) {
                this.sync();
            }
        }, SYNC_INTERVAL);

        // Initial sync
        if (this.isOnline) {
            this.sync();
        }
    }

    /**
     * Handle coming online.
     */
    _handleOnline() {
        console.log('[Sync] Online');
        this.isOnline = true;
        this.retryCount = 0;
        this._notify('online', {});
        this.sync();
    }

    /**
     * Handle going offline.
     */
    _handleOffline() {
        console.log('[Sync] Offline');
        this.isOnline = false;
        this._notify('offline', {});
    }

    /**
     * Perform a full sync.
     */
    async sync() {
        if (this.isSyncing || !this.isOnline) {
            return { success: false, reason: this.isSyncing ? 'already_syncing' : 'offline' };
        }

        this.isSyncing = true;
        this._notify('sync_start', {});

        try {
            // Get pending changes
            const pendingChanges = await this.localDb.getPendingChanges();
            const lastSync = await this.localDb.getLastSyncTime();

            console.log(`[Sync] Starting sync: ${pendingChanges.length} pending, last sync: ${lastSync}`);

            // Format changes for API
            const changes = pendingChanges.map(change => ({
                entity_type: change.entity_type,
                entity_id: change.entity_id,
                sync_id: change.sync_id,
                operation: change.operation,
                data: change.data,
                local_updated_at: change.data.local_updated_at,
                sync_version: change.sync_version,
            }));

            // Call full sync API (with auth)
            let headers = await this._getAuthHeaders();
            let response = await fetch(`${this.serverUrl}/api/v1/sync/full`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    device_id: this.deviceId,
                    changes: changes,
                    last_sync: lastSync,
                }),
            });
            if (response.status === 401) {
                const refreshed = await this._refreshTokens();
                if (refreshed) {
                    headers = await this._getAuthHeaders();
                    response = await fetch(`${this.serverUrl}/api/v1/sync/full`, {
                        method: 'POST',
                        headers,
                        body: JSON.stringify({
                            device_id: this.deviceId,
                            changes: changes,
                            last_sync: lastSync,
                        }),
                    });
                }
            }
            if (!response.ok) {
                throw new Error(`Sync failed: ${response.status}`);
            }

            const result = await response.json();

            // Apply server changes locally
            if (result.server_changes) {
                const applied = await this.localDb.applyServerChanges(result.server_changes);
                console.log('[Sync] Applied server changes:', applied);
            }

            // Clear synced items from queue
            if (result.changes_pushed > 0) {
                const syncedIds = pendingChanges.map(c => c.sync_id);
                await this.localDb.clearSyncQueue(syncedIds);
            }

            // Update last sync time
            await this.localDb.setLastSyncTime(result.last_sync_time);

            // Handle conflicts
            if (result.conflicts && result.conflicts.length > 0) {
                this._notify('conflicts', { conflicts: result.conflicts });
            }

            this.retryCount = 0;
            this._notify('sync_complete', {
                pushed: result.changes_pushed,
                pulled: result.changes_pulled,
                conflicts: result.conflicts?.length || 0,
            });

            console.log('[Sync] Complete:', {
                pushed: result.changes_pushed,
                pulled: result.changes_pulled,
            });

            return { success: true, result };

        } catch (error) {
            console.error('[Sync] Error:', error);
            this._notify('sync_error', { error: error.message });

            // Retry with backoff
            if (this.retryCount < RETRY_DELAYS.length) {
                const delay = RETRY_DELAYS[this.retryCount];
                this.retryCount++;
                console.log(`[Sync] Retrying in ${delay}ms (attempt ${this.retryCount})`);
                setTimeout(() => this.sync(), delay);
            }

            return { success: false, error: error.message };

        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Force an immediate sync.
     */
    async forceSync() {
        this.retryCount = 0;
        return this.sync();
    }

    /**
     * Resolve a conflict manually.
     */
    async resolveConflict(conflict, resolution) {
        if (!this.isOnline) {
            throw new Error('Cannot resolve conflict while offline');
        }

        const headers = await this._getAuthHeaders();
        let response = await fetch(`${this.serverUrl}/api/v1/sync/resolve`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                device_id: this.deviceId,
                sync_id: conflict.sync_id,
                entity_type: conflict.entity_type,
                resolution: resolution,
            }),
        });
        if (response.status === 401) {
            const refreshed = await this._refreshTokens();
            if (refreshed) {
                const newHeaders = await this._getAuthHeaders();
                response = await fetch(`${this.serverUrl}/api/v1/sync/resolve`, {
                    method: 'POST',
                    headers: newHeaders,
                    body: JSON.stringify({
                        device_id: this.deviceId,
                        sync_id: conflict.sync_id,
                        entity_type: conflict.entity_type,
                        resolution: resolution,
                    }),
                });
            }
        }

        if (!response.ok) {
            throw new Error('Failed to resolve conflict');
        }

        // Sync to get the resolved data
        await this.sync();

        return await response.json();
    }

    /**
     * Get sync status.
     */
    async getStatus() {
        const stats = await this.localDb.getStats();

        let serverStatus = null;
        if (this.isOnline) {
            try {
                const headers = await this._getAuthHeaders();
                const response = await fetch(
                    `${this.serverUrl}/api/v1/sync/status?device_id=${this.deviceId}`,
                    { headers }
                );
                if (response.ok) {
                    serverStatus = await response.json();
                }
            } catch (error) {
                console.warn('[Sync] Failed to get server status:', error);
            }
        }

        return {
            deviceId: this.deviceId,
            isOnline: this.isOnline,
            isSyncing: this.isSyncing,
            localStats: stats,
            serverStatus: serverStatus,
        };
    }

    /**
     * Stop the sync service.
     */
    stop() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }
}

// Singleton instance
let syncServiceInstance = null;

/**
 * Get the SyncService singleton.
 */
export function getSyncService(serverUrl = 'http://localhost:8000') {
    if (!syncServiceInstance) {
        syncServiceInstance = new SyncService(serverUrl);
    }
    return syncServiceInstance;
}

/**
 * Initialize the sync service.
 */
export async function initSyncService(serverUrl = 'http://localhost:8000') {
    const service = getSyncService(serverUrl);
    await service.init();
    return service;
}

export default SyncService;
