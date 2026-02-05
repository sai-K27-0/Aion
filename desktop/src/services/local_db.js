/**
 * Local Database Service - Offline-first data storage using IndexedDB.
 * 
 * This service provides:
 * - Local storage of blocks, tasks, and other entities
 * - Sync queue for offline changes
 * - Conflict tracking
 * - Migration support
 */

const DB_NAME = 'aion_local';
const DB_VERSION = 1;

// Entity stores
const STORES = {
    blocks: { keyPath: 'id', indexes: ['sync_id', 'parent_id', 'updated_at'] },
    block_fields: { keyPath: 'id', indexes: ['sync_id', 'block_id'] },
    block_entries: { keyPath: 'id', indexes: ['sync_id', 'block_id'] },
    block_contents: { keyPath: 'id', indexes: ['sync_id', 'block_id'] },
    triggers: { keyPath: 'id', indexes: ['sync_id'] },
    sync_queue: { keyPath: 'id', indexes: ['entity_type', 'sync_id', 'created_at'] },
    sync_meta: { keyPath: 'key' },
};

class LocalDatabase {
    constructor() {
        this.db = null;
        this.deviceId = null;
        this.isInitialized = false;
    }

    /**
     * Initialize the database.
     */
    async init() {
        if (this.isInitialized) return;

        // Get or create device ID
        this.deviceId = localStorage.getItem('aion_device_id');
        if (!this.deviceId) {
            this.deviceId = crypto.randomUUID();
            localStorage.setItem('aion_device_id', this.deviceId);
        }

        // Open IndexedDB
        this.db = await this._openDatabase();
        this.isInitialized = true;

        console.log('[LocalDB] Initialized with device ID:', this.deviceId);
    }

    /**
     * Open IndexedDB with schema setup.
     */
    _openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Create stores
                for (const [storeName, config] of Object.entries(STORES)) {
                    if (!db.objectStoreNames.contains(storeName)) {
                        const store = db.createObjectStore(storeName, {
                            keyPath: config.keyPath,
                        });

                        // Create indexes
                        if (config.indexes) {
                            for (const indexName of config.indexes) {
                                store.createIndex(indexName, indexName, { unique: false });
                            }
                        }
                    }
                }

                console.log('[LocalDB] Database schema created/upgraded');
            };
        });
    }

    /**
     * Get a transaction for the given stores.
     */
    _getTransaction(storeNames, mode = 'readonly') {
        return this.db.transaction(storeNames, mode);
    }

    // =========================================================================
    // Generic CRUD Operations
    // =========================================================================

    /**
     * Get a single record by ID.
     */
    async get(storeName, id) {
        return new Promise((resolve, reject) => {
            const tx = this._getTransaction([storeName]);
            const store = tx.objectStore(storeName);
            const request = store.get(id);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
        });
    }

    /**
     * Get all records from a store.
     */
    async getAll(storeName, options = {}) {
        return new Promise((resolve, reject) => {
            const tx = this._getTransaction([storeName]);
            const store = tx.objectStore(storeName);

            let request;
            if (options.index && options.value !== undefined) {
                const index = store.index(options.index);
                request = index.getAll(options.value);
            } else {
                request = store.getAll();
            }

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                let results = request.result;

                // Filter out deleted records unless requested
                if (!options.includeDeleted) {
                    results = results.filter(r => !r.is_deleted);
                }

                // Sort if needed
                if (options.sortBy) {
                    results.sort((a, b) => {
                        const aVal = a[options.sortBy];
                        const bVal = b[options.sortBy];
                        return options.sortDesc ? bVal - aVal : aVal - bVal;
                    });
                }

                resolve(results);
            };
        });
    }

    /**
     * Put (create or update) a record.
     */
    async put(storeName, record, addToSyncQueue = true) {
        // Ensure sync fields
        if (!record.sync_id) {
            record.sync_id = crypto.randomUUID();
        }
        if (!record.sync_version) {
            record.sync_version = 1;
        } else if (addToSyncQueue) {
            record.sync_version++;
        }
        record.local_updated_at = new Date().toISOString();
        record.device_id = this.deviceId;
        record.updated_at = record.updated_at || record.local_updated_at;

        return new Promise((resolve, reject) => {
            const tx = this._getTransaction([storeName], 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(record);

            request.onerror = () => reject(request.error);
            request.onsuccess = async () => {
                // Add to sync queue if needed
                if (addToSyncQueue) {
                    await this._addToSyncQueue(storeName, record, 'update');
                }
                resolve(record);
            };
        });
    }

    /**
     * Delete a record (soft delete for sync).
     */
    async delete(storeName, id) {
        const record = await this.get(storeName, id);
        if (record) {
            record.is_deleted = true;
            return this.put(storeName, record, true);
        }
    }

    /**
     * Hard delete a record (no sync).
     */
    async hardDelete(storeName, id) {
        return new Promise((resolve, reject) => {
            const tx = this._getTransaction([storeName], 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(id);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve();
        });
    }

    // =========================================================================
    // Sync Queue Operations
    // =========================================================================

    /**
     * Add a change to the sync queue.
     */
    async _addToSyncQueue(entityType, record, operation) {
        const queueItem = {
            id: crypto.randomUUID(),
            entity_type: entityType,
            entity_id: record.id,
            sync_id: record.sync_id,
            operation: operation,
            data: record,
            sync_version: record.sync_version,
            created_at: new Date().toISOString(),
            device_id: this.deviceId,
        };

        return new Promise((resolve, reject) => {
            const tx = this._getTransaction(['sync_queue'], 'readwrite');
            const store = tx.objectStore('sync_queue');
            const request = store.put(queueItem);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(queueItem);
        });
    }

    /**
     * Get all pending changes in the sync queue.
     */
    async getPendingChanges() {
        return this.getAll('sync_queue', { sortBy: 'created_at' });
    }

    /**
     * Clear synced items from the queue.
     */
    async clearSyncQueue(syncIds) {
        return new Promise((resolve, reject) => {
            const tx = this._getTransaction(['sync_queue'], 'readwrite');
            const store = tx.objectStore('sync_queue');
            const index = store.index('sync_id');

            let cleared = 0;
            for (const syncId of syncIds) {
                const request = index.openCursor(IDBKeyRange.only(syncId));
                request.onsuccess = (event) => {
                    const cursor = event.target.result;
                    if (cursor) {
                        cursor.delete();
                        cleared++;
                        cursor.continue();
                    }
                };
            }

            tx.oncomplete = () => resolve(cleared);
            tx.onerror = () => reject(tx.error);
        });
    }

    // =========================================================================
    // Sync Metadata
    // =========================================================================

    /**
     * Get sync metadata.
     */
    async getSyncMeta(key) {
        const meta = await this.get('sync_meta', key);
        return meta ? meta.value : null;
    }

    /**
     * Set sync metadata.
     */
    async setSyncMeta(key, value) {
        return new Promise((resolve, reject) => {
            const tx = this._getTransaction(['sync_meta'], 'readwrite');
            const store = tx.objectStore('sync_meta');
            const request = store.put({ key, value, updated_at: new Date().toISOString() });

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve();
        });
    }

    /**
     * Get the last sync time.
     */
    async getLastSyncTime() {
        return this.getSyncMeta('last_sync_time');
    }

    /**
     * Set the last sync time.
     */
    async setLastSyncTime(time) {
        return this.setSyncMeta('last_sync_time', time);
    }

    // =========================================================================
    // Block-specific Operations
    // =========================================================================

    /**
     * Get all blocks.
     */
    async getBlocks() {
        return this.getAll('blocks');
    }

    /**
     * Get a block by ID.
     */
    async getBlock(id) {
        return this.get('blocks', id);
    }

    /**
     * Get blocks by parent ID.
     */
    async getBlocksByParent(parentId) {
        return this.getAll('blocks', { index: 'parent_id', value: parentId });
    }

    /**
     * Create or update a block.
     */
    async saveBlock(block) {
        if (!block.id) {
            block.id = crypto.randomUUID();
            block.created_at = new Date().toISOString();
        }
        return this.put('blocks', block);
    }

    /**
     * Delete a block.
     */
    async deleteBlock(id) {
        return this.delete('blocks', id);
    }

    // =========================================================================
    // Bulk Operations
    // =========================================================================

    /**
     * Apply server changes to local database.
     */
    async applyServerChanges(changes) {
        const applied = { created: 0, updated: 0, deleted: 0 };

        for (const [entityType, records] of Object.entries(changes)) {
            const storeName = entityType;

            for (const record of records) {
                // Get existing local record
                const existing = await this.get(storeName, record.id);

                if (record.is_deleted) {
                    // Apply deletion
                    if (existing) {
                        await this.put(storeName, { ...existing, is_deleted: true }, false);
                        applied.deleted++;
                    }
                } else if (!existing) {
                    // Create new record
                    await this.put(storeName, record, false);
                    applied.created++;
                } else {
                    // Update existing record if server version is newer
                    if (record.sync_version > existing.sync_version) {
                        await this.put(storeName, record, false);
                        applied.updated++;
                    }
                }
            }
        }

        return applied;
    }

    /**
     * Export all data for backup.
     */
    async exportAll() {
        const data = {};
        for (const storeName of Object.keys(STORES)) {
            if (storeName !== 'sync_queue' && storeName !== 'sync_meta') {
                data[storeName] = await this.getAll(storeName, { includeDeleted: true });
            }
        }
        return data;
    }

    /**
     * Import data from backup.
     */
    async importAll(data, addToSyncQueue = false) {
        for (const [storeName, records] of Object.entries(data)) {
            for (const record of records) {
                await this.put(storeName, record, addToSyncQueue);
            }
        }
    }

    /**
     * Clear all data.
     */
    async clearAll() {
        return new Promise((resolve, reject) => {
            const storeNames = Object.keys(STORES);
            const tx = this._getTransaction(storeNames, 'readwrite');

            for (const storeName of storeNames) {
                tx.objectStore(storeName).clear();
            }

            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
    }

    // =========================================================================
    // Utility
    // =========================================================================

    /**
     * Get database statistics.
     */
    async getStats() {
        const stats = {
            deviceId: this.deviceId,
            stores: {},
        };

        for (const storeName of Object.keys(STORES)) {
            const records = await this.getAll(storeName, { includeDeleted: true });
            stats.stores[storeName] = {
                total: records.length,
                active: records.filter(r => !r.is_deleted).length,
                deleted: records.filter(r => r.is_deleted).length,
            };
        }

        stats.pendingSync = (await this.getPendingChanges()).length;
        stats.lastSync = await this.getLastSyncTime();

        return stats;
    }
}

// Singleton instance
let localDbInstance = null;

/**
 * Get the LocalDatabase singleton.
 */
export function getLocalDb() {
    if (!localDbInstance) {
        localDbInstance = new LocalDatabase();
    }
    return localDbInstance;
}

/**
 * Initialize the local database.
 */
export async function initLocalDb() {
    const db = getLocalDb();
    await db.init();
    return db;
}

export default LocalDatabase;
