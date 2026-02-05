import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/auth/server_connection_screen.dart';
import '../features/home/home_screen.dart';
import '../features/home/tablet_home_screen.dart';

/// Check if device is tablet (screen width > 600dp)
bool isTablet(BuildContext context) {
  final shortestSide = MediaQuery.of(context).size.shortestSide;
  return shortestSide >= 600;
}

/// Router provider for navigation
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/connect',
    debugLogDiagnostics: true,
    routes: [
      GoRoute(
        path: '/connect',
        name: 'connect',
        builder: (context, state) => const ServerConnectionScreen(),
      ),
      GoRoute(
        path: '/home',
        name: 'home',
        builder: (context, state) {
          // Use tablet UI for larger screens
          if (isTablet(context)) {
            return const TabletHomeScreen();
          }
          return const HomeScreen();
        },
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.red),
            const SizedBox(height: 16),
            Text('Page not found: ${state.uri}'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => context.go('/connect'),
              child: const Text('Go Home'),
            ),
          ],
        ),
      ),
    ),
  );
});
