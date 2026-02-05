import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../config.dart';

/// Voice interaction state
enum VoiceState {
  idle,
  listening,
  processing,
  speaking,
  error,
}

/// Voice service for speech-to-text and text-to-speech
class VoiceService {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  
  VoiceState _state = VoiceState.idle;
  final _stateController = StreamController<VoiceState>.broadcast();
  final _transcriptController = StreamController<String>.broadcast();
  final _responseController = StreamController<String>.broadcast();
  
  /// Current voice state
  VoiceState get state => _state;
  
  /// Stream of state changes
  Stream<VoiceState> get stateStream => _stateController.stream;
  
  /// Stream of transcription updates
  Stream<String> get transcriptStream => _transcriptController.stream;
  
  /// Stream of AI responses
  Stream<String> get responseStream => _responseController.stream;
  
  /// Connect to voice WebSocket
  Future<void> connect() async {
    if (_channel != null) return;
    
    try {
      final wsUrl = await AppConfig.getWsUrl();
      final uri = Uri.parse('$wsUrl/ai/voice/stream');
      
      // Use local variable to avoid null assertion on class field
      final channel = WebSocketChannel.connect(uri);
      _channel = channel;
      
      _subscription = channel.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );
      
      debugPrint('Voice WebSocket connected');
    } catch (e) {
      debugPrint('Voice connection failed: $e');
      _updateState(VoiceState.error);
    }
  }
  
  /// Disconnect from voice WebSocket
  Future<void> disconnect() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
    _channel = null;
    _updateState(VoiceState.idle);
  }
  
  /// Start listening for voice input
  void startListening() {
    if (_state != VoiceState.idle) return;
    
    _updateState(VoiceState.listening);
    _send({'type': 'start_listening'});
  }
  
  /// Stop listening
  void stopListening() {
    if (_state != VoiceState.listening) return;
    
    _updateState(VoiceState.processing);
    _send({'type': 'stop_listening'});
  }
  
  /// Send audio data for transcription
  void sendAudio(List<int> audioData) {
    if (_state != VoiceState.listening) return;
    
    _send({
      'type': 'audio',
      'data': base64Encode(audioData),
    });
  }
  
  /// Request text-to-speech
  void speak(String text) {
    _updateState(VoiceState.speaking);
    _send({
      'type': 'speak',
      'text': text,
    });
  }
  
  /// Interrupt current speech
  void interrupt() {
    if (_state == VoiceState.speaking) {
      _send({'type': 'interrupt'});
      _updateState(VoiceState.idle);
    }
  }
  
  void _send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (e) {
      debugPrint('Failed to send voice message: $e');
    }
  }
  
  void _handleMessage(dynamic message) {
    try {
      final data = jsonDecode(message as String) as Map<String, dynamic>;
      final type = data['type'] as String?;
      
      switch (type) {
        case 'transcript':
          _transcriptController.add(data['text'] as String);
          break;
          
        case 'transcript_final':
          _transcriptController.add(data['text'] as String);
          _updateState(VoiceState.processing);
          break;
          
        case 'response':
          _responseController.add(data['text'] as String);
          break;
          
        case 'speaking_start':
          _updateState(VoiceState.speaking);
          break;
          
        case 'speaking_end':
          _updateState(VoiceState.idle);
          break;
          
        case 'error':
          debugPrint('Voice error: ${data['message']}');
          _updateState(VoiceState.error);
          break;
      }
    } catch (e) {
      debugPrint('Failed to handle voice message: $e');
    }
  }
  
  void _handleError(dynamic error) {
    debugPrint('Voice WebSocket error: $error');
    _updateState(VoiceState.error);
  }
  
  void _handleDisconnect() {
    debugPrint('Voice WebSocket disconnected');
    _channel = null;
    _updateState(VoiceState.idle);
  }
  
  void _updateState(VoiceState newState) {
    if (_state != newState) {
      _state = newState;
      _stateController.add(newState);
    }
  }
  
  void dispose() {
    disconnect();
    _stateController.close();
    _transcriptController.close();
    _responseController.close();
  }
}

/// Provider for voice service
final voiceServiceProvider = Provider<VoiceService>((ref) {
  final service = VoiceService();
  ref.onDispose(() => service.dispose());
  return service;
});

/// Provider for voice state
final voiceStateProvider = StreamProvider<VoiceState>((ref) {
  final service = ref.watch(voiceServiceProvider);
  return service.stateStream;
});
