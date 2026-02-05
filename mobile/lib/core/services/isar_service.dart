import 'package:flutter/foundation.dart';
import 'package:isar/isar.dart';
import 'package:path_provider/path_provider.dart';
import '../../data/models/block_model.dart';

/// Isar database service for local data persistence
class IsarService {
  static Isar? _isar;
  
  /// Get the Isar instance
  static Isar get instance {
    if (_isar == null) {
      throw StateError('IsarService not initialized. Call init() first.');
    }
    return _isar!;
  }
  
  /// Check if Isar is initialized
  static bool get isInitialized => _isar != null;
  
  /// Initialize Isar database
  static Future<void> init() async {
    if (_isar != null) return;
    
    try {
      final dir = await getApplicationDocumentsDirectory();
      
      _isar = await Isar.open(
        [BlockModelSchema],
        directory: dir.path,
        name: 'aion_db',
        inspector: kDebugMode, // Enable inspector in debug mode
      );
      
      debugPrint('Isar database initialized at ${dir.path}');
    } catch (e) {
      debugPrint('Failed to initialize Isar: $e');
      rethrow;
    }
  }
  
  /// Close the database
  static Future<void> close() async {
    await _isar?.close();
    _isar = null;
  }
  
  /// Clear all data (for logout/reset)
  static Future<void> clearAll() async {
    if (_isar == null) return;
    
    await _isar!.writeTxn(() async {
      await _isar!.clear();
    });
  }
}
