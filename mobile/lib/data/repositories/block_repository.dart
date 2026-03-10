import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:isar/isar.dart';
import '../../core/api/api_client.dart';
import '../../core/services/isar_service.dart';
import '../../core/services/sync_service.dart';
import '../models/block_model.dart';

/// Repository for block data with offline support
class BlockRepository {
  final ApiClient _apiClient;
  final SyncService _syncService;
  
  BlockRepository(this._apiClient, this._syncService);
  
  Isar get _db => IsarService.instance;
  
  /// Get all blocks from local database
  Future<List<BlockModel>> getLocalBlocks() async {
    return await _db.blockModels.where().findAll();
  }
  
  /// Get block tree from local database
  Future<List<BlockModel>> getLocalBlockTree({String? parentUuid}) async {
    if (parentUuid == null) {
      // Get root blocks (no parent)
      return await _db.blockModels
          .where()
          .filter()
          .parentUuidIsNull()
          .sortByOrder()
          .findAll();
    } else {
      return await _db.blockModels
          .where()
          .filter()
          .parentUuidEqualTo(parentUuid)
          .sortByOrder()
          .findAll();
    }
  }
  
  /// Fetch blocks from server and cache locally
  Future<List<Map<String, dynamic>>> fetchAndCacheBlocks() async {
    try {
      final response = await _apiClient.get('/blocks/tree?max_depth=3');
      final blocks = response.data as List<dynamic>;
      
      // Cache to local database
      await _cacheBlocks(blocks);
      
      return blocks.cast<Map<String, dynamic>>();
    } catch (e) {
      debugPrint('Failed to fetch blocks from server: $e');
      rethrow;
    }
  }
  
  /// Cache blocks to local database
  Future<void> _cacheBlocks(List<dynamic> blocks) async {
    await _db.writeTxn(() async {
      for (final block in blocks) {
        await _cacheBlockRecursive(block as Map<String, dynamic>);
      }
    });
  }
  
  Future<void> _cacheBlockRecursive(Map<String, dynamic> block, {String? parentUuid}) async {
    final uuid = block['id'] as String;
    
    // Check if block exists
    var existing = await _db.blockModels
        .where()
        .filter()
        .uuidEqualTo(uuid)
        .findFirst();
    
    final model = BlockModel()
      ..id = existing?.id ?? Isar.autoIncrement
      ..uuid = uuid
      ..type = block['block_type'] ?? 'default'
      ..properties = {
        'name': block['name'],
        'description': block['description'],
        'icon': block['icon'],
        'color': block['color'],
      }
      ..content = []
      ..parentUuid = parentUuid
      ..order = block['position'] ?? 0
      ..isSynced = true
      ..createdAt = block['created_at'] != null
          ? DateTime.parse(block['created_at'])
          : null
      ..updatedAt = block['updated_at'] != null
          ? DateTime.parse(block['updated_at'])
          : null;
    
    await _db.blockModels.put(model);
    
    // Process children
    final children = block['children'] as List<dynamic>?;
    if (children != null) {
      for (final child in children) {
        await _cacheBlockRecursive(child as Map<String, dynamic>, parentUuid: uuid);
      }
    }
  }
  
  /// Create a new block (with offline support)
  Future<BlockModel> createBlock({
    required String name,
    String? description,
    String? parentUuid,
  }) async {
    final uuid = DateTime.now().millisecondsSinceEpoch.toString();
    
    // Create locally first
    final model = BlockModel()
      ..id = Isar.autoIncrement
      ..uuid = uuid
      ..type = 'default'
      ..properties = {
        'name': name,
        'description': description,
      }
      ..content = []
      ..parentUuid = parentUuid
      ..order = 0
      ..isSynced = false
      ..createdAt = DateTime.now()
      ..updatedAt = DateTime.now();
    
    await _db.writeTxn(() async {
      await _db.blockModels.put(model);
    });
    
    // Try to sync to server
    try {
      final response = await _apiClient.post('/blocks', data: {
        'name': name,
        'description': description,
        'parent_id': parentUuid,
      });
      
      // Update with server ID
      final serverData = response.data as Map<String, dynamic>;
      final updatedModel = model.copyWith(
        uuid: serverData['id'],
        isSynced: true,
      );
      
      await _db.writeTxn(() async {
        await _db.blockModels.put(updatedModel);
      });
      
      // Notify sync service
      _syncService.sendSyncEvent(
        eventType: 'create',
        entityType: 'block',
        entityId: serverData['id'],
        data: serverData,
      );
      
      return updatedModel;
    } catch (e) {
      debugPrint('Failed to sync block to server (will retry later): $e');
      return model;
    }
  }
  
  /// Sync all unsynced blocks to server
  Future<int> syncPendingBlocks() async {
    final unsynced = await _db.blockModels
        .where()
        .filter()
        .isSyncedEqualTo(false)
        .findAll();
    
    int syncedCount = 0;
    
    for (final block in unsynced) {
      try {
        final response = await _apiClient.post('/blocks', data: {
          'name': block.properties?['name'],
          'description': block.properties?['description'],
          'parent_id': block.parentUuid,
        });
        
        final serverData = response.data as Map<String, dynamic>;
        final updatedModel = block.copyWith(
          uuid: serverData['id'],
          isSynced: true,
        );
        
        await _db.writeTxn(() async {
          await _db.blockModels.put(updatedModel);
        });
        
        syncedCount++;
      } catch (e) {
        debugPrint('Failed to sync block ${block.uuid}: $e');
      }
    }
    
    return syncedCount;
  }
  
  /// Get count of pending (unsynced) blocks
  Future<int> getPendingCount() async {
    return await _db.blockModels
        .where()
        .filter()
        .isSyncedEqualTo(false)
        .count();
  }
  
  /// Clear all local data
  Future<void> clearLocalData() async {
    await _db.writeTxn(() async {
      await _db.blockModels.clear();
    });
  }
}

/// Provider for block repository
final blockRepositoryProvider = Provider<BlockRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  final syncService = ref.watch(syncServiceProvider);
  return BlockRepository(apiClient, syncService);
});
