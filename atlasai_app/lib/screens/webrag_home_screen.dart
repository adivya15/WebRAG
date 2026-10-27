import 'dart:async';
import 'package:flutter/material.dart';
import '../services/orchestrator_service.dart';
import '../theme/app_theme.dart';
import 'website_dashboard_screen.dart';
import 'web_chat_screen.dart';
import 'web_analytics_screen.dart';

/// WebRAG — Intelligent Website Mining & Question Answering System Home Screen
class WebRAGHomeScreen extends StatefulWidget {
  const WebRAGHomeScreen({super.key});

  @override
  State<WebRAGHomeScreen> createState() => _WebRAGHomeScreenState();
}

class _WebRAGHomeScreenState extends State<WebRAGHomeScreen> {
  final OrchestratorService _orchestrator = OrchestratorService();
  final TextEditingController _urlController = TextEditingController(text: 'https://en.wikipedia.org/wiki/Data_mining');

  int _maxPages = 30; // Must match one of the DropdownMenuItem values: 5, 15, 30, 50
  int _maxDepth = 2;

  bool _isCrawling = false;
  String? _activeJobId;
  String? _activeWebsiteId;
  int _crawlProgress = 0;
  String _crawlStatusText = 'Ready';
  String _currentCrawlingUrl = '';
  Timer? _statusTimer;

  List<Map<String, dynamic>> _indexedWebsites = [];
  bool _loadingWebsites = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _fetchIndexedWebsites();
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _fetchIndexedWebsites() async {
    setState(() => _loadingWebsites = true);
    try {
      final sites = await _orchestrator.listIndexedWebsites();
      if (mounted) {
        setState(() {
          _indexedWebsites = sites;
          _loadingWebsites = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingWebsites = false);
    }
  }

  void _startCrawling() async {
    final rawUrl = _urlController.text.trim();
    if (rawUrl.isEmpty) {
      _showSnackbar('Please enter a website URL');
      return;
    }

    setState(() {
      _isCrawling = true;
      _crawlProgress = 5;
      _crawlStatusText = 'Initiating crawl...';
      _currentCrawlingUrl = rawUrl;
      _errorMessage = null;
    });

    try {
      final res = await _orchestrator.crawlWebsite(
        rawUrl,
        maxPages: _maxPages,
        maxDepth: _maxDepth,
      );

      final jobId = res['jobId'] as String;
      final siteId = res['websiteId'] as String;

      setState(() {
        _activeJobId = jobId;
        _activeWebsiteId = siteId;
      });

      _startStatusPolling(jobId);
    } catch (e) {
      setState(() {
        _isCrawling = false;
        _errorMessage = e.toString().replaceAll('Exception:', '').trim();
      });
      _showSnackbar('Crawling initiation failed: $_errorMessage');
    }
  }

  void _startStatusPolling(String jobId) {
    _statusTimer?.cancel();
    _statusTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      try {
        final status = await _orchestrator.getCrawlStatus(jobId);
        final state = status['status'] as String? ?? 'unknown';
        final progress = (status['progress'] as num?)?.toInt() ?? 0;
        final currentUrl = status['currentUrl'] as String? ?? '';
        final error = status['error'] as String?;

        if (mounted) {
          setState(() {
            _crawlProgress = progress;
            _crawlStatusText = state.toUpperCase();
            _currentCrawlingUrl = currentUrl;
          });

          if (state == 'completed') {
            timer.cancel();
            setState(() {
              _isCrawling = false;
              _crawlProgress = 100;
              _crawlStatusText = 'COMPLETED';
            });
            _fetchIndexedWebsites();
            _showSnackbar('Crawling & Vector Indexing Completed!');
          } else if (state == 'failed') {
            timer.cancel();
            setState(() {
              _isCrawling = false;
              _errorMessage = error ?? 'Crawl failed.';
              _crawlStatusText = 'FAILED';
            });
            _showSnackbar('Crawl failed: ${_errorMessage ?? "Unknown error"}');
          }
        }
      } catch (e) {
        // Continue polling or retry
      }
    });
  }

  void _showSnackbar(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating),
    );
  }

  Future<void> _deleteWebsite(String websiteId, String domain) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove Indexed Website?'),
        content: Text('Are you sure you want to delete all indexed data and vector embeddings for $domain?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await _orchestrator.deleteWebsiteIndex(websiteId);
        _showSnackbar('Website data removed.');
        _fetchIndexedWebsites();
      } catch (e) {
        _showSnackbar('Delete failed: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.hub_outlined, color: AppColors.primary, size: 22),
            ),
            const SizedBox(width: 10),
            const Text(
              'WebRAG',
              style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: -0.5),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: const Color(0xFF10B981).withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Text(
                'MINING SYSTEM',
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Color(0xFF10B981)),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Web Analytics',
            icon: const Icon(Icons.insights_outlined),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const WebAnalyticsScreen()),
              );
            },
          ),
          IconButton(
            tooltip: 'Refresh websites',
            icon: const Icon(Icons.refresh),
            onPressed: _fetchIndexedWebsites,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _fetchIndexedWebsites,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 800),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _buildCrawlerInputCard(isDark),
                  const SizedBox(height: 16),
                  if (_isCrawling || _crawlProgress > 0) ...[
                    _buildProgressCard(isDark),
                    const SizedBox(height: 16),
                  ],
                  if (_errorMessage != null) ...[
                    _buildErrorCard(),
                    const SizedBox(height: 16),
                  ],
                  _buildQuickActionBar(),
                  const SizedBox(height: 20),
                  _buildIndexedWebsitesSection(isDark),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCrawlerInputCard(bool isDark) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        side: BorderSide(color: Theme.of(context).dividerColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.language, color: AppColors.primary, size: 24),
                const SizedBox(width: 8),
                Text(
                  'Crawl & Mine Website',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'Enter any public website URL to crawl, preprocess text, generate embeddings, and build an isolated RAG knowledge base.',
              style: TextStyle(fontSize: 12.5, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _urlController,
              enabled: !_isCrawling,
              decoration: InputDecoration(
                prefixIcon: const Icon(Icons.link, size: 20),
                hintText: 'https://example.com',
                labelText: 'Target Website URL',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: () => _urlController.clear(),
                ),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
              ),
            ),
            const SizedBox(height: 14),
            Column(
              children: [
                DropdownButtonFormField<int>(
                  value: _maxPages,
                  isExpanded: true,
                  decoration: InputDecoration(
                    labelText: 'Max Pages',
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
                  ),
                  items: const [
                    DropdownMenuItem(value: 5, child: Text('5 pages — Quick')),
                    DropdownMenuItem(value: 15, child: Text('15 pages')),
                    DropdownMenuItem(value: 30, child: Text('30 pages — Standard')),
                    DropdownMenuItem(value: 50, child: Text('50 pages — Deep')),
                  ],
                  onChanged: _isCrawling ? null : (val) => setState(() => _maxPages = val ?? 30),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<int>(
                  value: _maxDepth,
                  isExpanded: true,
                  decoration: InputDecoration(
                    labelText: 'Crawl Depth',
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
                  ),
                  items: const [
                    DropdownMenuItem(value: 1, child: Text('Depth 1 — Single level')),
                    DropdownMenuItem(value: 2, child: Text('Depth 2 — Standard')),
                    DropdownMenuItem(value: 3, child: Text('Depth 3 — Deep crawl')),
                  ],
                  onChanged: _isCrawling ? null : (val) => setState(() => _maxDepth = val ?? 2),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 46,
              child: FilledButton.icon(
                icon: _isCrawling
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.travel_explore),
                label: Text(
                  _isCrawling ? 'Crawling in Progress...' : 'Start Crawling & Mining',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                onPressed: _isCrawling ? null : _startCrawling,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressCard(bool isDark) {
    return Card(
      elevation: 0,
      color: AppColors.primary.withOpacity(0.04),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
        side: BorderSide(color: AppColors.primary.withOpacity(0.2)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    const Icon(Icons.radar, color: AppColors.primary, size: 20),
                    const SizedBox(width: 8),
                    Text(
                      'Live Crawl Status: $_crawlStatusText',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary),
                    ),
                  ],
                ),
                Text(
                  '$_crawlProgress%',
                  style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: _crawlProgress / 100.0,
                minHeight: 8,
                backgroundColor: AppColors.primary.withOpacity(0.12),
                valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
              ),
            ),
            if (_currentCrawlingUrl.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Target: $_currentCrawlingUrl',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard() {
    final isConnectionError = (_errorMessage ?? '').toLowerCase().contains('socket') ||
        (_errorMessage ?? '').toLowerCase().contains('cannot reach') ||
        (_errorMessage ?? '').toLowerCase().contains('connection refused');

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: const Color(0xFFEF4444).withOpacity(0.08),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: const Color(0xFFEF4444).withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.error_outline, color: Color(0xFFEF4444), size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _errorMessage ?? 'An error occurred during crawling.',
                  style: const TextStyle(color: Color(0xFFEF4444), fontSize: 12.5),
                ),
              ),
            ],
          ),
          if (isConnectionError) ...[
            const SizedBox(height: 8),
            const Text(
              '💡 Run the backend with:\n'
              '   uvicorn app.main:app --host 0.0.0.0 --port 8000\n'
              '   Then relaunch Flutter with your laptop\'s LAN IP:\n'
              '   flutter run --dart-define=API_BASE_URL=http://<YOUR-IP>:8000',
              style: TextStyle(fontSize: 11, color: Color(0xFFB45309)),
            ),
          ],
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Retry'),
              onPressed: () {
                setState(() => _errorMessage = null);
                _fetchIndexedWebsites();
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickActionBar() {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            icon: const Icon(Icons.chat_bubble_outline, size: 18),
            label: const Text('Open Web Chat'),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const WebChatScreen()),
              );
            },
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton.icon(
            icon: const Icon(Icons.bar_chart, size: 18),
            label: const Text('View Analytics'),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const WebAnalyticsScreen()),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildIndexedWebsitesSection(bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Indexed Websites (${_indexedWebsites.length})',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
            if (_loadingWebsites)
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
        const SizedBox(height: 12),
        if (_indexedWebsites.isEmpty && !_loadingWebsites)
          Container(
            padding: const EdgeInsets.all(AppSpacing.xl),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E293B) : const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: Theme.of(context).dividerColor),
            ),
            child: Column(
              children: [
                Icon(Icons.public_off_outlined, size: 48, color: Colors.grey.shade400),
                const SizedBox(height: 10),
                const Text(
                  'No websites indexed yet',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Enter a website URL above and click "Start Crawling & Mining".',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ],
            ),
          )
        else
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _indexedWebsites.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (context, idx) {
              final site = _indexedWebsites[idx];
              final domain = site['domain'] as String? ?? 'unknown';
              final websiteId = site['websiteId'] as String? ?? '';
              final totalPages = site['totalPages'] ?? 0;
              final totalChunks = site['totalChunks'] ?? 0;
              final totalWords = site['totalWords'] ?? 0;

              return Card(
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  side: BorderSide(color: Theme.of(context).dividerColor),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: AppColors.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(Icons.language, color: AppColors.primary, size: 20),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  domain,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14.5),
                                ),
                                Text(
                                  'ID: $websiteId',
                                  style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline, size: 20, color: Colors.red),
                            tooltip: 'Delete index',
                            onPressed: () => _deleteWebsite(websiteId, domain),
                          ),
                        ],
                      ),
                      const Divider(height: 20),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _buildStatBadge(Icons.article_outlined, '$totalPages', 'Pages'),
                          _buildStatBadge(Icons.grid_view_outlined, '$totalChunks', 'Chunks'),
                          _buildStatBadge(Icons.text_fields_outlined, '$totalWords', 'Words'),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              icon: const Icon(Icons.dashboard_outlined, size: 16),
                              label: const Text('Dashboard'),
                              onPressed: () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => WebsiteDashboardScreen(websiteId: websiteId, domain: domain),
                                  ),
                                );
                              },
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: FilledButton.icon(
                              icon: const Icon(Icons.chat_bubble_outline, size: 16),
                              label: const Text('Ask Q&A'),
                              onPressed: () {
                                Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => WebChatScreen(initialWebsiteId: websiteId),
                                  ),
                                );
                              },
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
      ],
    );
  }

  Widget _buildStatBadge(IconData icon, String val, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: AppColors.textSecondary),
        const SizedBox(width: 5),
        Text(val, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
        const SizedBox(width: 3),
        Text(label, style: const TextStyle(fontSize: 11.5, color: AppColors.textSecondary)),
      ],
    );
  }
}
