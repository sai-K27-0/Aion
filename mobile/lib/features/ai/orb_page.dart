import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

class _OrbResult {
  const _OrbResult({required this.summary, required this.blocks});
  final String summary;
  final List<Map<String, dynamic>> blocks;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

class OrbPage extends ConsumerStatefulWidget {
  const OrbPage({super.key});

  @override
  ConsumerState<OrbPage> createState() => _OrbPageState();
}

class _OrbPageState extends ConsumerState<OrbPage>
    with SingleTickerProviderStateMixin {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  late final AnimationController _pulseController;
  late final Animation<double> _pulse;

  bool _loading = false;
  String? _error;
  final List<_OrbResult> _history = [];

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _pulse = Tween<double>(begin: 0.92, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.post('/ai/smart-action', data: {'message': text});
      final data = resp.data as Map<String, dynamic>;
      final created = (data['blocks_created'] as List? ?? [])
          .cast<Map<String, dynamic>>();
      final summary = (data['summary'] ?? data['response'] ?? '').toString();
      setState(() {
        _history.insert(0, _OrbResult(summary: summary, blocks: created));
        _loading = false;
      });
      _controller.clear();
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          0,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SafeArea(
      child: Column(
        children: [
          // Orb
          Expanded(
            flex: 3,
            child: Center(
              child: AnimatedBuilder(
                animation: _pulse,
                builder: (_, child) => Transform.scale(
                  scale: _pulse.value,
                  child: child,
                ),
                child: _OrbWidget(loading: _loading),
              ),
            ),
          ),

          // Input
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    enabled: !_loading,
                    onSubmitted: (_) => _submit(),
                    decoration: InputDecoration(
                      hintText: 'Ask Aion anything…',
                      filled: true,
                      fillColor: cs.surfaceContainerHigh,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(28),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 14,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _loading ? null : _submit,
                  style: FilledButton.styleFrom(
                    shape: const CircleBorder(),
                    padding: const EdgeInsets.all(14),
                  ),
                  child: _loading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.send_rounded),
                ),
              ],
            ),
          ),

          // Error
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text(
                _error!,
                style: TextStyle(color: cs.error, fontSize: 12),
              ),
            ),

          // History
          if (_history.isNotEmpty)
            Expanded(
              flex: 4,
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                itemCount: _history.length,
                itemBuilder: (_, i) => _ResultCard(result: _history[i]),
              ),
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Orb widget
// ---------------------------------------------------------------------------

class _OrbWidget extends StatelessWidget {
  const _OrbWidget({required this.loading});
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return CustomPaint(
      size: const Size(180, 180),
      painter: _OrbPainter(color: cs.primary),
      child: SizedBox(
        width: 180,
        height: 180,
        child: Center(
          child: loading
              ? CircularProgressIndicator(color: cs.onPrimary)
              : Icon(Icons.auto_awesome, size: 56, color: cs.onPrimary),
        ),
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  _OrbPainter({required this.color});
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    // Glow rings
    for (int i = 3; i >= 1; i--) {
      canvas.drawCircle(
        center,
        radius + i * 10,
        Paint()
          ..color = color.withAlpha((0.06 * i * 40).round())
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20),
      );
    }

    // Gradient orb
    canvas.drawCircle(
      center,
      radius - 4,
      Paint()
        ..shader = RadialGradient(
          colors: [color.withAlpha(220), color.withAlpha(180)],
          center: const Alignment(-0.3, -0.3),
        ).createShader(Rect.fromCircle(center: center, radius: radius)),
    );

    // Faceted triangle (logo)
    final path = Path();
    for (int i = 0; i < 3; i++) {
      final angle = -math.pi / 2 + i * 2 * math.pi / 3;
      final x = center.dx + (radius * 0.45) * math.cos(angle);
      final y = center.dy + (radius * 0.45) * math.sin(angle);
      i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
    }
    path.close();
    canvas.drawPath(
      path,
      Paint()
        ..color = Colors.white.withAlpha(60)
        ..style = PaintingStyle.fill,
    );
    canvas.drawPath(
      path,
      Paint()
        ..color = Colors.white.withAlpha(160)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
  }

  @override
  bool shouldRepaint(_OrbPainter old) => old.color != color;
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});
  final _OrbResult result;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (result.summary.isNotEmpty)
              Text(
                result.summary,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            if (result.blocks.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: result.blocks
                    .map(
                      (b) => Chip(
                        avatar: const Icon(Icons.add_box_outlined, size: 14),
                        label: Text(
                          b['name']?.toString() ?? '—',
                          style: const TextStyle(fontSize: 12),
                        ),
                        backgroundColor: cs.primaryContainer,
                        labelStyle: TextStyle(color: cs.onPrimaryContainer),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    )
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
