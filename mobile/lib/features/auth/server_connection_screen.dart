import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/config.dart';

class ServerConnectionScreen extends ConsumerStatefulWidget {
  const ServerConnectionScreen({super.key});

  @override
  ConsumerState<ServerConnectionScreen> createState() => _ServerConnectionScreenState();
}

class _ServerConnectionScreenState extends ConsumerState<ServerConnectionScreen> {
  late TextEditingController _controller;
  bool _isLoading = false;
  bool _isInitializing = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
    _initializeUrl();
  }

  Future<void> _initializeUrl() async {
    try {
      final savedUrl = await AppConfig.getServerUrl();
      if (mounted) {
        setState(() {
          _controller.text = savedUrl;
          _isInitializing = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _controller.text = AppConfig.defaultBaseUrl;
          _isInitializing = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final url = _controller.text.trim();
    
    // Validate URL format
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setState(() {
        _error = 'URL must start with http:// or https://';
        _isLoading = false;
      });
      return;
    }

    final client = ref.read(apiClientProvider);

    try {
      client.updateBaseUrl(url);
      
      // Test connection with a simple endpoint
      final response = await client.get('/ai/status');
      
      // Save successful URL
      await AppConfig.setServerUrl(url);

      if (mounted) {
        // Show success and navigate to home
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Connected to Aion server'),
            backgroundColor: Colors.green,
          ),
        );
        
        // Navigate to home screen
        context.go('/home');
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Connection failed. Check the URL and ensure the server is running.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _useDefault() {
    setState(() {
      _controller.text = AppConfig.defaultBaseUrl;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isInitializing) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(),
        ),
      );
    }

    final isPhysicalDevice = AppConfig.isPhysicalDevice;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Logo
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: const Color(0xFF6366f1).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(
                    Icons.hub,
                    size: 48,
                    color: Color(0xFF6366f1),
                  ),
                ),
                const SizedBox(height: 32),
                
                // Title
                Text(
                  'Connect to Aion',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Enter your Aion server URL to sync your data',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.grey[600],
                  ),
                  textAlign: TextAlign.center,
                ),
                
                // Physical device warning
                if (isPhysicalDevice) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.amber.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.amber.withOpacity(0.3)),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.info_outline, color: Colors.amber[700], size: 20),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            'Physical device detected. Use your computer\'s IP address (e.g., 192.168.1.x:8000)',
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.amber[800],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                
                const SizedBox(height: 24),
                
                // URL Input
                TextField(
                  controller: _controller,
                  decoration: InputDecoration(
                    labelText: 'Server URL',
                    hintText: 'http://192.168.1.x:8000/api/v1',
                    border: const OutlineInputBorder(),
                    errorText: _error,
                    prefixIcon: const Icon(Icons.link),
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.restore),
                      tooltip: 'Use default URL',
                      onPressed: _useDefault,
                    ),
                  ),
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                ),
                const SizedBox(height: 24),
                
                // Connect Button
                ElevatedButton(
                  onPressed: _isLoading ? null : _connect,
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    backgroundColor: const Color(0xFF6366f1),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.power),
                            SizedBox(width: 8),
                            Text('Connect'),
                          ],
                        ),
                ),
                
                const SizedBox(height: 32),
                
                // Platform info
                Text(
                  'Platform: ${AppConfig.platformName}',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.grey[500],
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
