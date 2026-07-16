import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

// Production Railway deployment — see railway_deployment_notes memory for
// the app's live URL. Real patients' devices can't reach 10.0.2.2 (that's
// only a valid address from inside the Android emulator), so this must
// point at the actual public server before the app is useful off a dev
// machine. HTTPS here is also what activates the pinned-CA check in
// _pinHttpClient below — there's no TLS handshake to pin against plain HTTP.
const _baseUrl = 'https://web-production-c76a8.up.railway.app/api/v1/';

const _paths = {'auth/login/', 'auth/refresh/', 'auth/accept-invite/'};

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

class ApiClient {
  /// [pinnedCaCertBytes] is the DER/PEM bytes of the one CA this app will
  /// ever trust (assets/isrg_root_x1.pem — ISRG Root X1, the root that
  /// ultimately signs Railway's Let's Encrypt certificate). Pass null to
  /// fall back to the system trust store (only relevant for the plain-HTTP
  /// local dev server, which has no TLS handshake to pin in the first place).
  ApiClient({Uint8List? pinnedCaCertBytes, this.onSessionExpired})
      : dio = Dio(BaseOptions(baseUrl: _baseUrl)),
        _refreshDio = Dio(BaseOptions(baseUrl: _baseUrl)) {
    if (pinnedCaCertBytes != null) {
      _pinHttpClient(dio, pinnedCaCertBytes);
      _pinHttpClient(_refreshDio, pinnedCaCertBytes);
    }
    dio.interceptors.add(
      InterceptorsWrapper(onRequest: _onRequest, onError: _onError),
    );
  }

  /// Restricts the given Dio instance's trust store to *only* the pinned CA.
  /// Deliberately does not set a badCertificateCallback: HttpClient already
  /// fails closed (throws HandshakeException) when the presented chain
  /// doesn't validate against this restricted SecurityContext, which is
  /// exactly the behavior pinning needs — no MITM using a different,
  /// even otherwise-trusted, CA can succeed.
  void _pinHttpClient(Dio target, Uint8List caCertBytes) {
    final adapter = target.httpClientAdapter as IOHttpClientAdapter;
    adapter.createHttpClient = () {
      final context = SecurityContext(withTrustedRoots: false)
        ..setTrustedCertificatesBytes(caCertBytes);
      return HttpClient(context: context);
    };
  }

  final Dio dio;
  final _storage = const FlutterSecureStorage();
  // Plain client with no interceptors, so refreshing never recurses into
  // the auth-error handling below.
  final Dio _refreshDio;

  /// Called when the refresh token itself is rejected (expired/blacklisted/
  /// invalid) — the caller should navigate back to LoginScreen, since no
  /// amount of retrying will recover a request in this state.
  final void Function()? onSessionExpired;

  String? _accessToken;

  Future<void> _onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (!_paths.contains(options.path)) {
      _accessToken ??= await _storage.read(key: 'access_token');
      if (_accessToken != null) {
        options.headers['Authorization'] = 'Bearer $_accessToken';
      }
    }
    handler.next(options);
  }

  Future<void> _onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final isAuthRequest = _paths.contains(err.requestOptions.path);
    if (err.response?.statusCode != 401 || isAuthRequest) {
      handler.next(err);
      return;
    }

    final refreshToken = await _storage.read(key: 'refresh_token');
    if (refreshToken == null) {
      handler.next(err);
      return;
    }

    try {
      // ROTATE_REFRESH_TOKENS is on server-side, so the response always
      // carries a new refresh token that must overwrite the stored one.
      final response = await _refreshDio.post(
        'auth/refresh/',
        data: {'refresh': refreshToken},
      );
      await _saveTokens(
        access: response.data['access'] as String,
        refresh: response.data['refresh'] as String,
      );

      final retryOptions = err.requestOptions;
      retryOptions.headers['Authorization'] = 'Bearer $_accessToken';
      final retryResponse = await dio.fetch(retryOptions);
      handler.resolve(retryResponse);
    } on DioException {
      await clearTokens();
      onSessionExpired?.call();
      handler.next(err);
    }
  }

  Future<void> _saveTokens({required String access, required String refresh}) async {
    _accessToken = access;
    await _storage.write(key: 'access_token', value: access);
    await _storage.write(key: 'refresh_token', value: refresh);
  }

  Future<void> clearTokens() async {
    _accessToken = null;
    await _storage.delete(key: 'access_token');
    await _storage.delete(key: 'refresh_token');
  }

  Future<bool> hasStoredSession() async {
    return await _storage.read(key: 'refresh_token') != null;
  }

  Future<void> login(String username, String password) async {
    final response = await dio.post('auth/login/', data: {
      'username': username,
      'password': password,
    });
    await _saveTokens(
      access: response.data['access'] as String,
      refresh: response.data['refresh'] as String,
    );
  }

  Future<void> acceptInvite(String token, String password) async {
    final response = await dio.post('auth/accept-invite/', data: {
      'token': token,
      'password': password,
    });
    await _saveTokens(
      access: response.data['access'] as String,
      refresh: response.data['refresh'] as String,
    );
  }

  Future<Map<String, dynamic>> fetchDashboard() async {
    final response = await dio.get('dashboard/');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchProfile() async {
    final response = await dio.get('profile/');
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> fields) async {
    final response = await dio.patch('profile/', data: fields);
    return response.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> fetchAppointments({String scope = 'upcoming'}) async {
    final response = await dio.get('appointments/', queryParameters: {'scope': scope});
    return response.data['results'] as List<dynamic>;
  }

  Future<List<dynamic>> fetchAppointmentRequests() async {
    final response = await dio.get('appointment-requests/');
    return response.data['results'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> createAppointmentRequest(Map<String, dynamic> fields) async {
    final response = await dio.post('appointment-requests/', data: fields);
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateAppointmentRequest(int id, Map<String, dynamic> fields) async {
    final response = await dio.patch('appointment-requests/$id/', data: fields);
    return response.data as Map<String, dynamic>;
  }

  Future<void> cancelAppointmentRequest(int id) async {
    await dio.delete('appointment-requests/$id/');
  }

  Future<List<dynamic>> fetchTreatmentRecords() async {
    final response = await dio.get('records/treatment-records/');
    return response.data['results'] as List<dynamic>;
  }

  Future<List<dynamic>> fetchTreatmentPlans() async {
    final response = await dio.get('records/treatment-plans/');
    return response.data['results'] as List<dynamic>;
  }

  Future<List<dynamic>> fetchInvoices() async {
    final response = await dio.get('invoices/');
    return response.data['results'] as List<dynamic>;
  }

  Future<List<dynamic>> fetchMessages() async {
    final response = await dio.get('messages/');
    return response.data['results'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> sendMessage(String body) async {
    final response = await dio.post('messages/', data: {'body': body});
    return response.data as Map<String, dynamic>;
  }

  Future<void> markMessagesRead() async {
    await dio.post('messages/mark-read/');
  }

  Future<void> registerDevice(String fcmToken, String platform) async {
    await dio.post('devices/register/', data: {
      'fcm_token': fcmToken,
      'platform': platform,
    });
  }

  /// Extracts a human-readable message from a DRF error response, which may
  /// be a list of strings, a dict of field -> [messages], or a plain string.
  static String errorMessage(Object error) {
    if (error is DioException && error.response?.data != null) {
      final data = error.response!.data;
      if (data is Map) {
        final firstValue = data.values.isNotEmpty ? data.values.first : null;
        if (firstValue is List && firstValue.isNotEmpty) {
          return firstValue.first.toString();
        }
        if (firstValue != null) return firstValue.toString();
      }
      if (data is List && data.isNotEmpty) return data.first.toString();
    }
    return 'Something went wrong. Please try again.';
  }
}
