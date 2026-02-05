import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';
import 'package:dio/dio.dart';
import '../config.dart';
import '../api/api_client.dart';
import 'isar_service.dart';

/// Sync state for the UI
enum SyncState {
  disconnected,
  connecting,
  connected,
  syncing,
  synced,
  error,
  offline,
}

/// Sync event for real-time updates
class SyncEvent {
  final String type;
  final String entityType;
  final String entityId;
  final Map<String, dynamic> data;
  final DateTime timestamp;

  SyncEvent({
    required this.type,
    required this.entityType,
    required this.entityId,
    required this.data,
    required this.timestamp,
  });

  factory SyncEvent.fromJson(Map<String, dynamic> json) {
    return SyncEvent(
      type: json['event'] ?? json['type'] ?? 'unknown',
      entityType: json['entity_type'] ?? '',
      entityId: json['entity_id'] ?? '',
      data: json['data'] ?? {},
      timestamp: json['timestamp'] != null
          ? DateTime.parse(json['timestamp'])
          : DateTime.now(),
    );
  }
}

/// WebSocket-based sync service for real-time data synchronization
class SyncService {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  
  final String _deviceId;
  final String _deviceName;
  
  SyncState _state = SyncState.disconnected;
  final _stateController = StreamController<SyncState>.broadcast();
  final _eventController = StreamController<SyncEvent>.broadcast();
  
  int _reconnectAttempts = 0;
  static const int maxReconnectAttempts = 5;
  static const Duration pingInterval = Duration(seconds: 30);
  
  SyncService({String? deviceId, String? deviceName})
      : _deviceId = deviceId ?? const Uuid().v4(),
        _deviceName = deviceName ?? 'Mobile Device';
  
  /// Current sync state
  SyncState get state => _state;
  
  /// Stream of sync state changes
  Stream<SyncState> get stateStream => _stateController.stream;
  
  /// Stream of sync events
  Stream<SyncEvent> get eventStream => _eventController.stream;
  
  /// Device ID for this client
  String get deviceId => _deviceId;
  
  /// Connect to the sync server
  Future<void> connect() async {
    if (_state == SyncState.connecting || _state == SyncState.connected) {
      return;
    }
    
    _updateState(SyncState.connecting);
    
    try {
      final wsUrl = await AppConfig.getWsUrl();
      final uri = Uri.parse('$wsUrl/sync/ws/$_deviceId')
          .replace(queryParameters: {
        'device_name': _deviceName,
        'device_type': AppConfig.platformName,
      });
      
      debugPrint('Connecting to WebSocket: $uri');
      
      // Use local variable to avoid null assertion on class field
      final channel = WebSocketChannel.connect(uri);
      _channel = channel;
      
      _subscription = channel.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );
      
      // Wait for connection confirmation
      // The server sends a 'connected' message on successful connection
      // For now, we assume connection is successful after channel is created
      _updateState(SyncState.connected);
      _reconnectAttempts = 0;
      _startPingTimer();
      
    } catch (e) {
      debugPrint('WebSocket connection error: $e');
      _updateState(SyncState.error);
      _scheduleReconnect();
    }
  }
  
  /// Disconnect from the sync server
  Future<void> disconnect() async {
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    await _subscription?.cancel();
    await _channel?.sink.close();
    _channel = null;
    _updateState(SyncState.disconnected);
  }
  
  /// Send a sync event to the server
  void sendSyncEvent({
    required String eventType,
    required String entityType,
    required String entityId,
    required Map<String, dynamic> data,
  }) {
    if (_state != SyncState.connected) {
      debugPrint('Cannot send sync event: not connected');
      return;
    }
    
    final message = {
      'type': 'sync',
      'event': eventType,
      'entity_type': entityType,
      'entity_id': entityId,
      'data': data,
    };
    
    _send(message);
  }
  
  /// Request a full sync from the server
  void requestFullSync() {
    if (_state != SyncState.connected) return;
    _send({'type': 'request_full_sync'});
    _updateState(SyncState.syncing);
  }
  
  void _send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (e) {
      debugPrint('Failed to send message: $e');
    }
  }
  
  void _handleMessage(dynamic message) {
    try {
      final data = jsonDecode(message as String) as Map<String, dynamic>;
      final type = data['type'] as String?;
      
      debugPrint('WebSocket message: $type');
      
      switch (type) {
        case 'connected':
          debugPrint('Connected to sync server: ${data['message']}');
          break;
          
        case 'pong':
          // Ping response received
          break;
          
        case 'sync':
          final event = SyncEvent.fromJson(data);
          _eventController.add(event);
          break;
          
        case 'sync_ack':
          debugPrint('Sync acknowledged: ${data['entity_id']}');
          break;
          
        case 'full_sync_start':
          debugPrint('Full sync started');
          break;
          
        case 'device_connected':
          debugPrint('Device connected: ${data['device_name']}');
          break;
          
        case 'device_disconnected':
          debugPrint('Device disconnected: ${data['device_id']}');
          break;
          
        default:
          debugPrint('Unknown message type: $type');
      }
    } catch (e) {
      debugPrint('Failed to handle message: $e');
    }
  }
  
  void _handleError(dynamic error) {
    debugPrint('WebSocket error: $error');
    _updateState(SyncState.error);
    _scheduleReconnect();
  }
  
  void _handleDisconnect() {
    debugPrint('WebSocket disconnected');
    _pingTimer?.cancel();
    _updateState(SyncState.disconnected);
    _scheduleReconnect();
  }
  
  void _startPingTimer() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(pingInterval, (_) {
      if (_state == SyncState.connected) {
        _send({'type': 'ping'});
      }
    });
  }
  
  void _scheduleReconnect() {
    if (_reconnectAttempts >= maxReconnectAttempts) {
      debugPrint('Max reconnect attempts reached');
      return;
    }
    
    _reconnectTimer?.cancel();
    final delay = Duration(seconds: (1 << _reconnectAttempts).clamp(1, 30));
    debugPrint('Scheduling reconnect in ${delay.inSeconds}s (attempt ${_reconnectAttempts + 1})');
    
    _reconnectTimer = Timer(delay, () {
      _reconnectAttempts++;
      connect();
    });
  }
  
  void _updateState(SyncState newState) {
    if (_state != newState) {
      _state = newState;
      _stateController.add(newState);
    }
  }
  
  void dispose() {
    disconnect();
    _stateController.close();
    _eventController.close();
  }
}

/// Provider for the sync service
final syncServiceProvider = Provider<SyncService>((ref) {
  final service = SyncService();
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for sync state
final syncStateProvider = StreamProvider<SyncState>((ref) {
  final service = ref.watch(syncServiceProvider);
  return service.stateStream;
});

/// Provider for sync events
final syncEventsProvider = StreamProvider<SyncEvent>((ref) {
  final service = ref.watch(syncServiceProvider);
  return service.eventStream;
});

/// REST-based sync service for offline-first synchronization
class RestSyncService {
  final Dio _dio;
  final String _deviceId;
  final String _deviceName;
  final String _deviceType;
  final String _platform;
  
  String? _lastSyncTime;
  SyncState _state = SyncState.disconnected;
  final _stateController = StreamController<SyncState>.broadcast();
  
  RestSyncService({
    required Dio dio,
    String? deviceId,
    String? deviceName,
    String? deviceType,
    String? platform,
  }) : _dio = dio,
       _deviceId = deviceId ?? const Uuid().v4(),
       _deviceName = deviceName ?? 'Mobile Device',
       _deviceType = deviceType ?? 'phone',
       _platform = platform ?? AppConfig.platformName;
  
  SyncState get state => _state;
  Stream<SyncState> get stateStream => _stateController.stream;
  String get deviceId => _deviceId;
  
  /// Register this device with the server
  Future<bool> registerDevice() async {
    try {
      await _dio.post('/sync/register', data: {
        'device_id': _deviceId,
        'device_name': _deviceName,
        'device_type': _deviceType,
        'platform': _platform,
      });
      return true;
    } catch (e) {
      debugPrint('Failed to register device: $e');
      return false;
    }
  }
  
  /// Perform a full sync (push local changes, pull server changes)
  Future<SyncResult> fullSync({
    List<SyncChangeData>? localChanges,
  }) async {
    _updateState(SyncState.syncing);
    
    try {
      final response = await _dio.post('/sync/full', data: {
        'device_id': _deviceId,
        'changes': localChanges?.map((c) => c.toJson()).toList() ?? [],
        'last_sync': _lastSyncTime,
      });
      
      final data = response.data;
      _lastSyncTime = data['last_sync_time'];
      
      final result = SyncResult(
        success: data['success'] ?? false,
        changesPushed: data['changes_pushed'] ?? 0,
        changesPulled: data['changes_pulled'] ?? 0,
        conflicts: (data['conflicts'] as List?)
            ?.map((c) => SyncConflict.fromJson(c))
            .toList() ?? [],
        serverChanges: data['server_changes'] ?? {},
        lastSyncTime: _lastSyncTime,
      );
      
      _updateState(result.conflicts.isNotEmpty ? SyncState.synced : SyncState.synced);
      return result;
      
    } catch (e) {
      debugPrint('Sync failed: $e');
      _updateState(SyncState.error);
      return SyncResult(
        success: false,
        error: e.toString(),
      );
    }
  }
  
  /// Pull changes from server
  Future<Map<String, List<dynamic>>> pullChanges() async {
    try {
      final response = await _dio.post('/sync/pull', data: {
        'device_id': _deviceId,
        'since': _lastSyncTime,
      });
      
      final data = response.data;
      _lastSyncTime = data['last_sync_time'];
      return Map<String, List<dynamic>>.from(data['changes'] ?? {});
    } catch (e) {
      debugPrint('Pull failed: $e');
      return {};
    }
  }
  
  /// Push local changes to server
  Future<SyncResult> pushChanges(List<SyncChangeData> changes) async {
    try {
      final response = await _dio.post('/sync/push', data: {
        'device_id': _deviceId,
        'changes': changes.map((c) => c.toJson()).toList(),
      });
      
      final data = response.data;
      return SyncResult(
        success: data['success'] ?? false,
        changesPushed: data['changes_pushed'] ?? 0,
        conflicts: (data['conflicts'] as List?)
            ?.map((c) => SyncConflict.fromJson(c))
            .toList() ?? [],
        lastSyncTime: data['last_sync_time'],
      );
    } catch (e) {
      debugPrint('Push failed: $e');
      return SyncResult(success: false, error: e.toString());
    }
  }
  
  /// Get sync status
  Future<Map<String, dynamic>> getStatus() async {
    try {
      final response = await _dio.get('/sync/status', queryParameters: {
        'device_id': _deviceId,
      });
      return response.data;
    } catch (e) {
      return {'error': e.toString()};
    }
  }
  
  void _updateState(SyncState newState) {
    if (_state != newState) {
      _state = newState;
      _stateController.add(newState);
    }
  }
  
  void dispose() {
    _stateController.close();
  }
}

/// Data class for a sync change
class SyncChangeData {
  final String entityType;
  final String entityId;
  final String syncId;
  final String operation;
  final Map<String, dynamic> data;
  final String localUpdatedAt;
  final int syncVersion;
  
  SyncChangeData({
    required this.entityType,
    required this.entityId,
    required this.syncId,
    required this.operation,
    required this.data,
    required this.localUpdatedAt,
    required this.syncVersion,
  });
  
  Map<String, dynamic> toJson() => {
    'entity_type': entityType,
    'entity_id': entityId,
    'sync_id': syncId,
    'operation': operation,
    'data': data,
    'local_updated_at': localUpdatedAt,
    'sync_version': syncVersion,
  };
}

/// Result of a sync operation
class SyncResult {
  final bool success;
  final int changesPushed;
  final int changesPulled;
  final List<SyncConflict> conflicts;
  final Map<String, dynamic> serverChanges;
  final String? lastSyncTime;
  final String? error;
  
  SyncResult({
    this.success = false,
    this.changesPushed = 0,
    this.changesPulled = 0,
    this.conflicts = const [],
    this.serverChanges = const {},
    this.lastSyncTime,
    this.error,
  });
}

/// Sync conflict data
class SyncConflict {
  final String entityType;
  final String entityId;
  final String syncId;
  final Map<String, dynamic> clientData;
  final Map<String, dynamic> serverData;
  final int clientVersion;
  final int serverVersion;
  
  SyncConflict({
    required this.entityType,
    required this.entityId,
    required this.syncId,
    required this.clientData,
    required this.serverData,
    required this.clientVersion,
    required this.serverVersion,
  });
  
  factory SyncConflict.fromJson(Map<String, dynamic> json) => SyncConflict(
    entityType: json['entity_type'] ?? '',
    entityId: json['entity_id'] ?? '',
    syncId: json['sync_id'] ?? '',
    clientData: json['client_data'] ?? {},
    serverData: json['server_data'] ?? {},
    clientVersion: json['client_version'] ?? 0,
    serverVersion: json['server_version'] ?? 0,
  );
}

/// Provider for REST sync service
final restSyncServiceProvider = Provider<RestSyncService>((ref) {
  final client = ref.watch(apiClientProvider);
  final service = RestSyncService(dio: client.dio);
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for REST sync state
final restSyncStateProvider = StreamProvider<SyncState>((ref) {
  final service = ref.watch(restSyncServiceProvider);
  return service.stateStream;
});
