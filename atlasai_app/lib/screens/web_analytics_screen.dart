import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/orchestrator_service.dart';
import '../theme/app_theme.dart';

/// WebAnalyticsScreen: Web Data Mining analytics, statistical distributions, keyword frequencies, and latency metrics.
class WebAnalyticsScreen extends StatefulWidget {
  final String? filterWebsiteId;

  const WebAnalyticsScreen({super.key, this.filterWebsiteId});

  @override
  State<WebAnalyticsScreen> createState() => _WebAnalyticsScreenState();
}

class _WebAnalyticsScreenState extends State<WebAnalyticsScreen> {
  final OrchestratorService _orchestrator = OrchestratorService();
  bool _loading = true;
  Map<String, dynamic>? _stats;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchStats();
  }

  Future<void> _fetchStats() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await _orchestrator.getWebStats(websiteId: widget.filterWebsiteId);
      if (mounted) {
        setState(() {
          _stats = res;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceAll('Exception:', '').trim();
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Web Mining Analytics'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchStats,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.wifi_off_rounded, size: 48, color: Colors.red),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13)),
                        const SizedBox(height: 12),
                        if (_error!.toLowerCase().contains('socket') ||
                            _error!.toLowerCase().contains('cannot reach') ||
                            _error!.toLowerCase().contains('refused'))
                          Container(
                            padding: const EdgeInsets.all(12),
                            margin: const EdgeInsets.only(bottom: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFEF3C7),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Text(
                              '💡 Start backend: uvicorn app.main:app --host 0.0.0.0 --port 8000\n'
                              'Run Flutter: flutter run --dart-define=API_BASE_URL=http://<LAPTOP-IP>:8000',
                              style: TextStyle(fontSize: 11.5, color: Color(0xFF92400E)),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          icon: const Icon(Icons.refresh),
                          label: const Text('Retry'),
                          onPressed: _fetchStats,
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchStats,
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 850),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _buildSummaryMetrics(isDark),
                            const SizedBox(height: 16),
                            _buildWordFrequenciesCard(isDark),
                            const SizedBox(height: 16),
                            _buildChartsCard(isDark),
                            const SizedBox(height: 16),
                            _buildContentDistributionCard(isDark),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
    );
  }

  Widget _buildSummaryMetrics(bool isDark) {
    final totalWebsites = _stats?['totalWebsites'] ?? 0;
    final totalPages = _stats?['totalPages'] ?? 0;
    final totalWords = _stats?['totalWords'] ?? 0;
    final totalChunks = _stats?['totalChunks'] ?? 0;
    final avgLatency = _stats?['averageRetrievalLatencyMs'] ?? 0;
    final queriesLogged = _stats?['totalQueriesLogged'] ?? 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Mining Summary',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 10),
        GridView.count(
          crossAxisCount: MediaQuery.of(context).size.width > 600 ? 3 : 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
          childAspectRatio: 1.8,
          children: [
            _buildStatCard('Websites Indexed', '$totalWebsites', Icons.language, Colors.blue),
            _buildStatCard('Pages Crawled', '$totalPages', Icons.article_outlined, Colors.indigo),
            _buildStatCard('Words Extracted', '$totalWords', Icons.text_snippet_outlined, Colors.teal),
            _buildStatCard('Vector Chunks', '$totalChunks', Icons.grid_view_outlined, Colors.deepPurple),
            _buildStatCard('Avg Latency', '${avgLatency.toStringAsFixed(1)} ms', Icons.timer_outlined, Colors.amber.shade800),
            _buildStatCard('Queries Logged', '$queriesLogged', Icons.query_stats_outlined, Colors.green),
          ],
        ),
      ],
    );
  }

  Widget _buildStatCard(String label, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }

  Widget _buildWordFrequenciesCard(bool isDark) {
    final topWords = List<Map<String, dynamic>>.from(_stats?['topWords'] ?? const []);

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        side: BorderSide(color: Theme.of(context).dividerColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics_outlined, color: AppColors.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  'Top Meaningful Keywords (TF Mining)',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'Extracted through NLP tokenization and stopword elimination from crawled webpage bodies.',
              style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 14),
            if (topWords.isEmpty)
              const Text('No word frequency data available.')
            else ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: topWords.take(12).map((item) {
                  final word = item['word'] ?? '';
                  final count = item['count'] ?? 0;
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppColors.primary.withOpacity(0.2)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          word,
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.primary),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                          decoration: BoxDecoration(
                            color: AppColors.primary,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            '$count',
                            style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.white),
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildChartsCard(bool isDark) {
    final wordChartBase64 = _stats?['wordFrequencyChartBase64'] as String? ?? '';
    final distChartBase64 = _stats?['contentDistributionChartBase64'] as String? ?? '';

    if (wordChartBase64.isEmpty && distChartBase64.isEmpty) {
      return const SizedBox.shrink();
    }

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        side: BorderSide(color: Theme.of(context).dividerColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.bar_chart, color: AppColors.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  'Matplotlib Visualizations',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'Generated dynamically on the backend from actual crawled web data.',
              style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 14),
            if (wordChartBase64.isNotEmpty) ...[
              _buildBase64Image(wordChartBase64),
              const SizedBox(height: 16),
            ],
            if (distChartBase64.isNotEmpty) ...[
              _buildBase64Image(distChartBase64),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBase64Image(String dataUrl) {
    try {
      final raw = dataUrl.replaceFirst(RegExp(r'data:image/[^;]+;base64,'), '');
      final bytes = base64Decode(raw);
      return ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: Image.memory(
          bytes,
          fit: BoxFit.contain,
          width: double.infinity,
        ),
      );
    } catch (_) {
      return const SizedBox.shrink();
    }
  }

  Widget _buildContentDistributionCard(bool isDark) {
    final dist = List<Map<String, dynamic>>.from(_stats?['contentDistribution'] ?? const []);

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        side: BorderSide(color: Theme.of(context).dividerColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.table_chart_outlined, color: AppColors.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  'Crawled Pages Content Distribution',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (dist.isEmpty)
              const Text('No page distribution data.')
            else
              ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: dist.take(10).length,
                separatorBuilder: (_, __) => const Divider(height: 14),
                itemBuilder: (context, idx) {
                  final item = dist[idx];
                  final title = item['title'] as String? ?? 'Untitled';
                  final wordCount = item['word_count'] ?? 0;
                  final chunkCount = item['chunk_count'] ?? 0;

                  return Row(
                    children: [
                      Expanded(
                        child: Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        '$wordCount words',
                        style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '($chunkCount chunks)',
                        style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                      ),
                    ],
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}
