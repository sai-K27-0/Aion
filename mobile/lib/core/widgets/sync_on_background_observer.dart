import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/sync_service.dart';

/// Listens to app lifecycle: sync on pause/detached (with timeout),
/// and run periodic sync every 15 minutes when in foreground.
class SyncOnBackgroundObserver extends ConsumerStatefulWidget {
  final Widget child;

  const SyncOnBackgroundObserver({super.key, required this.child});

  @override
  ConsumerState<SyncOnBackgroundObserver> createState() =>
      _SyncOnBackgroundObserverState();
}

class _SyncOnBackgroundObserverState
    extends ConsumerState<SyncOnBackgroundObserver>
    with WidgetsBindingObserver {
  static const Duration _syncTimeout = Duration(seconds: 5);
  static const Duration _periodicSyncInterval = Duration(minutes: 15);
  Timer? _periodicTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _periodicTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _periodicTimer?.cancel();
      _periodicTimer = null;
      _syncBeforeBackground();
    } else if (state == AppLifecycleState.resumed) {
      _startPeriodicSync();
    }
  }

  void _startPeriodicSync() {
    _periodicTimer?.cancel();
    _periodicTimer = Timer.periodic(_periodicSyncInterval, (_) {
      _syncBeforeBackground();
    });
  }

  Future<void> _syncBeforeBackground() async {
    final restSync = ref.read(restSyncServiceProvider);
    try {
      await restSync.fullSync().timeout(_syncTimeout);
    } catch (e) {
      debugPrint('Sync on background: $e');
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
