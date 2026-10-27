import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import '../services/orchestrator_service.dart';
import '../theme/app_theme.dart';
import '../widgets/confidence_badge.dart';

class WebChatMessage {
  final String text;
  final bool isUser;
  final double? confidence;
  final List<Map<String, dynamic>> citations;
  final double? retrievalLatencyMs;
  final double? totalLatencyMs;
  final String? reasoning;
  final bool isError;

  WebChatMessage({
    required this.text,
    required this.isUser,
    this.confidence,
    this.citations = const [],
    this.retrievalLatencyMs,
    this.totalLatencyMs,
    this.reasoning,
    this.isError = false,
  });
}

/// WebChatScreen: Question Answering interface strictly grounded in crawled website content.
class WebChatScreen extends StatefulWidget {
  final String? initialWebsiteId;

  const WebChatScreen({super.key, this.initialWebsiteId});

  @override
  State<WebChatScreen> createState() => _WebChatScreenState();
}

class _WebChatScreenState extends State<WebChatScreen> {
  final OrchestratorService _orchestrator = OrchestratorService();
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final stt.SpeechToText _speech = stt.SpeechToText();

  List<Map<String, dynamic>> _websites = [];
  String? _selectedWebsiteId;
  String _selectedDomain = '';
  bool _loadingWebsites = true;

  final List<WebChatMessage> _messages = [];
  bool _isSending = false;
  bool _speechAvailable = false;
  bool _isListening = false;

  @override
  void initState() {
    super.initState();
    _initSpeech();
    _loadWebsites();
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _initSpeech() async {
    _speechAvailable = await _speech.initialize(
      onStatus: (status) {
        if (status == 'done' || status == 'notListening') {
          if (mounted) setState(() => _isListening = false);
        }
      },
      onError: (_) {
        if (mounted) setState(() => _isListening = false);
      },
    );
  }

  void _toggleListening() async {
    if (!_speechAvailable) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Speech recognition not available on this device')),
      );
      return;
    }

    if (_isListening) {
      await _speech.stop();
      setState(() => _isListening = false);
    } else {
      setState(() => _isListening = true);
      await _speech.listen(
        onResult: (result) {
          setState(() {
            _textController.text = result.recognizedWords;
          });
        },
      );
    }
  }

  Future<void> _loadWebsites() async {
    setState(() => _loadingWebsites = true);
    try {
      final sites = await _orchestrator.listIndexedWebsites();
      if (mounted) {
        setState(() {
          _websites = sites;
          _loadingWebsites = false;
          if (_websites.isNotEmpty) {
            if (widget.initialWebsiteId != null &&
                _websites.any((s) => s['websiteId'] == widget.initialWebsiteId)) {
              _selectedWebsiteId = widget.initialWebsiteId;
              final found = _websites.firstWhere((s) => s['websiteId'] == widget.initialWebsiteId);
              _selectedDomain = found['domain'] ?? '';
            } else {
              _selectedWebsiteId = _websites.first['websiteId'];
              _selectedDomain = _websites.first['domain'] ?? '';
            }
          }
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingWebsites = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send([String? overrideText]) async {
    final text = (overrideText ?? _textController.text).trim();
    if (text.isEmpty || _isSending) return;

    if (_selectedWebsiteId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select an indexed website first')),
      );
      return;
    }

    _textController.clear();
    setState(() {
      _messages.add(WebChatMessage(text: text, isUser: true));
      _isSending = true;
    });
    _scrollToBottom();

    try {
      final res = await _orchestrator.askWeb(_selectedWebsiteId!, text);

      final answer = res['answer'] as String? ?? 'No response received.';
      final confidence = (res['confidence'] as num?)?.toDouble() ?? 0.0;
      final citations = List<Map<String, dynamic>>.from(res['citations'] ?? const []);
      final retLatency = (res['retrievalLatencyMs'] as num?)?.toDouble();
      final totalLatency = (res['totalLatencyMs'] as num?)?.toDouble();
      final reasoning = res['reasoning'] as String?;

      setState(() {
        _messages.add(WebChatMessage(
          text: answer,
          isUser: false,
          confidence: confidence,
          citations: citations,
          retrievalLatencyMs: retLatency,
          totalLatencyMs: totalLatency,
          reasoning: reasoning,
        ));
        _isSending = false;
      });
      _scrollToBottom();
    } catch (e) {
      setState(() {
        _messages.add(WebChatMessage(
          text: 'Error querying website: $e',
          isUser: false,
          isError: true,
        ));
        _isSending = false;
      });
      _scrollToBottom();
    }
  }

  void _clearChat() {
    setState(() => _messages.clear());
  }

  void _showCitationModal(BuildContext context, Map<String, dynamic> citation) {
    final url = citation['url'] as String? ?? '';
    final title = citation['title'] as String? ?? 'Source Webpage';
    final snippet = citation['snippet'] as String? ?? '';
    final idx = citation['index'] ?? 1;

    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      'Source Citation #$idx',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary, fontSize: 12),
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.copy, size: 18),
                    tooltip: 'Copy URL',
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: url));
                      Navigator.pop(ctx);
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('URL copied to clipboard')),
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: 4),
              SelectableText(
                url,
                style: const TextStyle(fontSize: 12, color: AppColors.primary, decoration: TextDecoration.underline),
              ),
              const SizedBox(height: 14),
              const Text(
                'Retrieved Excerpt Grounding:',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).cardColor,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Theme.of(context).dividerColor),
                ),
                child: Text(
                  snippet,
                  style: const TextStyle(fontSize: 13, height: 1.4),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('WebRAG Chat', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            if (_selectedDomain.isNotEmpty)
              Text(
                _selectedDomain,
                style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
              ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_sweep_outlined),
            tooltip: 'Clear conversation',
            onPressed: _messages.isEmpty ? null : _clearChat,
          ),
        ],
      ),
      body: Column(
        children: [
          _buildWebsiteSelectorHeader(isDark),
          Expanded(
            child: _messages.isEmpty ? _buildEmptyState(isDark) : _buildMessageList(),
          ),
          if (_isSending)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
              color: AppColors.primary.withOpacity(0.04),
              child: Row(
                children: [
                  const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Searching ChromaDB & synthesizing answer with Groq...',
                      style: const TextStyle(fontSize: 12, color: AppColors.primary),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
          _buildInputBar(isDark),
        ],
      ),
    );
  }

  Widget _buildWebsiteSelectorHeader(bool isDark) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        border: Border(bottom: BorderSide(color: Theme.of(context).dividerColor, width: 0.8)),
      ),
      child: Row(
        children: [
          const Icon(Icons.language, size: 18, color: AppColors.primary),
          const SizedBox(width: 8),
          const Text('Active Site: ', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold)),
          const SizedBox(width: 6),
          Expanded(
            child: _loadingWebsites
                ? const SizedBox(
                    height: 16,
                    width: 16,
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : _websites.isEmpty
                    ? const Text('No websites crawled yet', style: TextStyle(fontSize: 12, color: Colors.red))
                    : DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          isExpanded: true,
                          value: _selectedWebsiteId,
                          hint: const Text('Select a crawled website'),
                          items: _websites.map((s) {
                            final siteId = s['websiteId'] as String;
                            final domain = s['domain'] as String? ?? 'unknown';
                            return DropdownMenuItem<String>(
                              value: siteId,
                              child: Text(
                                domain,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                              ),
                            );
                          }).toList(),
                          onChanged: (val) {
                            if (val != null) {
                              setState(() {
                                _selectedWebsiteId = val;
                                final item = _websites.firstWhere((s) => s['websiteId'] == val);
                                _selectedDomain = item['domain'] ?? '';
                              });
                            }
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(bool isDark) {
    final samplePrompts = [
      'What are the primary topics covered on this website?',
      'Summarize the core objectives and findings.',
      'What specific technologies, algorithms, or policies are discussed?',
      'Who are the key people or organizations mentioned?',
    ];

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 550),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.1),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.search_rounded, size: 36, color: AppColors.primary),
              ),
              const SizedBox(height: 14),
              Text(
                'Ask about ${_selectedDomain.isEmpty ? "the Website" : _selectedDomain}',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              const Text(
                'Answers are strictly grounded in crawled page excerpts with verified source URL citations.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 20),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text('Suggested Questions:', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
              ),
              const SizedBox(height: 8),
              ...samplePrompts.map(
                (p) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: InkWell(
                    onTap: () => _send(p),
                    borderRadius: BorderRadius.circular(AppRadius.md),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: Theme.of(context).cardColor,
                        borderRadius: BorderRadius.circular(AppRadius.md),
                        border: Border.all(color: Theme.of(context).dividerColor),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.chat_outlined, size: 16, color: AppColors.primary),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(p, style: const TextStyle(fontSize: 12.5)),
                          ),
                          const Icon(Icons.arrow_forward_ios, size: 12, color: Colors.grey),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMessageList() {
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(AppSpacing.md),
      itemCount: _messages.length,
      itemBuilder: (context, idx) {
        final msg = _messages[idx];
        return _buildMessageBubble(msg);
      },
    );
  }

  Widget _buildMessageBubble(WebChatMessage msg) {
    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12, left: 40),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.primary,
            borderRadius: BorderRadius.circular(16).copyWith(bottomRight: const Radius.circular(2)),
          ),
          child: Text(
            msg.text,
            style: const TextStyle(color: Colors.white, fontSize: 14),
          ),
        ),
      );
    }

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16, right: 30),
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(16).copyWith(bottomLeft: const Radius.circular(2)),
          border: Border.all(color: Theme.of(context).dividerColor),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.auto_awesome, size: 16, color: AppColors.primary),
                const SizedBox(width: 6),
                const Text(
                  'WebRAG',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5, color: AppColors.primary),
                ),
                const Spacer(),
                if (msg.confidence != null && msg.confidence! > 0)
                  ConfidenceBadge(confidence: msg.confidence!),
              ],
            ),
            const SizedBox(height: 10),
            MarkdownBody(
              data: msg.text,
              styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
                p: const TextStyle(fontSize: 13.5, height: 1.5),
              ),
            ),
            if (msg.citations.isNotEmpty) ...[
              const Divider(height: 24),
              const Text(
                'Source Citations:',
                style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: msg.citations.map((c) {
                  final idx = c['index'] ?? 1;
                  final title = c['title'] as String? ?? 'Page';
                  final display = title.length > 20 ? '${title.substring(0, 20)}…' : title;

                  return InkWell(
                    onTap: () => _showCitationModal(context, c),
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.08),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.primary.withOpacity(0.25)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(3),
                            decoration: const BoxDecoration(
                              color: AppColors.primary,
                              shape: BoxShape.circle,
                            ),
                            child: Text(
                              '$idx',
                              style: const TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            display,
                            style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: AppColors.primary),
                          ),
                          const SizedBox(width: 4),
                          const Icon(Icons.open_in_new, size: 11, color: AppColors.primary),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
            if (msg.retrievalLatencyMs != null) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  const Icon(Icons.timer_outlined, size: 12, color: AppColors.textSecondary),
                  const SizedBox(width: 4),
                  Text(
                    'Retrieval: ${msg.retrievalLatencyMs!.toStringAsFixed(0)}ms | Total: ${msg.totalLatencyMs?.toStringAsFixed(0) ?? "?"}ms',
                    style: const TextStyle(fontSize: 10.5, color: AppColors.textSecondary),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar(bool isDark) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        border: Border(top: BorderSide(color: Theme.of(context).dividerColor, width: 0.8)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            IconButton(
              icon: Icon(
                _isListening ? Icons.mic : Icons.mic_none,
                color: _isListening ? Colors.red : AppColors.primary,
              ),
              onPressed: _toggleListening,
            ),
            Expanded(
              child: TextField(
                controller: _textController,
                minLines: 1,
                maxLines: 4,
                decoration: InputDecoration(
                  hintText: 'Ask a question about ${_selectedDomain.isEmpty ? "website" : _selectedDomain}...',
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                ),
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              icon: const Icon(Icons.send_rounded, size: 18),
              onPressed: _isSending ? null : () => _send(),
            ),
          ],
        ),
      ),
    );
  }
}
