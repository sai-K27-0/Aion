import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import 'block_detail_page.dart';

class BlocksPage extends ConsumerStatefulWidget {
  const BlocksPage({super.key});

  @override
  ConsumerState<BlocksPage> createState() => _BlocksPageState();
}

class _BlocksPageState extends ConsumerState<BlocksPage> {
  List<Map<String, dynamic>> _blocks = [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadBlocks();
  }

  Future<void> _loadBlocks() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/blocks/tree', queryParameters: {
        'max_depth': 5,
      });
      final data = resp.data;
      final items = (data is Map ? data['blocks'] ?? [] : data) as List;
      setState(() {
        _blocks = items.cast<Map<String, dynamic>>();
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _createBlock({String? parentId}) async {
    String name = '';
    String type = 'default';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => _CreateBlockDialog(
        onNameChanged: (v) => name = v,
        onTypeChanged: (v) => type = v,
      ),
    );
    if (confirmed != true || name.trim().isEmpty) return;
    try {
      final client = ref.read(apiClientProvider);
      await client.post('/blocks', data: {
        'name': name.trim(),
        'block_type': type,
        if (parentId != null) 'parent_id': parentId,
      });
      await _loadBlocks();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString()), backgroundColor: Colors.red),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? _ErrorView(error: _error!, onRetry: _loadBlocks)
                : _blocks.isEmpty
                    ? _EmptyView(onCreate: _createBlock)
                    : RefreshIndicator(
                        onRefresh: _loadBlocks,
                        child: ListView.builder(
                          padding: const EdgeInsets.only(bottom: 80),
                          itemCount: _blocks.length,
                          itemBuilder: (_, i) => _BlockTile(
                            block: _blocks[i],
                            depth: 0,
                            onChanged: _loadBlocks,
                            onCreateChild: (id) =>
                                _createBlock(parentId: id),
                          ),
                        ),
                      ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _createBlock(),
        icon: const Icon(Icons.add),
        label: const Text('New block'),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Recursive block tile
// ---------------------------------------------------------------------------

class _BlockTile extends StatefulWidget {
  const _BlockTile({
    required this.block,
    required this.depth,
    required this.onChanged,
    required this.onCreateChild,
  });

  final Map<String, dynamic> block;
  final int depth;
  final VoidCallback onChanged;
  final void Function(String parentId) onCreateChild;

  @override
  State<_BlockTile> createState() => _BlockTileState();
}

class _BlockTileState extends State<_BlockTile> {
  bool _expanded = false;

  List<Map<String, dynamic>> get _children =>
      ((widget.block['children'] as List?) ?? [])
          .cast<Map<String, dynamic>>();

  bool get _hasChildren => _children.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final indent = widget.depth * 16.0;
    final blockId = widget.block['id']?.toString() ?? '';
    final name = widget.block['name']?.toString() ?? '—';
    final blockType = widget.block['block_type']?.toString() ?? 'default';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => BlockDetailPage(
                block: widget.block,
                onChanged: widget.onChanged,
              ),
            ),
          ),
          onLongPress: () => _showContextMenu(context, blockId, name),
          child: Padding(
            padding: EdgeInsets.only(left: indent + 8, right: 8),
            child: Row(
              children: [
                // Expand / leaf icon
                SizedBox(
                  width: 32,
                  child: _hasChildren
                      ? IconButton(
                          padding: EdgeInsets.zero,
                          iconSize: 18,
                          icon: Icon(
                            _expanded
                                ? Icons.expand_less
                                : Icons.expand_more,
                          ),
                          onPressed: () =>
                              setState(() => _expanded = !_expanded),
                        )
                      : const Icon(Icons.circle, size: 6),
                ),
                // Block icon
                Icon(
                  _hasChildren
                      ? Icons.folder_outlined
                      : _typeIcon(blockType),
                  size: 18,
                  color: cs.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: const TextStyle(fontSize: 14),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (blockType != 'default')
                          Text(
                            blockType,
                            style: TextStyle(
                              fontSize: 11,
                              color: cs.onSurfaceVariant,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const Icon(Icons.chevron_right, size: 16),
              ],
            ),
          ),
        ),
        const Divider(height: 1, indent: 48),
        if (_expanded && _hasChildren)
          ...(_children.map(
            (child) => _BlockTile(
              block: child,
              depth: widget.depth + 1,
              onChanged: widget.onChanged,
              onCreateChild: widget.onCreateChild,
            ),
          )),
      ],
    );
  }

  void _showContextMenu(
      BuildContext context, String blockId, String name) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.add_outlined),
              title: const Text('Add child block'),
              onTap: () => Navigator.pop(context, 'child'),
            ),
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('Edit block'),
              onTap: () => Navigator.pop(context, 'edit'),
            ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (action == 'child') {
      widget.onCreateChild(blockId);
    } else if (action == 'edit') {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => BlockDetailPage(
            block: widget.block,
            onChanged: widget.onChanged,
          ),
        ),
      );
    }
  }
}

IconData _typeIcon(String type) {
  switch (type) {
    case 'database':
      return Icons.table_chart_outlined;
    case 'document':
      return Icons.description_outlined;
    case 'folder':
      return Icons.folder_outlined;
    default:
      return Icons.article_outlined;
  }
}

// ---------------------------------------------------------------------------
// Empty / Error views
// ---------------------------------------------------------------------------

class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.onCreate});
  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.grid_view_outlined,
                size: 64, color: cs.onSurfaceVariant),
            const SizedBox(height: 16),
            Text(
              'No blocks yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Create your first block to get started',
              textAlign: TextAlign.center,
              style: TextStyle(color: cs.onSurfaceVariant),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: onCreate,
              icon: const Icon(Icons.add),
              label: const Text('Create block'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.error, required this.onRetry});
  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_outlined, size: 48, color: cs.error),
            const SizedBox(height: 12),
            Text(
              'Could not load blocks',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 6),
            Text(
              error,
              textAlign: TextAlign.center,
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12),
            ),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Create block dialog
// ---------------------------------------------------------------------------

class _CreateBlockDialog extends StatefulWidget {
  const _CreateBlockDialog({
    required this.onNameChanged,
    required this.onTypeChanged,
  });

  final void Function(String) onNameChanged;
  final void Function(String) onTypeChanged;

  @override
  State<_CreateBlockDialog> createState() => _CreateBlockDialogState();
}

class _CreateBlockDialogState extends State<_CreateBlockDialog> {
  String _type = 'default';

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New block'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Name',
              border: OutlineInputBorder(),
            ),
            onChanged: widget.onNameChanged,
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _type,
            decoration: const InputDecoration(
              labelText: 'Type',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'default', child: Text('Default')),
              DropdownMenuItem(value: 'document', child: Text('Document')),
              DropdownMenuItem(value: 'database', child: Text('Database')),
              DropdownMenuItem(value: 'folder', child: Text('Folder')),
            ],
            onChanged: (v) {
              setState(() => _type = v ?? 'default');
              widget.onTypeChanged(v ?? 'default');
            },
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Create'),
        ),
      ],
    );
  }
}
