import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';
import '../../core/config.dart';
import '../../core/services/sync_service.dart';
import '../tasks/tasks_screen.dart';

/// Tablet-optimized home screen: orb hub, landscape rail, touch-first.
/// Rail indices: 0=Orb/Dashboard, 1=Tasks, 2=Mind Map, 3=Pomodoro, 4=Stats, 5=Habits, 6=Calendar, 7=Chat, 8=Settings.
class TabletHomeScreen extends ConsumerStatefulWidget {
  const TabletHomeScreen({super.key});

  @override
  ConsumerState<TabletHomeScreen> createState() => _TabletHomeScreenState();
}

class _TabletHomeScreenState extends ConsumerState<TabletHomeScreen> {
  int _selectedNavIndex = 0;
  String? _selectedBlockId;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initSync();
    });
  }

  Future<void> _initSync() async {
    if (!mounted) return;
    try {
      final syncService = ref.read(restSyncServiceProvider);
      await syncService.registerDevice();
      if (!mounted) return;
      await syncService.fullSync();
    } catch (e) {
      debugPrint('Initial sync failed: $e');
    }
  }

  void _navigateTo(int index) {
    HapticFeedback.lightImpact();
    setState(() {
      _selectedNavIndex = index;
      _selectedBlockId = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final syncState = ref.watch(restSyncStateProvider);
    final isWide = MediaQuery.of(context).size.width > 900;

    return Scaffold(
      body: Row(
        children: [
          // Touch-friendly navigation rail (extended, min 72dp targets)
          SizedBox(
            width: 140,
            child: NavigationRail(
              extended: true,
              minExtendedWidth: 140,
              selectedIndex: _selectedNavIndex,
              onDestinationSelected: _navigateTo,
              labelType: NavigationRailLabelType.all,
              leading: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Column(
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            Theme.of(context).colorScheme.primary,
                            Theme.of(context).colorScheme.secondary,
                          ],
                        ),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: Theme.of(context).colorScheme.primary.withOpacity(0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.auto_awesome, color: Colors.white, size: 28),
                    ),
                    const SizedBox(height: 6),
                    Text('Aion', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
              trailing: Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    syncState.when(
                      data: (state) => _SyncIndicator(state: state),
                      loading: () => const SizedBox.shrink(),
                      error: (_, __) => const SizedBox.shrink(),
                    ),
                    const SizedBox(height: 12),
                  ],
                ),
              ),
              destinations: const [
                NavigationRailDestination(
                  icon: Icon(Icons.dashboard_outlined, size: 26),
                  selectedIcon: Icon(Icons.dashboard, size: 26),
                  label: Text('Orb'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.task_outlined, size: 26),
                  selectedIcon: Icon(Icons.task, size: 26),
                  label: Text('Tasks'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.account_tree_outlined, size: 26),
                  selectedIcon: Icon(Icons.account_tree, size: 26),
                  label: Text('Mind Map'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.timer_outlined, size: 26),
                  selectedIcon: Icon(Icons.timer, size: 26),
                  label: Text('Pomodoro'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.analytics_outlined, size: 26),
                  selectedIcon: Icon(Icons.analytics, size: 26),
                  label: Text('Stats'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.check_circle_outline, size: 26),
                  selectedIcon: Icon(Icons.check_circle, size: 26),
                  label: Text('Habits'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.calendar_month_outlined, size: 26),
                  selectedIcon: Icon(Icons.calendar_month, size: 26),
                  label: Text('Calendar'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.chat_outlined, size: 26),
                  selectedIcon: Icon(Icons.chat, size: 26),
                  label: Text('Chat'),
                ),
                NavigationRailDestination(
                  icon: Icon(Icons.settings_outlined, size: 26),
                  selectedIcon: Icon(Icons.settings, size: 26),
                  label: Text('Settings'),
                ),
              ],
            ),
          ),
          const VerticalDivider(thickness: 1, width: 1),
          Expanded(
            child: _buildMainContent(isWide),
          ),
        ],
      ),
      floatingActionButton: _QuickCaptureFab(onNavigate: _navigateTo),
    );
  }

  Widget _buildMainContent(bool isWide) {
    switch (_selectedNavIndex) {
      case 0:
        return _OrbHubView(isWide: isWide, onNavigate: _navigateTo);
      case 1:
        return const TasksScreen();
      case 2:
        return _MindMapView(
          isWide: isWide,
          selectedBlockId: _selectedBlockId,
          onBlockSelected: (id) => setState(() => _selectedBlockId = id),
        );
      case 3:
        return const _PomodoroView();
      case 4:
        return const _StatsView();
      case 5:
        return const _HabitsView();
      case 6:
        return const _CalendarView();
      case 7:
        return const _TabletChatView();
      case 8:
        return const _TabletSettingsView();
      default:
        return const SizedBox.shrink();
    }
  }
}

class _SyncIndicator extends StatelessWidget {
  final SyncState state;

  const _SyncIndicator({required this.state});

  @override
  Widget build(BuildContext context) {
    IconData icon;
    Color color;

    switch (state) {
      case SyncState.syncing:
        icon = Icons.sync;
        color = Colors.blue;
        break;
      case SyncState.synced:
        icon = Icons.cloud_done;
        color = Colors.green;
        break;
      case SyncState.offline:
        icon = Icons.cloud_off;
        color = Colors.orange;
        break;
      case SyncState.error:
        icon = Icons.cloud_off;
        color = Colors.red;
        break;
      default:
        icon = Icons.cloud_queue;
        color = Colors.grey;
    }

    return Tooltip(
      message: state.name,
      child: Icon(icon, color: color, size: 20),
    );
  }
}

/// Orb hub: one place for all entry points (same as desktop radial menu).
/// Large touch tiles for two-handed landscape use.
class _OrbHubView extends ConsumerWidget {
  final bool isWide;
  final void Function(int index) onNavigate;

  const _OrbHubView({required this.isWide, required this.onNavigate});

  static const List<({String label, IconData icon, int index})> _tiles = [
    (label: 'Tasks', icon: Icons.task_alt, index: 1),
    (label: 'Mind Map', icon: Icons.account_tree, index: 2),
    (label: 'Pomodoro', icon: Icons.timer, index: 3),
    (label: 'Statistics', icon: Icons.analytics, index: 4),
    (label: 'Habits', icon: Icons.check_circle, index: 5),
    (label: 'Calendar', icon: Icons.calendar_month, index: 6),
    (label: 'AI Chat', icon: Icons.chat, index: 7),
    (label: 'Settings', icon: Icons.settings, index: 8),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Good ${_getGreeting()}!',
            style: theme.textTheme.headlineMedium,
          ),
          const SizedBox(height: 4),
          Text(
            _getDateString(),
            style: theme.textTheme.bodyLarge?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 28),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final crossAxisCount = isWide && constraints.maxWidth > 700 ? 4 : 2;
                return GridView.builder(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: crossAxisCount,
                    mainAxisSpacing: 16,
                    crossAxisSpacing: 16,
                    childAspectRatio: 1.1,
                  ),
                  itemCount: _tiles.length,
                  itemBuilder: (context, index) {
                    final t = _tiles[index];
                    return _OrbTile(
                      label: t.label,
                      icon: t.icon,
                      onTap: () => onNavigate(t.index),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'morning';
    if (hour < 17) return 'afternoon';
    return 'evening';
  }

  String _getDateString() {
    final now = DateTime.now();
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    return '${days[now.weekday % 7]}, ${months[now.month - 1]} ${now.day}';
  }
}

/// Single orb tile: min 48dp touch target, haptic, splash.
class _OrbTile extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const _OrbTile({required this.label, required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.5),
      borderRadius: BorderRadius.circular(20),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 40, color: theme.colorScheme.primary),
              const SizedBox(height: 12),
              Text(
                label,
                textAlign: TextAlign.center,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Quick capture FAB: opens bottom sheet (New Task, New Note, Voice).
class _QuickCaptureFab extends StatelessWidget {
  final void Function(int index) onNavigate;

  const _QuickCaptureFab({required this.onNavigate});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton.extended(
      onPressed: () => _showQuickCaptureSheet(context),
      icon: const Icon(Icons.add),
      label: const Text('Quick capture'),
    );
  }

  void _showQuickCaptureSheet(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Quick capture',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              ListTile(
                leading: const Icon(Icons.task_alt, size: 28),
                title: const Text('New task'),
                subtitle: const Text('Add a task to your list'),
                onTap: () {
                  Navigator.pop(context);
                  onNavigate(1);
                },
              ),
              ListTile(
                leading: const Icon(Icons.note_add, size: 28),
                title: const Text('New note'),
                subtitle: const Text('Add a block or note in Mind Map'),
                onTap: () {
                  Navigator.pop(context);
                  onNavigate(2);
                },
              ),
              ListTile(
                leading: const Icon(Icons.mic, size: 28),
                title: const Text('Voice note'),
                subtitle: const Text('Speak to capture (coming soon)'),
                onTap: () {
                  Navigator.pop(context);
                  // Placeholder for voice
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Placeholder: Pomodoro (matches desktop).
class _PomodoroView extends StatelessWidget {
  const _PomodoroView();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.timer, size: 80, color: Theme.of(context).colorScheme.primary.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text('Pomodoro', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text('25:00', style: Theme.of(context).textTheme.displaySmall),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: () {},
            icon: const Icon(Icons.play_arrow),
            label: const Text('Start'),
          ),
        ],
      ),
    );
  }
}

/// Placeholder: Statistics (matches desktop).
class _StatsView extends StatelessWidget {
  const _StatsView();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Statistics', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 24),
          Expanded(
            child: GridView.count(
              crossAxisCount: 2,
              mainAxisSpacing: 16,
              crossAxisSpacing: 16,
              children: [
                _StatCard(value: '—', label: 'Tasks done'),
                _StatCard(value: '—', label: 'Active'),
                _StatCard(value: '—', label: 'Pomodoros'),
                _StatCard(value: '—', label: 'Habits'),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String value;
  final String label;

  const _StatCard({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(value, style: theme.textTheme.headlineMedium?.copyWith(color: theme.colorScheme.primary)),
            const SizedBox(height: 4),
            Text(label, style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}

/// Placeholder: Habits (matches desktop).
class _HabitsView extends StatelessWidget {
  const _HabitsView();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Habits', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 16),
          Expanded(
            child: Center(
              child: Text(
                'Track daily habits here. Connect to backend when ready.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.grey),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Mind Map view with split panel
class _MindMapView extends ConsumerStatefulWidget {
  final bool isWide;
  final String? selectedBlockId;
  final Function(String?) onBlockSelected;

  const _MindMapView({
    required this.isWide,
    required this.selectedBlockId,
    required this.onBlockSelected,
  });

  @override
  ConsumerState<_MindMapView> createState() => _MindMapViewState();
}

class _MindMapViewState extends ConsumerState<_MindMapView> {
  List<dynamic> _blocks = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadBlocks();
  }

  Future<void> _loadBlocks() async {
    try {
      final client = ref.read(apiClientProvider);
      final response = await client.get('/blocks/tree?max_depth=5');
      if (mounted) {
        setState(() {
          _blocks = response.data as List<dynamic>;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (widget.isWide) {
      return Row(
        children: [
          // Block tree
          SizedBox(
            width: 300,
            child: _buildBlockTree(),
          ),
          const VerticalDivider(width: 1),
          // Block details
          Expanded(
            child: widget.selectedBlockId != null
                ? _BlockDetailPanel(blockId: widget.selectedBlockId!)
                : const Center(
                    child: Text('Select a block to view details'),
                  ),
          ),
        ],
      );
    }

    return _buildBlockTree();
  }

  Widget _buildBlockTree() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Text(
                'Mind Map',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.add),
                onPressed: () {},
              ),
              IconButton(
                icon: const Icon(Icons.refresh),
                onPressed: _loadBlocks,
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _loadBlocks,
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: _blocks.length,
              itemBuilder: (context, index) {
                return _BlockTreeItem(
                  block: _blocks[index],
                  depth: 0,
                  selectedId: widget.selectedBlockId,
                  onSelect: widget.onBlockSelected,
                );
              },
            ),
          ),
        ),
      ],
    );
  }
}

class _BlockTreeItem extends StatefulWidget {
  final dynamic block;
  final int depth;
  final String? selectedId;
  final Function(String?) onSelect;

  const _BlockTreeItem({
    required this.block,
    required this.depth,
    required this.selectedId,
    required this.onSelect,
  });

  @override
  State<_BlockTreeItem> createState() => _BlockTreeItemState();
}

class _BlockTreeItemState extends State<_BlockTreeItem> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final children = widget.block['children'] as List<dynamic>? ?? [];
    final hasChildren = children.isNotEmpty;
    final isSelected = widget.block['id'] == widget.selectedId;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            widget.onSelect(widget.block['id']);
          },
          child: Container(
            constraints: const BoxConstraints(minHeight: 52),
            padding: EdgeInsets.only(
              left: 16 + widget.depth * 24.0,
              top: 14,
              bottom: 14,
              right: 16,
            ),
            decoration: BoxDecoration(
              color: isSelected
                  ? Theme.of(context).colorScheme.primary.withOpacity(0.1)
                  : null,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                if (hasChildren)
                  GestureDetector(
                    onTap: () {
                      HapticFeedback.selectionClick();
                      setState(() => _expanded = !_expanded);
                    },
                    child: Padding(
                      padding: const EdgeInsets.all(8),
                      child: Icon(
                        _expanded ? Icons.expand_more : Icons.chevron_right,
                        size: 28,
                      ),
                    ),
                  )
                else
                  const SizedBox(width: 44),
                const SizedBox(width: 4),
                Text(widget.block['icon'] ?? '📄', style: const TextStyle(fontSize: 22)),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    widget.block['name'] ?? 'Untitled',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: isSelected ? FontWeight.bold : null,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (hasChildren && _expanded)
          ...children.map((child) => _BlockTreeItem(
                block: child,
                depth: widget.depth + 1,
                selectedId: widget.selectedId,
                onSelect: widget.onSelect,
              )),
      ],
    );
  }
}

class _BlockDetailPanel extends ConsumerWidget {
  final String blockId;

  const _BlockDetailPanel({required this.blockId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Block Details',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 16),
          Text('Block ID: $blockId'),
          // TODO: Load and display block details
        ],
      ),
    );
  }
}

/// Calendar view
class _CalendarView extends ConsumerWidget {
  const _CalendarView();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Calendar',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 24),
          Expanded(
            child: Card(
              child: CalendarDatePicker(
                initialDate: DateTime.now(),
                firstDate: DateTime(2020),
                lastDate: DateTime(2030),
                onDateChanged: (date) {},
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Tablet Chat view with larger input
class _TabletChatView extends ConsumerStatefulWidget {
  const _TabletChatView();

  @override
  ConsumerState<_TabletChatView> createState() => _TabletChatViewState();
}

class _TabletChatViewState extends ConsumerState<_TabletChatView> {
  final _controller = TextEditingController();
  final List<Map<String, dynamic>> _messages = [];
  bool _isLoading = false;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          Text(
            'Chat with Aion',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.chat_bubble_outline,
                          size: 64,
                          color: Theme.of(context).colorScheme.primary.withOpacity(0.3),
                        ),
                        const SizedBox(height: 16),
                        const Text('Start a conversation with Aion'),
                      ],
                    ),
                  )
                : ListView.builder(
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      return _ChatMessage(
                        content: msg['content'] ?? '',
                        isUser: msg['role'] == 'user',
                      );
                    },
                  ),
          ),
          if (_isLoading)
            const Padding(
              padding: EdgeInsets.all(8),
              child: CircularProgressIndicator(),
            ),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  decoration: InputDecoration(
                    hintText: 'Ask anything...',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                    ),
                  ),
                  onSubmitted: (_) => _sendMessage(),
                ),
              ),
              const SizedBox(width: 16),
              IconButton.filled(
                onPressed: _isLoading ? null : _sendMessage,
                icon: const Icon(Icons.send),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add({'role': 'user', 'content': text});
      _isLoading = true;
    });
    _controller.clear();

    try {
      final client = ref.read(apiClientProvider);
      final response = await client.post('/ai/chat', data: {'message': text});
      
      if (mounted) {
        setState(() {
          _messages.add({
            'role': 'assistant',
            'content': response.data['response'] ?? 'No response',
          });
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages.add({
            'role': 'assistant',
            'content': 'Error: Failed to get response',
          });
          _isLoading = false;
        });
      }
    }
  }
}

class _ChatMessage extends StatelessWidget {
  final String content;
  final bool isUser;

  const _ChatMessage({required this.content, required this.isUser});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.6,
        ),
        decoration: BoxDecoration(
          color: isUser
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: isUser ? null : Border.all(color: Colors.grey.withOpacity(0.3)),
        ),
        child: Text(
          content,
          style: TextStyle(color: isUser ? Colors.white : null),
        ),
      ),
    );
  }
}

/// Tablet Settings view
class _TabletSettingsView extends ConsumerWidget {
  const _TabletSettingsView();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Settings',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 24),
          Expanded(
            child: ListView(
              children: [
                _SettingsSection(
                  title: 'Connection',
                  children: [
                    ListTile(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      minVerticalPadding: 16,
                      leading: const Icon(Icons.link, size: 26),
                      title: const Text('Server URL'),
                      subtitle: const Text('http://localhost:8000'),
                    ),
                  ],
                ),
                _SettingsSection(
                  title: 'Sync',
                  children: [
                    ListTile(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      minVerticalPadding: 16,
                      leading: const Icon(Icons.sync, size: 26),
                      title: const Text('Auto Sync'),
                      trailing: Switch(value: true, onChanged: (v) {}),
                    ),
                  ],
                ),
                _SettingsSection(
                  title: 'About',
                  children: [
                    const ListTile(
                      contentPadding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      minVerticalPadding: 16,
                      leading: Icon(Icons.info, size: 26),
                      title: Text('Version'),
                      subtitle: Text('0.3.8 (Tablet)'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _SettingsSection({required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            title.toUpperCase(),
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: Theme.of(context).colorScheme.primary,
              letterSpacing: 1,
            ),
          ),
        ),
        Card(
          margin: const EdgeInsets.symmetric(horizontal: 8),
          child: Column(children: children),
        ),
      ],
    );
  }
}
