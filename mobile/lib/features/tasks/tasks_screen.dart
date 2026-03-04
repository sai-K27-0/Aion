import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';

/// Simplified Tasks screen for phone UI
class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});

  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends ConsumerState<TasksScreen> {
  List<TaskItem> _tasks = [];
  bool _isLoading = true;
  String _filter = 'all'; // all, today, completed

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  Future<void> _loadTasks() async {
    setState(() => _isLoading = true);

    try {
      final client = ref.read(apiClientProvider);
      // Load all blocks and extract todos
      final response = await client.get('/blocks/tree?max_depth=3');
      final blocks = response.data as List<dynamic>;

      final tasks = <TaskItem>[];
      _extractTasks(blocks, tasks);

      if (mounted) {
        setState(() {
          _tasks = tasks;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  void _extractTasks(List<dynamic> blocks, List<TaskItem> tasks) {
    for (final block in blocks) {
      final blockName = block['name'] ?? 'Untitled';
      final blockId = block['id'] ?? '';
      final todos = block['todos'] as List<dynamic>? ?? [];

      for (final todo in todos) {
        tasks.add(TaskItem(
          id: todo['id'] ?? '',
          text: todo['text'] ?? '',
          status: todo['status'] ?? 'not_started',
          priority: todo['priority'] ?? 'medium',
          date: todo['date'],
          blockId: blockId,
          blockName: blockName,
        ));
      }

      // Recurse into children
      final children = block['children'] as List<dynamic>? ?? [];
      _extractTasks(children, tasks);
    }
  }

  List<TaskItem> get _filteredTasks {
    switch (_filter) {
      case 'today':
        final today = DateTime.now().toIso8601String().substring(0, 10);
        return _tasks.where((t) => t.date == today).toList();
      case 'completed':
        return _tasks.where((t) => t.status == 'completed').toList();
      default:
        return _tasks.where((t) => t.status != 'completed').toList();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tasks'),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.filter_list),
            onSelected: (value) => setState(() => _filter = value),
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'all',
                child: Row(
                  children: [
                    Icon(Icons.list, 
                        color: _filter == 'all' 
                            ? Theme.of(context).colorScheme.primary 
                            : null),
                    const SizedBox(width: 8),
                    const Text('Active'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'today',
                child: Row(
                  children: [
                    Icon(Icons.today,
                        color: _filter == 'today'
                            ? Theme.of(context).colorScheme.primary
                            : null),
                    const SizedBox(width: 8),
                    const Text('Today'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'completed',
                child: Row(
                  children: [
                    Icon(Icons.check_circle,
                        color: _filter == 'completed'
                            ? Theme.of(context).colorScheme.primary
                            : null),
                    const SizedBox(width: 8),
                    const Text('Completed'),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _filteredTasks.isEmpty
              ? RefreshIndicator(
                  onRefresh: _loadTasks,
                  child: SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    child: SizedBox(
                      height: MediaQuery.of(context).size.height - 200,
                      child: _buildEmptyState(),
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadTasks,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _filteredTasks.length,
                    itemBuilder: (context, index) {
                      final task = _filteredTasks[index];
                      return _TaskTile(
                        task: task,
                        onToggle: () => _toggleTask(task),
                        onTap: () => _showTaskDetails(task),
                      );
                    },
                  ),
                ),
      floatingActionButton: FloatingActionButton(
        onPressed: _showQuickAddDialog,
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            _filter == 'completed' ? Icons.celebration : Icons.task_alt,
            size: 64,
            color: Theme.of(context).colorScheme.primary.withOpacity(0.5),
          ),
          const SizedBox(height: 16),
          Text(
            _filter == 'completed'
                ? 'No completed tasks'
                : _filter == 'today'
                    ? 'No tasks for today'
                    : 'All caught up!',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.grey,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Tap + to add a new task',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Colors.grey[600],
                ),
          ),
        ],
      ),
    );
  }

  void _toggleTask(TaskItem task) async {
    final newStatus = task.status == 'completed' ? 'not_started' : 'completed';
    
    // Optimistic update
    setState(() {
      final index = _tasks.indexWhere((t) => t.id == task.id);
      if (index >= 0) {
        _tasks[index] = task.copyWith(status: newStatus);
      }
    });

    // TODO: Update on server via API
  }

  void _showTaskDetails(TaskItem task) {
    showModalBottomSheet(
      context: context,
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _PriorityBadge(priority: task.priority),
                const Spacer(),
                _StatusBadge(status: task.status),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              task.text,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.folder_outlined, size: 16),
                const SizedBox(width: 4),
                Text(
                  task.blockName,
                  style: TextStyle(color: Colors.grey[500]),
                ),
              ],
            ),
            if (task.date != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.calendar_today, size: 16),
                  const SizedBox(width: 4),
                  Text(
                    task.date!,
                    style: TextStyle(color: Colors.grey[500]),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _ActionButton(
                  icon: task.status == 'completed'
                      ? Icons.restart_alt
                      : Icons.check,
                  label: task.status == 'completed' ? 'Reopen' : 'Complete',
                  onPressed: () {
                    Navigator.pop(context);
                    _toggleTask(task);
                  },
                ),
                _ActionButton(
                  icon: Icons.edit,
                  label: 'Edit',
                  onPressed: () {
                    Navigator.pop(context);
                    // TODO: Show edit dialog
                  },
                ),
                _ActionButton(
                  icon: Icons.delete,
                  label: 'Delete',
                  color: Colors.red,
                  onPressed: () {
                    Navigator.pop(context);
                    // TODO: Delete task
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showQuickAddDialog() {
    final controller = TextEditingController();
    
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
          left: 16,
          right: 16,
          top: 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              autofocus: true,
              decoration: InputDecoration(
                hintText: 'What needs to be done?',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: () {
                    if (controller.text.trim().isNotEmpty) {
                      Navigator.pop(context);
                      _createQuickTask(controller.text.trim());
                    }
                  },
                ),
              ),
              onSubmitted: (value) {
                if (value.trim().isNotEmpty) {
                  Navigator.pop(context);
                  _createQuickTask(value.trim());
                }
              },
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  void _createQuickTask(String text) async {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Creating task: "$text"')),
    );

    // TODO: Create task via AI or direct API
    // For now, just reload to show any server-side created tasks
    await Future.delayed(const Duration(seconds: 1));
    _loadTasks();
  }
}

class TaskItem {
  final String id;
  final String text;
  final String status;
  final String priority;
  final String? date;
  final String blockId;
  final String blockName;

  TaskItem({
    required this.id,
    required this.text,
    required this.status,
    required this.priority,
    this.date,
    required this.blockId,
    required this.blockName,
  });

  TaskItem copyWith({
    String? id,
    String? text,
    String? status,
    String? priority,
    String? date,
    String? blockId,
    String? blockName,
  }) {
    return TaskItem(
      id: id ?? this.id,
      text: text ?? this.text,
      status: status ?? this.status,
      priority: priority ?? this.priority,
      date: date ?? this.date,
      blockId: blockId ?? this.blockId,
      blockName: blockName ?? this.blockName,
    );
  }
}

class _TaskTile extends StatelessWidget {
  final TaskItem task;
  final VoidCallback onToggle;
  final VoidCallback onTap;

  const _TaskTile({
    required this.task,
    required this.onToggle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isCompleted = task.status == 'completed';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 56),
          child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              GestureDetector(
                onTap: onToggle,
                child: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: isCompleted
                        ? Theme.of(context).colorScheme.primary
                        : Colors.transparent,
                    border: Border.all(
                      color: isCompleted
                          ? Theme.of(context).colorScheme.primary
                          : Colors.grey,
                      width: 2,
                    ),
                  ),
                  child: isCompleted
                      ? const Icon(Icons.check, size: 20, color: Colors.white)
                      : null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      task.text,
                      style: TextStyle(
                        decoration: isCompleted
                            ? TextDecoration.lineThrough
                            : null,
                        color: isCompleted ? Colors.grey : null,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Text(
                          task.blockName,
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.grey[600],
                          ),
                        ),
                        if (task.date != null) ...[
                          const SizedBox(width: 8),
                          Icon(Icons.calendar_today,
                              size: 12, color: Colors.grey[600]),
                          const SizedBox(width: 2),
                          Text(
                            task.date!,
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.grey[600],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              _PriorityDot(priority: task.priority),
            ],
          ),
        ),
        ),
      ),
    );
  }
}

class _PriorityDot extends StatelessWidget {
  final String priority;

  const _PriorityDot({required this.priority});

  @override
  Widget build(BuildContext context) {
    Color color;
    switch (priority) {
      case 'high':
        color = Colors.red;
        break;
      case 'medium':
        color = Colors.orange;
        break;
      default:
        color = Colors.green;
    }

    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
      ),
    );
  }
}

class _PriorityBadge extends StatelessWidget {
  final String priority;

  const _PriorityBadge({required this.priority});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;
    switch (priority) {
      case 'high':
        color = Colors.red;
        label = 'High';
        break;
      case 'medium':
        color = Colors.orange;
        label = 'Medium';
        break;
      default:
        color = Colors.green;
        label = 'Low';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;
    switch (status) {
      case 'completed':
        color = Colors.green;
        label = 'Completed';
        break;
      case 'in_progress':
        color = Colors.blue;
        label = 'In Progress';
        break;
      case 'on_hold':
        color = Colors.orange;
        label = 'On Hold';
        break;
      default:
        color = Colors.grey;
        label = 'Not Started';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final Color? color;

  const _ActionButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color),
          const SizedBox(height: 4),
          Text(label, style: TextStyle(color: color, fontSize: 12)),
        ],
      ),
    );
  }
}
