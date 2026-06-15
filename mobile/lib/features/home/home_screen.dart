import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/services/sync_service.dart';
import '../ai/orb_page.dart';
import '../blocks/blocks_page.dart';
import '../settings/settings_page.dart';
import '../tasks/tasks_screen.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _index = 0;

  static const _pages = <Widget>[
    OrbPage(),
    BlocksPage(),
    TasksScreen(),
    SettingsPage(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initSync());
  }

  Future<void> _initSync() async {
    if (!mounted) return;
    try {
      final sync = ref.read(restSyncServiceProvider);
      await sync.registerDevice();
      await sync.fullSync();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final syncState = ref.watch(restSyncStateProvider);

    return Scaffold(
      body: Column(
        children: [
          _SyncIndicator(state: syncState),
          Expanded(
            child: IndexedStack(index: _index, children: _pages),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_outlined),
            selectedIcon: Icon(Icons.auto_awesome),
            label: 'AI',
          ),
          NavigationDestination(
            icon: Icon(Icons.grid_view_outlined),
            selectedIcon: Icon(Icons.grid_view),
            label: 'Blocks',
          ),
          NavigationDestination(
            icon: Icon(Icons.checklist_outlined),
            selectedIcon: Icon(Icons.checklist),
            label: 'Tasks',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Slim sync status bar — only visible when syncing or on error
// ---------------------------------------------------------------------------

class _SyncIndicator extends StatelessWidget {
  const _SyncIndicator({required this.state});
  final AsyncValue<SyncState> state;

  @override
  Widget build(BuildContext context) {
    return state.when(
      loading: () => const SizedBox.shrink(),
      error: (e, _) =>
          _bar(context, 'Sync error', Theme.of(context).colorScheme.error),
      data: (syncState) {
        switch (syncState) {
          case SyncState.syncing:
            return _bar(context, 'Syncing…', Colors.blue, loading: true);
          case SyncState.error:
            return _bar(context, 'Sync error',
                Theme.of(context).colorScheme.error);
          default:
            return const SizedBox.shrink();
        }
      },
    );
  }

  Widget _bar(BuildContext context, String label, Color color,
      {bool loading = false}) {
    return Material(
      color: color.withAlpha(25),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (loading)
                SizedBox(
                  width: 10,
                  height: 10,
                  child: CircularProgressIndicator(
                    strokeWidth: 1.5,
                    color: color,
                  ),
                )
              else
                Icon(Icons.cloud_off_outlined, size: 12, color: color),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(fontSize: 11, color: color),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
