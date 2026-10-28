/// Centralized API configuration for WebRAG.
///
/// The base URL defaults to the laptop's LAN IP (10.201.169.154:8000).
/// Override at compile time via:
///   flutter run --dart-define=API_BASE_URL=http://<your-ip>:8000
class ApiConfig {
  /// Backend base URL — injected at compile time via --dart-define.
  /// Defaults to the development laptop's LAN address.
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.35.150.154:8000',
  );

  /// Connection timeout for all HTTP requests.
  static const Duration connectTimeout = Duration(seconds: 15);

  /// Read timeout for all HTTP requests (long for crawl status polling).
  static const Duration receiveTimeout = Duration(seconds: 60);

  /// Returns a human-readable description of the active backend target.
  static String get description {
    if (baseUrl.contains('10.0.2.2')) return 'Android Emulator (localhost)';
    if (baseUrl.contains('127.0.0.1') || baseUrl.contains('localhost')) {
      return 'Localhost (may not work on physical device)';
    }
    if (baseUrl.startsWith('https://')) return 'Deployed Backend ($baseUrl)';
    return 'LAN Backend ($baseUrl)';
  }
}
