import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api/api_client.dart';
import '../../core/config.dart';
import '../../core/services/secure_storage_service.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  // AI
  String _aiProvider = 'ollama';
  String _aiModel = '';
  String _aiApiKey = '';
  Map<String, dynamic>? _aiStatus;
  bool _loadingAi = false;

  // Account
  Map<String, dynamic>? _me;
  bool _loadingMe = false;

  // Devices
  List<Map<String, dynamic>> _devices = [];
  bool _loadingDevices = false;

  // Server
  String _serverUrl = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    _loadAiSettings();
    _loadAiStatus();
    _loadMe();
    _loadDevices();
    _loadServerUrl();
  }

  Future<void> _loadAiSettings() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _aiProvider = prefs.getString('ai_provider') ?? 'ollama';
      _aiModel = prefs.getString('ai_model') ?? '';
      _aiApiKey = prefs.getString('ai_api_key') ?? '';
    });
  }

  Future<void> _saveAiSettings() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('ai_provider', _aiProvider);
    await prefs.setString('ai_model', _aiModel);
    await prefs.setString('ai_api_key', _aiApiKey);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('AI settings saved')),
      );
    }
  }

  Future<void> _loadAiStatus() async {
    setState(() => _loadingAi = true);
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/ai/status');
      setState(() {
        _aiStatus = resp.data as Map<String, dynamic>?;
        _loadingAi = false;
      });
    } catch (_) {
      setState(() => _loadingAi = false);
    }
  }

  Future<void> _loadMe() async {
    setState(() => _loadingMe = true);
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/auth/me');
      setState(() {
        _me = resp.data as Map<String, dynamic>?;
        _loadingMe = false;
      });
    } catch (_) {
      setState(() => _loadingMe = false);
    }
  }

  Future<void> _loadDevices() async {
    setState(() => _loadingDevices = true);
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/devices/');
      final data = resp.data as Map<String, dynamic>?;
      setState(() {
        _devices = ((data?['devices'] ?? []) as List)
            .cast<Map<String, dynamic>>();
        _loadingDevices = false;
      });
    } catch (_) {
      setState(() => _loadingDevices = false);
    }
  }

  Future<void> _loadServerUrl() async {
    final url = await AppConfig.getServerUrl();
    if (mounted) setState(() => _serverUrl = url);
  }

  Future<void> _signOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Sign out?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final client = ref.read(apiClientProvider);
      await client.post('/auth/logout');
    } catch (_) {}
    final storage = SecureStorageService.instance;
    await storage.clearAuthSession();
    if (mounted) context.go('/connect');
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _sectionTitle('AI Provider'),
          _AiSection(
            provider: _aiProvider,
            model: _aiModel,
            apiKey: _aiApiKey,
            status: _aiStatus,
            loading: _loadingAi,
            onProviderChanged: (v) => setState(() => _aiProvider = v),
            onModelChanged: (v) => setState(() => _aiModel = v),
            onApiKeyChanged: (v) => setState(() => _aiApiKey = v),
            onSave: _saveAiSettings,
            onRefreshStatus: _loadAiStatus,
          ),
          const SizedBox(height: 24),
          _sectionTitle('Account'),
          _AccountSection(
            me: _me,
            loading: _loadingMe,
            onSignOut: _signOut,
          ),
          const SizedBox(height: 24),
          _sectionTitle('Devices'),
          _DevicesSection(
            devices: _devices,
            loading: _loadingDevices,
            onRefresh: _loadDevices,
          ),
          const SizedBox(height: 24),
          _sectionTitle('Server'),
          _ServerSection(
            url: _serverUrl,
            onChangeServer: () => context.go('/connect'),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(String title) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          title.toUpperCase(),
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                letterSpacing: 1.2,
                color: Theme.of(context).colorScheme.primary,
              ),
        ),
      );
}

// ---------------------------------------------------------------------------
// AI section
// ---------------------------------------------------------------------------

class _AiSection extends StatelessWidget {
  const _AiSection({
    required this.provider,
    required this.model,
    required this.apiKey,
    required this.status,
    required this.loading,
    required this.onProviderChanged,
    required this.onModelChanged,
    required this.onApiKeyChanged,
    required this.onSave,
    required this.onRefreshStatus,
  });

  final String provider;
  final String model;
  final String apiKey;
  final Map<String, dynamic>? status;
  final bool loading;
  final void Function(String) onProviderChanged;
  final void Function(String) onModelChanged;
  final void Function(String) onApiKeyChanged;
  final VoidCallback onSave;
  final VoidCallback onRefreshStatus;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final statusDot = status != null
        ? (status!['available'] == true
            ? Colors.green
            : cs.error)
        : Colors.grey;
    final statusLabel = status != null
        ? (status!['available'] == true
            ? 'Available'
            : 'Unavailable')
        : 'Unknown';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Status row
            Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: statusDot,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text('$provider — $statusLabel'),
                const Spacer(),
                if (loading)
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  IconButton(
                    onPressed: onRefreshStatus,
                    icon: const Icon(Icons.refresh, size: 18),
                    padding: EdgeInsets.zero,
                  ),
              ],
            ),

            // Models list
            if (status?['models'] != null &&
                (status!['models'] as List).isNotEmpty) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                children: ((status!['models'] as List))
                    .take(5)
                    .map((m) => Chip(
                          label: Text(
                            m is Map ? (m['name'] ?? m) : m,
                            style: const TextStyle(fontSize: 11),
                          ),
                          visualDensity: VisualDensity.compact,
                          materialTapTargetSize:
                              MaterialTapTargetSize.shrinkWrap,
                        ))
                    .toList(),
              ),
            ],

            const Divider(height: 24),

            // Provider dropdown
            DropdownButtonFormField<String>(
              value: provider,
              decoration: const InputDecoration(
                labelText: 'Provider',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              items: const [
                DropdownMenuItem(
                    value: 'ollama', child: Text('Ollama (local)')),
                DropdownMenuItem(
                    value: 'openai', child: Text('OpenAI')),
                DropdownMenuItem(
                    value: 'anthropic', child: Text('Anthropic')),
              ],
              onChanged: (v) => onProviderChanged(v ?? 'ollama'),
            ),

            const SizedBox(height: 12),

            // Model
            TextFormField(
              initialValue: model,
              decoration: const InputDecoration(
                labelText: 'Model',
                hintText: 'e.g. llama3.2',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onChanged: onModelChanged,
            ),

            if (provider != 'ollama') ...[
              const SizedBox(height: 12),
              TextFormField(
                initialValue: apiKey,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'API Key',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onChanged: onApiKeyChanged,
              ),
            ],

            const SizedBox(height: 12),

            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.tonal(
                onPressed: onSave,
                child: const Text('Save'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Account section
// ---------------------------------------------------------------------------

class _AccountSection extends StatelessWidget {
  const _AccountSection({
    required this.me,
    required this.loading,
    required this.onSignOut,
  });

  final Map<String, dynamic>? me;
  final bool loading;
  final VoidCallback onSignOut;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (loading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    final username = me?['username']?.toString() ?? '—';
    final email = me?['email']?.toString() ?? '';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: cs.primaryContainer,
                  child: Text(
                    username.isNotEmpty
                        ? username[0].toUpperCase()
                        : '?',
                    style: TextStyle(
                      color: cs.onPrimaryContainer,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      username,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (email.isNotEmpty)
                      Text(
                        email,
                        style: TextStyle(
                          fontSize: 12,
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: onSignOut,
                icon: const Icon(Icons.logout, size: 16),
                label: const Text('Sign out'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: cs.error,
                  side: BorderSide(color: cs.error.withAlpha(100)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Devices section
// ---------------------------------------------------------------------------

class _DevicesSection extends StatelessWidget {
  const _DevicesSection({
    required this.devices,
    required this.loading,
    required this.onRefresh,
  });

  final List<Map<String, dynamic>> devices;
  final bool loading;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (loading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    return Card(
      child: Column(
        children: [
          ListTile(
            title: Text('${devices.length} registered device(s)'),
            trailing: IconButton(
              onPressed: onRefresh,
              icon: const Icon(Icons.refresh, size: 18),
            ),
          ),
          if (devices.isEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Text(
                'No devices registered',
                style: TextStyle(color: cs.onSurfaceVariant),
              ),
            )
          else
            ...devices.map(
              (d) => ListTile(
                leading: Icon(
                  _deviceIcon(d['device_type']?.toString() ?? ''),
                ),
                title: Text(d['device_name']?.toString() ?? '—'),
                subtitle: Text(
                  [
                    d['platform']?.toString() ?? '',
                    d['device_type']?.toString() ?? '',
                  ].where((s) => s.isNotEmpty).join(' · '),
                ),
                trailing: _deviceStatus(d, cs),
              ),
            ),
        ],
      ),
    );
  }

  IconData _deviceIcon(String type) {
    switch (type) {
      case 'desktop':
        return Icons.computer;
      case 'tablet':
        return Icons.tablet_android;
      case 'phone':
        return Icons.smartphone;
      default:
        return Icons.devices_other;
    }
  }

  Widget? _deviceStatus(Map<String, dynamic> d, ColorScheme cs) {
    final status =
        d['approval_status']?.toString() ?? d['status']?.toString() ?? '';
    if (status == 'approved' || d['token_valid'] == true) {
      return Icon(Icons.check_circle, color: Colors.green, size: 18);
    }
    if (status == 'pending') {
      return Chip(
        label: const Text('Pending', style: TextStyle(fontSize: 10)),
        backgroundColor: cs.errorContainer,
        labelStyle: TextStyle(color: cs.onErrorContainer),
        visualDensity: VisualDensity.compact,
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      );
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// Server section
// ---------------------------------------------------------------------------

class _ServerSection extends StatelessWidget {
  const _ServerSection({
    required this.url,
    required this.onChangeServer,
  });

  final String url;
  final VoidCallback onChangeServer;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        leading: Icon(Icons.dns_outlined, color: cs.primary),
        title: const Text('Backend server'),
        subtitle: Text(
          url.isEmpty ? 'Not configured' : url,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: onChangeServer,
      ),
    );
  }
}
