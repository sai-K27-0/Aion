import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/config.dart';
import '../../core/services/sync_service.dart';
import '../tasks/tasks_screen.dart';

/// Main home screen with bottom navigation - Phone optimized
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _currentIndex = 0;

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

    final pages = [
      const TasksScreen(),  // Tasks first for phone - most used
      const BlocksPage(),
      const ChatPage(),
      const SettingsPage(),
    ];

    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: pages,
      ),
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Sync status indicator
          syncState.when(
            data: (state) => _SyncStatusBar(state: state),
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
          NavigationBar(
            selectedIndex: _currentIndex,
            onDestinationSelected: (index) {
              setState(() => _currentIndex = index);
            },
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.task_outlined),
                selectedIcon: Icon(Icons.task),
                label: 'Tasks',
              ),
              NavigationDestination(
                icon: Icon(Icons.folder_outlined),
                selectedIcon: Icon(Icons.folder),
                label: 'Blocks',
              ),
              NavigationDestination(
                icon: Icon(Icons.chat_outlined),
                selectedIcon: Icon(Icons.chat),
                label: 'Chat',
              ),
              NavigationDestination(
                icon: Icon(Icons.settings_outlined),
                selectedIcon: Icon(Icons.settings),
                label: 'Settings',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SyncStatusBar extends ConsumerWidget {
  final SyncState state;

  const _SyncStatusBar({required this.state});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state == SyncState.synced || state == SyncState.connected) {
      return const SizedBox.shrink();
    }

    Color color;
    String text;
    IconData icon;

    switch (state) {
      case SyncState.syncing:
        color = Colors.blue;
        text = 'Syncing...';
        icon = Icons.sync;
        break;
      case SyncState.offline:
        color = Colors.orange;
        text = 'Offline - tap to retry';
        icon = Icons.cloud_off;
        break;
      case SyncState.error:
        color = Colors.red;
        text = 'Sync error - tap to retry';
        icon = Icons.error_outline;
        break;
      default:
        return const SizedBox.shrink();
    }

    return GestureDetector(
      onTap: () async {
        if (state == SyncState.syncing) return;
        try {
          await ref.read(restSyncServiceProvider).fullSync();
        } catch (e) {
          debugPrint('Manual sync failed: $e');
        }
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        color: color.withOpacity(0.1),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Text(
              text,
              style: TextStyle(color: color, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

/// Blocks list page with actual API integration
class BlocksPage extends ConsumerStatefulWidget {
  const BlocksPage({super.key});

  @override
  ConsumerState<BlocksPage> createState() => _BlocksPageState();
}

class _BlocksPageState extends ConsumerState<BlocksPage> {
  List<dynamic> _blocks = [];
  bool _isLoading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadBlocks();
  }

  Future<void> _loadBlocks() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final client = ref.read(apiClientProvider);
      final response = await client.get('/blocks/tree?max_depth=3');
      
      if (mounted) {
        setState(() {
          _blocks = response.data as List<dynamic>;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Failed to load blocks';
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Blocks'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadBlocks,
          ),
        ],
      ),
      body: _buildBody(),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          _showCreateBlockDialog(context);
        },
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 64, color: Colors.red[300]),
            const SizedBox(height: 16),
            Text(_error!, style: TextStyle(color: Colors.grey[400])),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadBlocks,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_blocks.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.folder_open,
              size: 64,
              color: Theme.of(context).colorScheme.primary.withOpacity(0.5),
            ),
            const SizedBox(height: 16),
            Text(
              'No blocks yet',
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                color: Colors.grey,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Tap + to create your first block',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.grey[600],
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadBlocks,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _blocks.length,
        itemBuilder: (context, index) {
          final block = _blocks[index];
          return _BlockTile(
            block: block,
            onTap: () => _showBlockDetails(block),
          );
        },
      ),
    );
  }

  void _showBlockDetails(dynamic block) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.6,
        minChildSize: 0.3,
        maxChildSize: 0.9,
        expand: false,
        builder: (context, scrollController) {
          return Container(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.grey[600],
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  block['name'] ?? 'Untitled',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                if (block['description'] != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    block['description'],
                    style: TextStyle(color: Colors.grey[400]),
                  ),
                ],
                const SizedBox(height: 16),
                Text(
                  'Type: ${block['block_type'] ?? 'default'}',
                  style: TextStyle(color: Colors.grey[500], fontSize: 12),
                ),
                if (block['children'] != null && (block['children'] as List).isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    'Children (${(block['children'] as List).length})',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 8),
                  ...(block['children'] as List).map((child) => ListTile(
                    leading: const Icon(Icons.subdirectory_arrow_right),
                    title: Text(child['name'] ?? 'Untitled'),
                    dense: true,
                  )),
                ],
              ],
            ),
          );
        },
      ),
    );
  }

  void _showCreateBlockDialog(BuildContext context) {
    final nameController = TextEditingController();
    final descController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create Block'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(
                labelText: 'Name',
                hintText: 'Enter block name',
              ),
              autofocus: true,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: descController,
              decoration: const InputDecoration(
                labelText: 'Description',
                hintText: 'Optional description',
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final name = nameController.text.trim();
              if (name.isEmpty) return;

              Navigator.pop(context);
              await _createBlock(name, descController.text.trim());
            },
            child: const Text('Create'),
          ),
        ],
      ),
    );
  }

  Future<void> _createBlock(String name, String description) async {
    try {
      final client = ref.read(apiClientProvider);
      await client.post('/blocks', data: {
        'name': name,
        'description': description.isEmpty ? null : description,
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Created "$name"')),
        );
        _loadBlocks();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to create block'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
}

class _BlockTile extends StatelessWidget {
  final dynamic block;
  final VoidCallback onTap;

  const _BlockTile({required this.block, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final hasChildren = block['children'] != null && (block['children'] as List).isNotEmpty;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primary.withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            hasChildren ? Icons.folder : Icons.article,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        title: Text(block['name'] ?? 'Untitled'),
        subtitle: block['description'] != null
            ? Text(
                block['description'],
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              )
            : null,
        trailing: hasChildren
            ? Chip(
                label: Text('${(block['children'] as List).length}'),
                padding: EdgeInsets.zero,
                visualDensity: VisualDensity.compact,
              )
            : null,
        onTap: onTap,
      ),
    );
  }
}

/// Chat page with AI integration and voice support
class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  final List<Map<String, dynamic>> _messages = [];
  bool _isLoading = false;
  bool _isListening = false;
  String? _detectedIntent;

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    setState(() {
      _messages.add({'role': 'user', 'content': text});
      _isLoading = true;
      _detectedIntent = null;
    });
    _messageController.clear();
    _scrollToBottom();

    try {
      final client = ref.read(apiClientProvider);
      
      // First, detect intent
      try {
        final intentResponse = await client.post('/ai/intent', data: {
          'message': text,
        });
        final intent = intentResponse.data;
        if (intent['action'] != 'none' && (intent['confidence'] as num) >= 0.6) {
          setState(() {
            _detectedIntent = '${_getIntentIcon(intent['action'])} ${_getIntentDescription(intent)}';
          });
        }
      } catch (_) {
        // Intent parsing is optional
      }
      
      // Then, get chat response
      final response = await client.post('/ai/chat', data: {
        'message': text,
        'web_search': false,
      });

      if (mounted) {
        setState(() {
          _messages.add({
            'role': 'assistant',
            'content': response.data['response'] ?? 'No response',
            'sources': response.data['sources'],
            'confidence': response.data['confidence'],
          });
          _isLoading = false;
        });
        _scrollToBottom();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages.add({
            'role': 'assistant',
            'content': 'Error: Failed to get response. Check your connection.',
          });
          _isLoading = false;
        });
      }
    }
  }
  
  String _getIntentIcon(String? action) {
    switch (action) {
      case 'create_block': return '📝';
      case 'search': return '🔍';
      case 'schedule_event': return '📅';
      case 'open_app': return '📱';
      case 'web_search': return '🌐';
      case 'browser_task': return '🤖';
      case 'focus_mode': return '🎯';
      default: return '💬';
    }
  }
  
  String _getIntentDescription(Map<String, dynamic> intent) {
    final action = intent['action'] as String?;
    final params = intent['parameters'] as Map<String, dynamic>? ?? {};
    
    switch (action) {
      case 'create_block':
        return 'Create "${params['name'] ?? 'note'}"';
      case 'search':
        return 'Search for "${params['query'] ?? ''}"';
      case 'schedule_event':
        return 'Schedule "${params['title'] ?? 'event'}"';
      case 'web_search':
        return 'Web search: "${params['query'] ?? ''}"';
      case 'focus_mode':
        return 'Enable focus mode';
      default:
        return action ?? 'Unknown';
    }
  }
  
  void _toggleVoice() {
    setState(() {
      _isListening = !_isListening;
    });
    
    if (_isListening) {
      // Start voice listening (placeholder for actual implementation)
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Voice input coming soon! For now, please type your message.'),
          duration: Duration(seconds: 2),
        ),
      );
      setState(() {
        _isListening = false;
      });
    }
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat with Aion'),
        actions: [
          if (_messages.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () {
                setState(() => _messages.clear());
              },
            ),
        ],
      ),
      body: Column(
        children: [
          // Messages
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.smart_toy_outlined,
                          size: 64,
                          color: Theme.of(context).colorScheme.primary.withOpacity(0.5),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'Start a conversation',
                          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Ask Aion about your blocks, tasks, or anything else',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.grey[600],
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.all(16),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      final isUser = msg['role'] == 'user';
                      return _ChatBubble(
                        message: msg['content'] ?? '',
                        isUser: isUser,
                      );
                    },
                  ),
          ),

          // Loading indicator
          if (_isLoading)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  const SizedBox(width: 16),
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Aion is thinking...',
                    style: TextStyle(color: Colors.grey[500], fontSize: 12),
                  ),
                ],
              ),
            ),

          // Intent indicator
          if (_detectedIntent != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.3),
              child: Row(
                children: [
                  Text(
                    _detectedIntent!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const Spacer(),
                  GestureDetector(
                    onTap: () => setState(() => _detectedIntent = null),
                    child: Icon(
                      Icons.close,
                      size: 16,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                ],
              ),
            ),

          // Input area
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              border: Border(
                top: BorderSide(color: Colors.grey.withOpacity(0.2)),
              ),
            ),
            child: SafeArea(
              child: Row(
                children: [
                  // Voice button
                  IconButton(
                    onPressed: _isLoading ? null : _toggleVoice,
                    icon: Icon(
                      _isListening ? Icons.mic : Icons.mic_none,
                      color: _isListening 
                          ? Theme.of(context).colorScheme.primary 
                          : null,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: TextField(
                      controller: _messageController,
                      decoration: InputDecoration(
                        hintText: 'Ask Aion anything...',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                        ),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 12,
                        ),
                      ),
                      onSubmitted: (_) => _sendMessage(),
                      textInputAction: TextInputAction.send,
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _isLoading ? null : _sendMessage,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  final String message;
  final bool isUser;

  const _ChatBubble({required this.message, required this.isUser});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: BoxDecoration(
          color: isUser
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16).copyWith(
            bottomRight: isUser ? const Radius.circular(4) : null,
            bottomLeft: !isUser ? const Radius.circular(4) : null,
          ),
          border: isUser ? null : Border.all(color: Colors.grey.withOpacity(0.2)),
        ),
        child: Text(
          message,
          style: TextStyle(
            color: isUser ? Colors.white : null,
          ),
        ),
      ),
    );
  }
}

/// Settings page
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  String _serverUrl = '';
  String _aiStatus = 'Unknown';
  List<String> _availableModels = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final url = await AppConfig.getServerUrl();
    setState(() {
      _serverUrl = url;
    });

    // Load AI status
    try {
      final client = ref.read(apiClientProvider);
      final response = await client.get('/ai/status');
      
      if (mounted) {
        final data = response.data;
        final ollama = data['ollama'] ?? {};
        setState(() {
          _aiStatus = ollama['available'] == true ? 'Online' : 'Offline';
          _availableModels = (ollama['models'] as List?)
              ?.map((m) => m is String ? m : (m['name'] ?? 'unknown').toString())
              .toList() ?? [];
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _aiStatus = 'Error';
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        children: [
          // Server Connection
          _SettingsSection(
            title: 'Connection',
            children: [
              ListTile(
                leading: const Icon(Icons.link),
                title: const Text('Server URL'),
                subtitle: Text(_serverUrl),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/connect'),
              ),
            ],
          ),

          // AI Status
          _SettingsSection(
            title: 'AI',
            children: [
              ListTile(
                leading: Icon(
                  Icons.smart_toy,
                  color: _aiStatus == 'Online' ? Colors.green : Colors.red,
                ),
                title: const Text('Ollama Status'),
                subtitle: Text(_aiStatus),
                trailing: _isLoading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : IconButton(
                        icon: const Icon(Icons.refresh),
                        onPressed: _loadSettings,
                      ),
              ),
              if (_availableModels.isNotEmpty)
                ListTile(
                  leading: const Icon(Icons.model_training),
                  title: const Text('Available Models'),
                  subtitle: Text(_availableModels.take(3).join(', ')),
                ),
            ],
          ),

          // About
          _SettingsSection(
            title: 'About',
            children: [
              ListTile(
                leading: const Icon(Icons.info_outline),
                title: const Text('Version'),
                subtitle: const Text('0.3.7'),
              ),
              ListTile(
                leading: const Icon(Icons.code),
                title: const Text('Platform'),
                subtitle: Text(AppConfig.platformName),
              ),
            ],
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
              fontWeight: FontWeight.w600,
              color: Theme.of(context).colorScheme.primary,
              letterSpacing: 1,
            ),
          ),
        ),
        ...children,
        const Divider(),
      ],
    );
  }
}
