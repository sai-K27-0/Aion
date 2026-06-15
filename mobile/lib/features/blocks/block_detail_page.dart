import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';

class BlockDetailPage extends ConsumerStatefulWidget {
  const BlockDetailPage({
    super.key,
    required this.block,
    required this.onChanged,
  });

  final Map<String, dynamic> block;
  final VoidCallback onChanged;

  @override
  ConsumerState<BlockDetailPage> createState() => _BlockDetailPageState();
}

class _BlockDetailPageState extends ConsumerState<BlockDetailPage> {
  late final TextEditingController _nameController;
  bool _editing = false;
  bool _saving = false;
  String? _error;

  // Children — seed from block tree data, refresh from tree endpoint if needed
  late List<Map<String, dynamic>> _children;
  bool _loadingChildren = false;

  @override
  void initState() {
    super.initState();
    _nameController =
        TextEditingController(text: widget.block['name']?.toString() ?? '');
    _children = ((widget.block['children'] as List?) ?? [])
        .cast<Map<String, dynamic>>();
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  String get _blockId => widget.block['id']?.toString() ?? '';

  Future<void> _refreshChildren() async {
    if (_blockId.isEmpty) return;
    setState(() => _loadingChildren = true);
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get(
        '/blocks/tree',
        queryParameters: {'parent_id': _blockId, 'max_depth': 2},
      );
      final data = resp.data;
      final items =
          (data is Map ? data['blocks'] ?? [] : data) as List;
      setState(() {
        _children = items.cast<Map<String, dynamic>>();
        _loadingChildren = false;
      });
    } catch (_) {
      setState(() => _loadingChildren = false);
    }
  }

  Future<void> _saveName() async {
    final newName = _nameController.text.trim();
    if (newName.isEmpty) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final client = ref.read(apiClientProvider);
      await client.put('/blocks/$_blockId', data: {'name': newName});
      setState(() {
        _editing = false;
        _saving = false;
      });
      widget.onChanged();
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _saving = false;
      });
    }
  }

  Future<void> _deleteBlock() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete block?'),
        content: const Text('This will remove the block and all its children.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final client = ref.read(apiClientProvider);
      await client.delete('/blocks/$_blockId');
      widget.onChanged();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString()), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _addChild() async {
    String name = '';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Add child block'),
        content: TextField(
          autofocus: true,
          onChanged: (v) => name = v,
          decoration: const InputDecoration(hintText: 'Block name'),
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
      ),
    );
    if (confirmed != true || name.trim().isEmpty || !mounted) return;
    try {
      final client = ref.read(apiClientProvider);
      await client.post('/blocks', data: {
        'name': name.trim(),
        'parent_id': _blockId,
        'block_type': 'default',
      });
      widget.onChanged();
      await _refreshChildren();
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
    final cs = Theme.of(context).colorScheme;
    final blockType =
        widget.block['block_type']?.toString() ?? 'default';

    return Scaffold(
      appBar: AppBar(
        title: _editing
            ? null
            : Text(
                _nameController.text.isEmpty ? 'Block' : _nameController.text,
              ),
        actions: [
          if (!_editing)
            IconButton(
              onPressed: () => setState(() => _editing = true),
              icon: const Icon(Icons.edit_outlined),
              tooltip: 'Rename',
            ),
          IconButton(
            onPressed: _deleteBlock,
            icon: Icon(Icons.delete_outline, color: cs.error),
            tooltip: 'Delete',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Name editor
          if (_editing) ...[
            TextField(
              controller: _nameController,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Block name',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            if (_error != null)
              Text(_error!, style: TextStyle(color: cs.error, fontSize: 12)),
            Row(
              children: [
                TextButton(
                  onPressed: _saving
                      ? null
                      : () => setState(() => _editing = false),
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _saving ? null : _saveName,
                  child: _saving
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child:
                              CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
            const Divider(height: 24),
          ],

          // Block type chip
          Wrap(
            spacing: 8,
            children: [
              Chip(
                label: Text(blockType),
                avatar: const Icon(Icons.category_outlined, size: 14),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),

          // Properties (if any)
          if (widget.block['properties'] is Map &&
              (widget.block['properties'] as Map).isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('Properties',
                style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            ...((widget.block['properties'] as Map).entries.map(
                  (e) => Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      children: [
                        Text('${e.key}: ',
                            style: const TextStyle(
                                fontWeight: FontWeight.w500)),
                        Expanded(
                          child: Text(e.value?.toString() ?? ''),
                        ),
                      ],
                    ),
                  ),
                )),
          ],

          const SizedBox(height: 24),

          // Children
          Row(
            children: [
              Text('Children',
                  style: Theme.of(context).textTheme.titleMedium),
              const Spacer(),
              TextButton.icon(
                onPressed: _addChild,
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Add'),
              ),
            ],
          ),
          const SizedBox(height: 8),

          if (_loadingChildren)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: CircularProgressIndicator(),
              ),
            )
          else if (_children.isEmpty)
            Text(
              'No children yet',
              style: TextStyle(color: cs.onSurfaceVariant),
            )
          else
            ...(_children.map(
              (c) => ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  (c['children'] as List?)?.isNotEmpty == true
                      ? Icons.folder_outlined
                      : Icons.article_outlined,
                  color: cs.primary,
                ),
                title: Text(c['name']?.toString() ?? '—'),
                subtitle: Text(
                  c['block_type']?.toString() ?? 'default',
                  style: const TextStyle(fontSize: 11),
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => BlockDetailPage(
                        block: c,
                        onChanged: () {
                          _refreshChildren();
                          widget.onChanged();
                        },
                      ),
                    ),
                  );
                },
              ),
            )),
        ],
      ),
    );
  }
}
