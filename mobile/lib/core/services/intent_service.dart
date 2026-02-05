import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';

/// Types of actions the AI can perform
enum ActionType {
  createBlock,
  search,
  scheduleEvent,
  openApp,
  webSearch,
  browserTask,
  focusMode,
  none,
}

/// A detected intent from user input
class DetectedIntent {
  final ActionType action;
  final double confidence;
  final Map<String, dynamic> parameters;
  final String reasoning;

  DetectedIntent({
    required this.action,
    required this.confidence,
    required this.parameters,
    required this.reasoning,
  });

  factory DetectedIntent.fromJson(Map<String, dynamic> json) {
    return DetectedIntent(
      action: _parseActionType(json['action'] as String?),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      parameters: json['parameters'] as Map<String, dynamic>? ?? {},
      reasoning: json['reasoning'] as String? ?? '',
    );
  }

  static ActionType _parseActionType(String? action) {
    switch (action) {
      case 'create_block':
        return ActionType.createBlock;
      case 'search':
        return ActionType.search;
      case 'schedule_event':
        return ActionType.scheduleEvent;
      case 'open_app':
        return ActionType.openApp;
      case 'web_search':
        return ActionType.webSearch;
      case 'browser_task':
        return ActionType.browserTask;
      case 'focus_mode':
        return ActionType.focusMode;
      default:
        return ActionType.none;
    }
  }

  bool get isActionable => action != ActionType.none && confidence >= 0.6;
}

/// Service for parsing user intents and executing actions
class IntentService {
  final ApiClient _apiClient;

  IntentService(this._apiClient);

  /// Parse a message to detect user intent
  Future<DetectedIntent> parseIntent(String message) async {
    try {
      final response = await _apiClient.post('/ai/intent', data: {
        'message': message,
      });

      final data = response.data as Map<String, dynamic>;
      return DetectedIntent.fromJson(data);
    } catch (e) {
      debugPrint('Intent parsing failed: $e');
      return DetectedIntent(
        action: ActionType.none,
        confidence: 0.0,
        parameters: {},
        reasoning: 'Failed to parse intent',
      );
    }
  }

  /// Execute a detected intent
  Future<Map<String, dynamic>> executeIntent(DetectedIntent intent) async {
    if (!intent.isActionable) {
      return {'success': false, 'error': 'Intent not actionable'};
    }

    try {
      final response = await _apiClient.post('/ai/execute', data: {
        'action_type': _actionTypeToString(intent.action),
        'parameters': intent.parameters,
      });

      return response.data as Map<String, dynamic>;
    } catch (e) {
      debugPrint('Intent execution failed: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  String _actionTypeToString(ActionType action) {
    switch (action) {
      case ActionType.createBlock:
        return 'create_block';
      case ActionType.search:
        return 'search';
      case ActionType.scheduleEvent:
        return 'schedule_event';
      case ActionType.openApp:
        return 'open_app';
      case ActionType.webSearch:
        return 'web_search';
      case ActionType.browserTask:
        return 'browser_task';
      case ActionType.focusMode:
        return 'focus_mode';
      case ActionType.none:
        return 'none';
    }
  }

  /// Get action description for UI
  String getActionDescription(DetectedIntent intent) {
    switch (intent.action) {
      case ActionType.createBlock:
        final name = intent.parameters['name'] ?? 'note';
        return 'Create "$name"';
      case ActionType.search:
        final query = intent.parameters['query'] ?? '';
        return 'Search for "$query"';
      case ActionType.scheduleEvent:
        final title = intent.parameters['title'] ?? 'event';
        return 'Schedule "$title"';
      case ActionType.openApp:
        final app = intent.parameters['app_name'] ?? 'app';
        return 'Open $app';
      case ActionType.webSearch:
        final query = intent.parameters['query'] ?? '';
        return 'Search web for "$query"';
      case ActionType.browserTask:
        return 'Automate browser task';
      case ActionType.focusMode:
        return 'Enable focus mode';
      case ActionType.none:
        return 'No action detected';
    }
  }

  /// Get icon for action type
  String getActionIcon(ActionType action) {
    switch (action) {
      case ActionType.createBlock:
        return '📝';
      case ActionType.search:
        return '🔍';
      case ActionType.scheduleEvent:
        return '📅';
      case ActionType.openApp:
        return '📱';
      case ActionType.webSearch:
        return '🌐';
      case ActionType.browserTask:
        return '🤖';
      case ActionType.focusMode:
        return '🎯';
      case ActionType.none:
        return '💬';
    }
  }
}

/// Provider for intent service
final intentServiceProvider = Provider<IntentService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return IntentService(apiClient);
});
