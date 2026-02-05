import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';
import '../../core/config.dart';
import '../../core/services/sync_service.dart';
import '../tasks/tasks_screen.dart';

/// Tablet-optimized home screen with split-view layout
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
    // Initialize sync on startup after the first frame
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

  @override
  Widget build(BuildContext context) {
    final syncState = ref.watch(restSyncStateProvider);
    final isWide = MediaQuery.of(context).size.width > 900;

    return Scaffold(
      body: Row(
        children: [
          // Navigation Rail
          NavigationRail(
            selectedIndex: _selectedNavIndex,
            onDestinationSelected: (index) {
              setState(() {
                _selectedNavIndex = index;
                _selectedBlockId = null;
              });
            },
            labelType: NavigationRailLabelType.all,
            leading: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Column(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Theme.of(context).colorScheme.primary,
                          Theme.of(context).colorScheme.secondary,
                        ],
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.auto_awesome, color: Colors.white),
                  ),
                  const SizedBox(height: 4),
                  const Text('Aion', style: TextStyle(fontWeight: FontWeight.bold)),
                ],
              ),
            ),
            trailing: Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  // Sync status
                  syncState.when(
                    data: (state) => _SyncIndicator(state: state),
                    loading: () => const SizedBox.shrink(),
                    error: (_, __) => const SizedBox.shrink(),
                  ),
                  const SizedBox(height: 8),
                ],
              ),
            ),
            destinations: const [
              NavigationRailDestination(
                icon: Icon(Icons.dashboard_outlined),
                selectedIcon: Icon(Icons.dashboard),
                label: Text('Dashboard'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.task_outlined),
                selectedIcon: Icon(Icons.task),
                label: Text('Tasks'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.account_tree_outlined),
                selectedIcon: Icon(Icons.account_tree),
                label: Text('Mind Map'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.calendar_month_outlined),
                selectedIcon: Icon(Icons.calendar_month),
                label: Text('Calendar'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.chat_outlined),
                selectedIcon: Icon(Icons.chat),
                label: Text('Chat'),
              ),
              NavigationRailDestination(
                icon: Icon(Icons.settings_outlined),
                selectedIcon: Icon(Icons.settings),
                label: Text('Settings'),
              ),
            ],
          ),
          const VerticalDivider(thickness: 1, width: 1),
          // Main content area with split view
          Expanded(
            child: _buildMainContent(isWide),
          ),
        ],
      ),
    );
  }

  Widget _buildMainContent(bool isWide) {
    switch (_selectedNavIndex) {
      case 0: // Dashboard
        return _DashboardView(isWide: isWide);
      case 1: // Tasks
        return const TasksScreen();
      case 2: // Mind Map
        return _MindMapView(
          isWide: isWide,
          selectedBlockId: _selectedBlockId,
          onBlockSelected: (id) => setState(() => _selectedBlockId = id),
        );
      case 3: // Calendar
        return const _CalendarView();
      case 4: // Chat
        return const _TabletChatView();
      case 5: // Settings
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

/// Dashboard with overview widgets
class _DashboardView extends ConsumerWidget {
  final bool isWide;

  const _DashboardView({required this.isWide});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Good ${_getGreeting()}!',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          Text(
            _getDateString(),
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.grey,
                ),
          ),
          const SizedBox(height: 24),
          Expanded(
            child: isWide
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(flex: 2, child: _buildLeftColumn(context)),
                      const SizedBox(width: 24),
                      Expanded(flex: 1, child: _buildRightColumn(context)),
                    ],
                  )
                : SingleChildScrollView(
                    child: Column(
                      children: [
                        _buildLeftColumn(context),
                        const SizedBox(height: 24),
                        _buildRightColumn(context),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildLeftColumn(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _DashboardCard(
          title: 'Today\'s Tasks',
          icon: Icons.task_alt,
          child: const _QuickTaskList(),
        ),
        const SizedBox(height: 16),
        _DashboardCard(
          title: 'Recent Blocks',
          icon: Icons.folder,
          child: const _RecentBlocks(),
        ),
      ],
    );
  }

  Widget _buildRightColumn(BuildContext context) {
    return Column(
      children: [
        _DashboardCard(
          title: 'Quick Stats',
          icon: Icons.analytics,
          child: const _QuickStats(),
        ),
        const SizedBox(height: 16),
        _DashboardCard(
          title: 'AI Assistant',
          icon: Icons.auto_awesome,
          child: const _QuickChat(),
        ),
      ],
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
    final days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    final months = ['January', 'February', 'March', 'April', 'May', 'June', 
                    'July', 'August', 'September', 'October', 'November', 'December'];
    return '${days[now.weekday % 7]}, ${months[now.month - 1]} ${now.day}';
  }
}

class _DashboardCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Widget child;

  const _DashboardCard({
    required this.title,
    required this.icon,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const Divider(),
            child,
          ],
        ),
      ),
    );
  }
}

class _QuickTaskList extends StatelessWidget {
  const _QuickTaskList();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        ListTile(
          leading: const Icon(Icons.check_circle_outline),
          title: const Text('Complete project review'),
          subtitle: const Text('Work'),
          dense: true,
        ),
        ListTile(
          leading: const Icon(Icons.check_circle, color: Colors.green),
          title: const Text('Team meeting'),
          subtitle: const Text('Work'),
          dense: true,
        ),
        ListTile(
          leading: const Icon(Icons.check_circle_outline),
          title: const Text('Study for exam'),
          subtitle: const Text('Personal'),
          dense: true,
        ),
        TextButton(
          onPressed: () {},
          child: const Text('View All Tasks →'),
        ),
      ],
    );
  }
}

class _RecentBlocks extends StatelessWidget {
  const _RecentBlocks();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _BlockChip(icon: '💼', name: 'Work'),
        _BlockChip(icon: '🌟', name: 'Personal'),
        _BlockChip(icon: '📚', name: 'Studies'),
        _BlockChip(icon: '💡', name: 'Ideas'),
      ],
    );
  }
}

class _BlockChip extends StatelessWidget {
  final String icon;
  final String name;

  const _BlockChip({required this.icon, required this.name});

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      avatar: Text(icon),
      label: Text(name),
      onPressed: () {},
    );
  }
}

class _QuickStats extends StatelessWidget {
  const _QuickStats();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: [
        _StatItem(value: '12', label: 'Tasks Done'),
        _StatItem(value: '3', label: 'Active'),
        _StatItem(value: '5', label: 'Pomodoros'),
      ],
    );
  }
}

class _StatItem extends StatelessWidget {
  final String value;
  final String label;

  const _StatItem({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                color: Theme.of(context).colorScheme.primary,
              ),
        ),
        Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
      ],
    );
  }
}

class _QuickChat extends StatelessWidget {
  const _QuickChat();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Text(
          'Ask Aion anything...',
          style: TextStyle(color: Colors.grey),
        ),
        const SizedBox(height: 12),
        TextField(
          decoration: InputDecoration(
            hintText: 'Type a message',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            suffixIcon: const Icon(Icons.send),
          ),
        ),
      ],
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
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
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
          onTap: () => widget.onSelect(widget.block['id']),
          child: Container(
            padding: EdgeInsets.only(
              left: widget.depth * 20.0,
              top: 8,
              bottom: 8,
              right: 8,
            ),
            decoration: BoxDecoration(
              color: isSelected
                  ? Theme.of(context).colorScheme.primary.withOpacity(0.1)
                  : null,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                if (hasChildren)
                  GestureDetector(
                    onTap: () => setState(() => _expanded = !_expanded),
                    child: Icon(
                      _expanded ? Icons.expand_more : Icons.chevron_right,
                      size: 20,
                    ),
                  )
                else
                  const SizedBox(width: 20),
                const SizedBox(width: 4),
                Text(widget.block['icon'] ?? '📄'),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.block['name'] ?? 'Untitled',
                    style: TextStyle(
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
                      leading: const Icon(Icons.link),
                      title: const Text('Server URL'),
                      subtitle: const Text('http://localhost:8000'),
                    ),
                  ],
                ),
                _SettingsSection(
                  title: 'Sync',
                  children: [
                    ListTile(
                      leading: const Icon(Icons.sync),
                      title: const Text('Auto Sync'),
                      trailing: Switch(value: true, onChanged: (v) {}),
                    ),
                  ],
                ),
                _SettingsSection(
                  title: 'About',
                  children: [
                    const ListTile(
                      leading: Icon(Icons.info),
                      title: Text('Version'),
                      subtitle: Text('0.1.0 (Tablet)'),
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
