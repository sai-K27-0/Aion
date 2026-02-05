/**
 * Secure Storage Service for Aion Desktop
 * Uses OS keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service)
 * via Tauri's Rust backend.
 * 
 * Falls back to localStorage when running in browser (dev mode).
 */

// Check if running in Tauri environment
const isTauri = () => window.__TAURI__ !== undefined;

// Storage keys
const KEYS = {
  ACCESS_TOKEN: 'access_token',
  REFRESH_TOKEN: 'refresh_token',
  USER_ID: 'user_id',
  DEVICE_ID: 'device_id',
  DEVICE_TOKEN: 'device_token',
  ENCRYPTION_KEY: 'encryption_key',
};

/**
 * Get a value from secure storage
 * @param {string} key - The key to retrieve
 * @returns {Promise<string|null>} - The value or null if not found
 */
async function get(key) {
  if (isTauri()) {
    try {
      const { invoke } = window.__TAURI__.tauri;
      return await invoke('secure_storage_get', { key });
    } catch (error) {
      console.error('[SecureStorage] Failed to get:', error);
      return null;
    }
  } else {
    // Fallback to localStorage (less secure, for dev only)
    console.warn('[SecureStorage] Using localStorage fallback (not secure)');
    return localStorage.getItem(`aion_secure_${key}`);
  }
}

/**
 * Set a value in secure storage
 * @param {string} key - The key to set
 * @param {string} value - The value to store
 * @returns {Promise<boolean>} - True if successful
 */
async function set(key, value) {
  if (isTauri()) {
    try {
      const { invoke } = window.__TAURI__.tauri;
      await invoke('secure_storage_set', { key, value });
      return true;
    } catch (error) {
      console.error('[SecureStorage] Failed to set:', error);
      return false;
    }
  } else {
    console.warn('[SecureStorage] Using localStorage fallback (not secure)');
    localStorage.setItem(`aion_secure_${key}`, value);
    return true;
  }
}

/**
 * Delete a value from secure storage
 * @param {string} key - The key to delete
 * @returns {Promise<boolean>} - True if successful
 */
async function remove(key) {
  if (isTauri()) {
    try {
      const { invoke } = window.__TAURI__.tauri;
      await invoke('secure_storage_delete', { key });
      return true;
    } catch (error) {
      console.error('[SecureStorage] Failed to delete:', error);
      return false;
    }
  } else {
    localStorage.removeItem(`aion_secure_${key}`);
    return true;
  }
}

/**
 * Check if a key exists in secure storage
 * @param {string} key - The key to check
 * @returns {Promise<boolean>} - True if exists
 */
async function exists(key) {
  if (isTauri()) {
    try {
      const { invoke } = window.__TAURI__.tauri;
      return await invoke('secure_storage_exists', { key });
    } catch (error) {
      console.error('[SecureStorage] Failed to check existence:', error);
      return false;
    }
  } else {
    return localStorage.getItem(`aion_secure_${key}`) !== null;
  }
}

// =============================================================================
// Authentication Token Management
// =============================================================================

/**
 * Get the current access token
 * @returns {Promise<string|null>}
 */
async function getAccessToken() {
  return get(KEYS.ACCESS_TOKEN);
}

/**
 * Set the access token
 * @param {string} token
 * @returns {Promise<boolean>}
 */
async function setAccessToken(token) {
  return set(KEYS.ACCESS_TOKEN, token);
}

/**
 * Get the current refresh token
 * @returns {Promise<string|null>}
 */
async function getRefreshToken() {
  return get(KEYS.REFRESH_TOKEN);
}

/**
 * Set the refresh token
 * @param {string} token
 * @returns {Promise<boolean>}
 */
async function setRefreshToken(token) {
  return set(KEYS.REFRESH_TOKEN, token);
}

/**
 * Get the current user ID
 * @returns {Promise<string|null>}
 */
async function getUserId() {
  return get(KEYS.USER_ID);
}

/**
 * Set the user ID
 * @param {string} userId
 * @returns {Promise<boolean>}
 */
async function setUserId(userId) {
  return set(KEYS.USER_ID, userId);
}

/**
 * Save a complete authentication session
 * @param {Object} session - The session data
 * @param {string} session.accessToken
 * @param {string} session.refreshToken
 * @param {string} session.userId
 * @returns {Promise<boolean>}
 */
async function saveAuthSession({ accessToken, refreshToken, userId }) {
  const results = await Promise.all([
    setAccessToken(accessToken),
    setRefreshToken(refreshToken),
    setUserId(userId),
  ]);
  return results.every(r => r);
}

/**
 * Clear all authentication data (logout)
 * @returns {Promise<boolean>}
 */
async function clearAuthSession() {
  const results = await Promise.all([
    remove(KEYS.ACCESS_TOKEN),
    remove(KEYS.REFRESH_TOKEN),
    remove(KEYS.USER_ID),
  ]);
  return results.every(r => r);
}

/**
 * Check if user is authenticated
 * @returns {Promise<boolean>}
 */
async function isAuthenticated() {
  const token = await getAccessToken();
  return token !== null && token !== '';
}

// =============================================================================
// Device Management
// =============================================================================

/**
 * Get or generate a unique device ID
 * @returns {Promise<string>}
 */
async function getOrCreateDeviceId() {
  let deviceId = await get(KEYS.DEVICE_ID);
  if (!deviceId) {
    // Generate a new UUID
    deviceId = crypto.randomUUID();
    await set(KEYS.DEVICE_ID, deviceId);
  }
  return deviceId;
}

/**
 * Get the device token
 * @returns {Promise<string|null>}
 */
async function getDeviceToken() {
  return get(KEYS.DEVICE_TOKEN);
}

/**
 * Set the device token
 * @param {string} token
 * @returns {Promise<boolean>}
 */
async function setDeviceToken(token) {
  return set(KEYS.DEVICE_TOKEN, token);
}

// =============================================================================
// Encryption Key (for local database)
// =============================================================================

/**
 * Get or generate an encryption key for local database
 * @returns {Promise<string>}
 */
async function getOrCreateEncryptionKey() {
  let key = await get(KEYS.ENCRYPTION_KEY);
  if (!key) {
    // Generate a 32-byte (256-bit) key
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    key = Array.from(array).map(b => b.toString(16).padStart(2, '0')).join('');
    await set(KEYS.ENCRYPTION_KEY, key);
  }
  return key;
}

// =============================================================================
// Export
// =============================================================================

export const SecureStorage = {
  // Low-level API
  get,
  set,
  remove,
  exists,
  KEYS,
  
  // Authentication
  getAccessToken,
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
  getUserId,
  setUserId,
  saveAuthSession,
  clearAuthSession,
  isAuthenticated,
  
  // Device
  getOrCreateDeviceId,
  getDeviceToken,
  setDeviceToken,
  
  // Encryption
  getOrCreateEncryptionKey,
};

export default SecureStorage;
