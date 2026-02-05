import 'dart:math';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure storage service for sensitive data like tokens and credentials.
/// Uses Android Keystore and iOS Keychain for encrypted storage.
class SecureStorageService {
  static SecureStorageService? _instance;
  late final FlutterSecureStorage _storage;
  
  // Storage keys
  static const String _accessTokenKey = 'aion_access_token';
  static const String _refreshTokenKey = 'aion_refresh_token';
  static const String _userIdKey = 'aion_user_id';
  static const String _deviceTokenKey = 'aion_device_token';
  static const String _encryptionKeyKey = 'aion_encryption_key';
  
  SecureStorageService._() {
    _storage = const FlutterSecureStorage(
      aOptions: AndroidOptions(
        encryptedSharedPreferences: true,
        // Use AES encryption with Android Keystore
        keyCipherAlgorithm: KeyCipherAlgorithm.RSA_ECB_OAEPwithSHA_256andMGF1Padding,
        storageCipherAlgorithm: StorageCipherAlgorithm.AES_GCM_NoPadding,
      ),
      iOptions: IOSOptions(
        accessibility: KeychainAccessibility.first_unlock_this_device,
        // Data is only accessible on this device
      ),
    );
  }
  
  /// Get singleton instance
  static SecureStorageService get instance {
    _instance ??= SecureStorageService._();
    return _instance!;
  }
  
  // ==========================================================================
  // Access Token
  // ==========================================================================
  
  /// Get the stored access token
  Future<String?> getAccessToken() async {
    try {
      return await _storage.read(key: _accessTokenKey);
    } catch (e) {
      // If storage is corrupted, clear it
      await _storage.delete(key: _accessTokenKey);
      return null;
    }
  }
  
  /// Store the access token
  Future<void> setAccessToken(String token) async {
    await _storage.write(key: _accessTokenKey, value: token);
  }
  
  /// Delete the access token
  Future<void> deleteAccessToken() async {
    await _storage.delete(key: _accessTokenKey);
  }
  
  // ==========================================================================
  // Refresh Token
  // ==========================================================================
  
  /// Get the stored refresh token
  Future<String?> getRefreshToken() async {
    try {
      return await _storage.read(key: _refreshTokenKey);
    } catch (e) {
      await _storage.delete(key: _refreshTokenKey);
      return null;
    }
  }
  
  /// Store the refresh token
  Future<void> setRefreshToken(String token) async {
    await _storage.write(key: _refreshTokenKey, value: token);
  }
  
  /// Delete the refresh token
  Future<void> deleteRefreshToken() async {
    await _storage.delete(key: _refreshTokenKey);
  }
  
  // ==========================================================================
  // User ID
  // ==========================================================================
  
  /// Get the stored user ID
  Future<String?> getUserId() async {
    try {
      return await _storage.read(key: _userIdKey);
    } catch (e) {
      await _storage.delete(key: _userIdKey);
      return null;
    }
  }
  
  /// Store the user ID
  Future<void> setUserId(String userId) async {
    await _storage.write(key: _userIdKey, value: userId);
  }
  
  /// Delete the user ID
  Future<void> deleteUserId() async {
    await _storage.delete(key: _userIdKey);
  }
  
  // ==========================================================================
  // Device Token
  // ==========================================================================
  
  /// Get the stored device token
  Future<String?> getDeviceToken() async {
    try {
      return await _storage.read(key: _deviceTokenKey);
    } catch (e) {
      await _storage.delete(key: _deviceTokenKey);
      return null;
    }
  }
  
  /// Store the device token
  Future<void> setDeviceToken(String token) async {
    await _storage.write(key: _deviceTokenKey, value: token);
  }
  
  /// Delete the device token
  Future<void> deleteDeviceToken() async {
    await _storage.delete(key: _deviceTokenKey);
  }
  
  // ==========================================================================
  // Encryption Key (for local database encryption)
  // ==========================================================================
  
  /// Get or generate an encryption key for local database
  Future<String> getOrCreateEncryptionKey() async {
    try {
      var key = await _storage.read(key: _encryptionKeyKey);
      if (key == null) {
        // Generate a new 32-byte key
        key = _generateSecureKey();
        await _storage.write(key: _encryptionKeyKey, value: key);
      }
      return key;
    } catch (e) {
      // If storage fails, generate ephemeral key (data won't persist across installs)
      return _generateSecureKey();
    }
  }
  
  String _generateSecureKey() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }
  
  // ==========================================================================
  // Auth Session Management
  // ==========================================================================
  
  /// Store complete auth session
  Future<void> saveAuthSession({
    required String accessToken,
    required String refreshToken,
    required String userId,
  }) async {
    await Future.wait([
      setAccessToken(accessToken),
      setRefreshToken(refreshToken),
      setUserId(userId),
    ]);
  }
  
  /// Clear all auth data (logout)
  Future<void> clearAuthSession() async {
    await Future.wait([
      deleteAccessToken(),
      deleteRefreshToken(),
      deleteUserId(),
    ]);
  }
  
  /// Check if user is authenticated
  Future<bool> isAuthenticated() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }
  
  // ==========================================================================
  // Clear All Data
  // ==========================================================================
  
  /// Clear all secure storage (for logout or app reset)
  Future<void> clearAll() async {
    await _storage.deleteAll();
  }
  
  // ==========================================================================
  // Custom Key-Value Storage
  // ==========================================================================
  
  /// Read a custom key
  Future<String?> read(String key) async {
    try {
      return await _storage.read(key: key);
    } catch (e) {
      return null;
    }
  }
  
  /// Write a custom key-value pair
  Future<void> write(String key, String value) async {
    await _storage.write(key: key, value: value);
  }
  
  /// Delete a custom key
  Future<void> delete(String key) async {
    await _storage.delete(key: key);
  }
}
