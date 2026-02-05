import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';
import 'core/services/isar_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Initialize Isar database
  try {
    await IsarService.init();
    debugPrint('Isar database initialized successfully');
  } catch (e) {
    debugPrint('Failed to initialize Isar: $e');
    // Continue anyway - app can work without local DB
  }

  runApp(
    const ProviderScope(
      child: AionApp(),
    ),
  );
}
