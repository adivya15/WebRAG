import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'api_config.dart';

/// Talks to the FastAPI WebRAG backend.
///
/// The backend URL is resolved from [ApiConfig.baseUrl], which is injected
/// at compile time via `--dart-define=API_BASE_URL=http://<your-lan-ip>:8000`.
/// No IP address is hardcoded in this file.
class OrchestratorService {
  final String baseUrl;

  OrchestratorService({String? baseUrl})
      : baseUrl = baseUrl ?? ApiConfig.baseUrl;

  // ── Internal helpers ─────────────────────────────────────────────────────

  /// Wraps every GET with a timeout and converts socket errors into friendly messages.
  Future<http.Response> _get(Uri url) async {
    try {
      return await http
          .get(url)
          .timeout(ApiConfig.receiveTimeout);
    } on SocketException catch (e) {
      throw Exception(
        'Cannot reach the backend at $baseUrl.\n'
        'Make sure:\n'
        '  1. FastAPI is running: uvicorn app.main:app --host 0.0.0.0 --port 8000\n'
        '  2. Your phone and laptop are on the same Wi-Fi network.\n'
        '  3. You passed the correct IP: --dart-define=API_BASE_URL=http://<laptop-ip>:8000\n'
        '(${e.message})',
      );
    } on Exception catch (e) {
      throw Exception('Network error: $e');
    }
  }

  /// Wraps every POST with a timeout and converts socket errors into friendly messages.
  Future<http.Response> _post(Uri url, Map<String, dynamic> body) async {
    try {
      return await http
          .post(url,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(body))
          .timeout(ApiConfig.receiveTimeout);
    } on SocketException catch (e) {
      throw Exception(
        'Cannot reach the backend at $baseUrl.\n'
        'Make sure FastAPI is running on your laptop '
        '(uvicorn app.main:app --host 0.0.0.0 --port 8000) '
        'and that you passed --dart-define=API_BASE_URL=http://<laptop-ip>:8000.\n'
        '(${e.message})',
      );
    } on Exception catch (e) {
      throw Exception('Network error: $e');
    }
  }

  // ── Connectivity ─────────────────────────────────────────────────────────

  Future<bool> ping() async {
    try {
      final url = Uri.parse('$baseUrl/ping');
      print('================================');
      print('Calling backend...');
      print('URL: $url  (${ApiConfig.description})');
      final res = await _get(url);
      print('Status: ${res.statusCode}  Body: ${res.body}');
      print('================================');
      return res.statusCode == 200;
    } catch (e) {
      print('PING FAILED: $e');
      return false;
    }
  }

  // ── Legacy AskHTE endpoints (preserved) ──────────────────────────────────

  Future<Map<String, dynamic>> query(
    String userQuery, {
    String userRole = 'technician',
    String? equipmentId,
    List<String>? agents,
    String? targetLanguage,
  }) async {
    final url = Uri.parse('$baseUrl/query');
    print('Sending query to: $url');
    final requestBody = {
      'query': userQuery,
      'user_role': userRole,
      'equipment_id': equipmentId,
      ?'agents': agents,
      ?'target_language': targetLanguage,
    };
    print('===== Outgoing Request Body =====');
    print(jsonEncode(requestBody));
    final res = await _post(url, requestBody);
    if (res.statusCode != 200) {
      throw Exception('Orchestrator error: ${res.statusCode}\n${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> listDocuments() async {
    final url = Uri.parse('$baseUrl/documents/list');
    final res = await _get(url);
    if (res.statusCode != 200) return [];
    return List<Map<String, dynamic>>.from(jsonDecode(res.body));
  }

  Future<Map<String, dynamic>> summarizeDocument(String docId,
      {String detailLevel = 'short'}) async {
    final url = Uri.parse('$baseUrl/documents/summarize');
    final res = await _post(url, {'doc_id': docId, 'detail_level': detailLevel});
    if (res.statusCode != 200) {
      throw Exception('Summarize error: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> compareDocuments(String docA, String docB) async {
    final url = Uri.parse('$baseUrl/documents/compare?doc_a=$docA&doc_b=$docB');
    final res = await _get(url);
    if (res.statusCode != 200) {
      throw Exception('Compare error: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  // ── WebRAG — Intelligent Website Mining Endpoints ────────────────────────

  /// Initiates a background crawl & indexing job for a target website.
  Future<Map<String, dynamic>> crawlWebsite(
    String url, {
    int maxPages = 30,
    int maxDepth = 2,
  }) async {
    final target = Uri.parse('$baseUrl/api/web/crawl');
    final res = await _post(target, {
      'url': url,
      'max_pages': maxPages,
      'max_depth': maxDepth,
    });
    if (res.statusCode != 200) {
      throw Exception('Crawl initiation failed: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Fetches real-time status and progress of a crawling job.
  Future<Map<String, dynamic>> getCrawlStatus(String jobId) async {
    final target = Uri.parse('$baseUrl/api/web/status/$jobId');
    final res = await _get(target);
    if (res.statusCode != 200) {
      throw Exception('Status check failed: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Lists all successfully indexed websites.
  Future<List<Map<String, dynamic>>> listIndexedWebsites() async {
    try {
      final target = Uri.parse('$baseUrl/api/web/websites');
      final res = await _get(target);
      if (res.statusCode != 200) return [];
      return List<Map<String, dynamic>>.from(jsonDecode(res.body));
    } catch (_) {
      return [];
    }
  }

  /// Lists all crawled pages for a given website ID.
  Future<List<Map<String, dynamic>>> listIndexedPages(String websiteId) async {
    try {
      final target = Uri.parse('$baseUrl/api/web/pages?website_id=$websiteId');
      final res = await _get(target);
      if (res.statusCode != 200) return [];
      return List<Map<String, dynamic>>.from(jsonDecode(res.body));
    } catch (_) {
      return [];
    }
  }

  /// Queries the indexed website content with grounded RAG and source citations.
  Future<Map<String, dynamic>> askWeb(
    String websiteId,
    String query, {
    int topK = 5,
  }) async {
    final target = Uri.parse('$baseUrl/api/web/chat');
    final res = await _post(target, {
      'website_id': websiteId,
      'query': query,
      'top_k': topK,
    });
    if (res.statusCode != 200) {
      throw Exception('WebRAG query error: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Fetches web data mining analytics, word frequencies, and distribution charts.
  Future<Map<String, dynamic>> getWebStats({String? websiteId}) async {
    final queryParam = (websiteId != null && websiteId.isNotEmpty)
        ? '?website_id=$websiteId'
        : '';
    final target = Uri.parse('$baseUrl/api/web/stats$queryParam');
    final res = await _get(target);
    if (res.statusCode != 200) {
      throw Exception('Web statistics error: ${res.statusCode} ${res.body}');
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Deletes a website's vector embeddings and catalog entry.
  Future<Map<String, dynamic>> deleteWebsiteIndex(String websiteId) async {
    final target = Uri.parse('$baseUrl/api/web/index/$websiteId');
    try {
      final res = await http
          .delete(target)
          .timeout(ApiConfig.receiveTimeout);
      if (res.statusCode != 200) {
        throw Exception('Delete failed: ${res.statusCode} ${res.body}');
      }
      return jsonDecode(res.body) as Map<String, dynamic>;
    } on SocketException catch (e) {
      throw Exception('Network error: ${e.message}');
    }
  }
}