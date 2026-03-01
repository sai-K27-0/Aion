import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Application configuration with persistent server URL storage
/// and automatic device type detection.
class AppConfig {
  // Storage keys
  static const String _serverUrlKey = 'aion_server_url';
  static const String _serverWsUrlKey = 'aion_server_ws_url';

  /// Preset: use this as server URL when connecting via Cloudflare Tunnel (off-LAN).
  /// User should replace with their actual tunnel hostname, e.g. from `cloudflared tunnel --url http://localhost:8000`
  /// or a custom domain. Example: 'https://aion.yourdomain.com/api/v1' or 'https://xxxx.trycloudflare.com/api/v1'
  static const String cloudflareTunnelUrlPreset = 'https://your-tunnel-hostname/api/v1';
  
  // Default URLs based on platform
  static String get defaultBaseUrl {
    if (kIsWeb) {
      // Web platform - use window.location.origin or localhost
      return 'http://localhost:8000/api/v1';
    }
    
    if (Platform.isAndroid) {
      // Android emulator uses 10.0.2.2 to access host localhost
      // Physical devices need the actual IP address
      if (_isEmulator) {
        return 'http://10.0.2.2:8000/api/v1';
      } else {
        // For physical devices, users must configure the server URL
        return 'http://192.168.1.100:8000/api/v1';
      }
    }
    
    if (Platform.isIOS) {
      // iOS simulator uses localhost directly
      // Physical devices need the actual IP address
      if (_isEmulator) {
        return 'http://localhost:8000/api/v1';
      } else {
        return 'http://192.168.1.100:8000/api/v1';
      }
    }
    
    // Desktop platforms
    return 'http://localhost:8000/api/v1';
  }
  
  static String get defaultWsUrl {
    final base = defaultBaseUrl;
    return base.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
  }
  
  // Cached values
  static String? _cachedServerUrl;
  static String? _cachedWsUrl;
  static bool? _cachedIsEmulator;
  
  /// Check if running on emulator/simulator
  static bool get _isEmulator {
    if (_cachedIsEmulator != null) return _cachedIsEmulator!;
    
    // This is a simple heuristic - for more accurate detection,
    // use device_info_plus package
    if (Platform.isAndroid) {
      // Android emulators typically have "sdk" in the model
      _cachedIsEmulator = Platform.environment.containsKey('ANDROID_SDK_ROOT') ||
                          Platform.environment.containsKey('ANDROID_EMULATOR');
    } else if (Platform.isIOS) {
      // iOS simulators run on x86_64 architecture (Intel Macs) or
      // have specific environment variables
      _cachedIsEmulator = Platform.environment.containsKey('SIMULATOR_DEVICE_NAME');
    } else {
      _cachedIsEmulator = false;
    }
    
    return _cachedIsEmulator!;
  }
  
  /// Get the current server URL (from storage or default)
  static Future<String> getServerUrl() async {
    if (_cachedServerUrl != null) return _cachedServerUrl!;
    
    try {
      final prefs = await SharedPreferences.getInstance();
      _cachedServerUrl = prefs.getString(_serverUrlKey) ?? defaultBaseUrl;
    } catch (e) {
      _cachedServerUrl = defaultBaseUrl;
    }
    
    // Defensive fallback in case cache assignment failed
    return _cachedServerUrl ?? defaultBaseUrl;
  }
  
  /// Get the current WebSocket URL
  static Future<String> getWsUrl() async {
    if (_cachedWsUrl != null) return _cachedWsUrl!;
    
    try {
      final prefs = await SharedPreferences.getInstance();
      _cachedWsUrl = prefs.getString(_serverWsUrlKey);
      if (_cachedWsUrl == null) {
        // Derive from server URL
        final serverUrl = await getServerUrl();
        _cachedWsUrl = serverUrl
            .replaceFirst('http://', 'ws://')
            .replaceFirst('https://', 'wss://');
      }
    } catch (e) {
      _cachedWsUrl = defaultWsUrl;
    }
    
    // Defensive fallback in case cache assignment failed
    return _cachedWsUrl ?? defaultWsUrl;
  }
  
  /// Save a custom server URL
  static Future<void> setServerUrl(String url) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_serverUrlKey, url);
      
      // Auto-derive WebSocket URL
      final wsUrl = url
          .replaceFirst('http://', 'ws://')
          .replaceFirst('https://', 'wss://');
      await prefs.setString(_serverWsUrlKey, wsUrl);
      
      // Update cache
      _cachedServerUrl = url;
      _cachedWsUrl = wsUrl;
    } catch (e) {
      debugPrint('Failed to save server URL: $e');
    }
  }
  
  /// Clear cached URLs (force reload from storage)
  static void clearCache() {
    _cachedServerUrl = null;
    _cachedWsUrl = null;
  }
  
  /// Check if we're running on a physical device
  static bool get isPhysicalDevice => !_isEmulator;
  
  /// Get platform name for device registration
  static String get platformName {
    if (kIsWeb) return 'web';
    if (Platform.isAndroid) return 'android';
    if (Platform.isIOS) return 'ios';
    if (Platform.isMacOS) return 'macos';
    if (Platform.isWindows) return 'windows';
    if (Platform.isLinux) return 'linux';
    return 'unknown';
  }
}
