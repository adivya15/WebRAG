import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/orchestrator_service.dart';
import '../theme/app_theme.dart';
import 'web_chat_screen.dart';
import 'web_analytics_screen.dart';

/// Website Dashboard Screen: Detailed inspection of crawled pages, chunks, content volume, and timestamps.
class WebsiteDashboardScreen extends StatefulWidget {
  final String websiteId;
  final String domain;

  const WebsiteDashboardScreen({
    super.key,
    required this.websiteId,
    required this.domain,
  });

  @override
  State<WebsiteDashboardScreen> createState() => _WebsiteDashboardScreenState();
}

class _WebsiteDashboardScreenState extends State<WebsiteDashboardScreen> {
  final OrchestratorService _orchestrator = OrchestratorService();
  bool _loading = true;
  List<Map<String, dynamic>> _pages = [];
  Map<String, dynamic>? _stats;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _fetchDetails();
  }

  Future<void> _fetchDetails() async {
    setState(() => _loading = true);
    try {
      final pagesFuture = _orchestrator.listIndexedPages(widget.websiteId);
      final statsFuture = _orchestrator.getWebStats(websiteId: widget.websiteId);

      final results = await Future.wait([pagesFuture, statsFuture]);
      if (mounted) {
        setState(() {
          _pages = results[0] as List<Map<String, dynamic>>;
          _stats = results[1] as Map<String, dynamic>;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _copyToClipboard(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('URL copied to clipboard'), behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final totalPages = _stats?['totalPages'] ?? _pages.length;
    final totalChunks = _stats?['totalChunks'] ?? 0;
    final totalWords = _stats?['totalWords'] ?? 0;
    final avgWords = _stats?['averageWordsPerPage'] ?? 0;

    final filteredPages = _pages.where((p) {
      final title = (p['title'] as String? ?? '').toLowerCase();
      final url = (p['url'] as String? ?? '').toLowerCase();
      final q = _searchQuery.toLowerCase();
      return title.contains(q) || url.contains(q);
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.domain),
        actions: [
          IconButton(
            icon: const Icon(Icons.bar_chart),
            tooltip: 'Domain Analytics',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => WebAnalyticsScreen(filterWebsiteId: widget.websiteId),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.chat_bubble_outline),
            tooltip: 'Ask Website',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => WebChatScreen(initialWebsiteId: widget.websiteId),
                ),
              );
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetchDetails,
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 800),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _buildHeaderCard(isDark),
                        const SizedBox(height: 16),
                        _buildMetricsRow(totalPages, totalChunks, totalWords, avgWords),
                        const SizedBox(height: 20),
                        _buildPagesListSection(filteredPages, isDark),
                      ],
                    ),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _buildHeaderCard(bool isDark) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.06),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.primary.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.public, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.domain,
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 17),
                    ),
                    Text(
                      'Website ID: ${widget.websiteId}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF10B981).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.check_circle, size: 14, color: Color(0xFF10B981)),
                    SizedBox(width: 4),
                    Text(
                      'INDEXED',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF10B981)),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.chat_bubble_outline, size: 16),
                  label: const Text('Start Question Answering'),
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => WebChatScreen(initialWebsiteId: widget.websiteId),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricsRow(dynamic pages, dynamic chunks, dynamic words, dynamic avgWords) {
    return Row(
      children: [
        Expanded(child: _buildMetricTile('Pages Crawled', '$pages', Icons.pages)),
        const SizedBox(width: 8),
        Expanded(child: _buildMetricTile('Text Chunks', '$chunks', Icons.grid_view)),
        const SizedBox(width: 8),
        Expanded(child: _buildMetricTile('Words Extracted', '$words', Icons.text_snippet)),
      ],
    );
  }

  Widget _buildMetricTile(String title, String value, IconData icon) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: AppColors.primary),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
          ),
          Text(
            title,
            style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildPagesListSection(List<Map<String, dynamic>> pages, bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Indexed Web Pages (${pages.length})',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
          ],
        ),
        const SizedBox(height: 10),
        TextField(
          decoration: InputDecoration(
            hintText: 'Filter pages by title or URL...',
            prefixIcon: const Icon(Icons.search, size: 20),
            contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
          ),
          onChanged: (val) => setState(() => _searchQuery = val),
        ),
        const SizedBox(height: 14),
        if (pages.isEmpty)
          Container(
            padding: const EdgeInsets.all(AppSpacing.xl),
            alignment: Alignment.center,
            child: const Text('No matching pages found.'),
          )
        else
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: pages.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, idx) {
              final page = pages[idx];
              final title = page['title'] as String? ?? 'Untitled';
              final url = page['url'] as String? ?? '';
              final wordCount = page['wordCount'] ?? 0;
              final chunkCount = page['chunkCount'] ?? 0;
              final language = page['language'] as String? ?? 'English';

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
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  title,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                ),
                                const SizedBox(height: 3),
                                InkWell(
                                  onTap: () => _copyToClipboard(url),
                                  child: Text(
                                    url,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: AppColors.primary,
                                      decoration: TextDecoration.underline,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.copy, size: 16),
                            tooltip: 'Copy URL',
                            onPressed: () => _copyToClipboard(url),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.blue.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              language,
                              style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Colors.blue),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            '$wordCount words',
                            style: const TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            '• $chunkCount vector chunks',
                            style: const TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
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
}
