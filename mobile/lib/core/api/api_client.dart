import 'dart:async';
import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../config.dart';
import '../services/secure_storage_service.dart';

part 'api_client.g.dart';

@riverpod
Dio dio(DioRef ref) {
  // Mutex to prevent concurrent token refresh attempts
  Completer<bool>? refreshCompleter;

  final dio = Dio(
    BaseOptions(
      baseUrl: AppConfig.defaultBaseUrl,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 3),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ),
  );

  // Auth: add Bearer token to requests; on 401 try refresh and retry once
  dio.interceptors.add(InterceptorsWrapper(
    onRequest: (options, handler) async {
      final token = await SecureStorageService.instance.getAccessToken();
      if (token != null && token.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    },
    onError: (error, handler) async {
      if (error.response?.statusCode != 401) {
        return handler.next(error);
      }

      // If another request is already refreshing, wait for it
      if (refreshCompleter != null) {
        final success = await refreshCompleter!.future;
        if (success) {
          final token = await SecureStorageService.instance.getAccessToken();
          error.requestOptions.headers['Authorization'] = 'Bearer $token';
          final retry = await dio.fetch(error.requestOptions);
          return handler.resolve(retry);
        }
        return handler.next(error);
      }

      final refreshToken = await SecureStorageService.instance.getRefreshToken();
      if (refreshToken == null || refreshToken.isEmpty) {
        return handler.next(error);
      }

      refreshCompleter = Completer<bool>();
      try {
        final res = await dio.post(
          '/auth/refresh',
          data: {'refresh_token': refreshToken},
        );
        final data = res.data as Map<String, dynamic>;
        if (data['access_token'] != null) {
          await SecureStorageService.instance.setAccessToken(data['access_token'] as String);
        }
        if (data['refresh_token'] != null) {
          await SecureStorageService.instance.setRefreshToken(data['refresh_token'] as String);
        }
        if (data['user_id'] != null) {
          await SecureStorageService.instance.setUserId(data['user_id'] as String);
        }
        refreshCompleter!.complete(true);
        refreshCompleter = null;
        final opts = error.requestOptions;
        opts.headers['Authorization'] = 'Bearer ${data['access_token']}';
        final retry = await dio.fetch(opts);
        return handler.resolve(retry);
      } catch (_) {
        refreshCompleter!.complete(false);
        refreshCompleter = null;
        return handler.next(error);
      }
    },
  ));

  dio.interceptors.add(LogInterceptor(
    requestBody: true,
    responseBody: true,
  ));

  return dio;
}

@riverpod
ApiClient apiClient(ApiClientRef ref) {
  return ApiClient(ref.watch(dioProvider));
}

class ApiClient {
  final Dio _dio;

  ApiClient(this._dio);

  /// Expose the internal Dio instance for services that need direct access
  Dio get dio => _dio;

  Future<Response> get(String path, {Map<String, dynamic>? queryParameters}) async {
    try {
      return await _dio.get(path, queryParameters: queryParameters);
    } catch (e) {
      rethrow;
    }
  }

  Future<Response> post(String path, {dynamic data}) async {
    try {
      return await _dio.post(path, data: data);
    } catch (e) {
      rethrow;
    }
  }
  
  // Update base URL dynamically (e.g. after user inputs IP)
  void updateBaseUrl(String url) {
    _dio.options.baseUrl = url;
  }
}
