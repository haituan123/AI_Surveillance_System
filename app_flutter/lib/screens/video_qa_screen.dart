import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart' hide Text;
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../core/app_localization.dart';
import '../core/api_config.dart';
import '../models/qa_models.dart';
import '../services/qa_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/localized_text.dart';

class VideoQAScreen extends StatefulWidget {
  const VideoQAScreen({super.key});

  @override
  State<VideoQAScreen> createState() => _VideoQAScreenState();
}

class _VideoQAScreenState extends State<VideoQAScreen> {
  final QAService _qaService = QAService();
  final TextEditingController _questionController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  List<QAConversationModel> _conversations = [];
  QAConversationModel? _selectedConversation;
  List<QAMessageModel> _messages = [];
  List<QAUploadedVideoModel> _uploadedVideos = [];

  bool _loadingConversations = false;
  bool _loadingMessages = false;
  bool _sending = false;
  bool _uploadingVideo = false;
  bool _showHistory = false;
  bool _showVideoRail = true;
  String? _errorMessage;
  int _videoPage = 0;
  Timer? _pollTimer;
  final Map<String, GlobalKey<_QAVideoPlayerCardState>> _videoPlayerKeys = {};

  // Selected Scope Filter: 'all' or one uploaded videoId.
  String _selectedScope = 'all';

  @override
  void initState() {
    super.initState();
    _loadConversations();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _questionController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _checkAndStartPolling() {
    _pollTimer?.cancel();
    final hasProcessing = _uploadedVideos.any((v) => v.isProcessing);
    if (hasProcessing) {
      _pollTimer = Timer.periodic(
        const Duration(seconds: 3),
        (_) => _pollVideoStatuses(),
      );
    }
  }

  Future<void> _pollVideoStatuses() async {
    if (_selectedConversation == null) return;
    try {
      final videos = await _qaService.listUploadedVideos(
        _selectedConversation!.id,
      );
      if (!mounted) return;
      setState(() {
        _uploadedVideos = videos;
        final lastPage = videos.isEmpty ? 0 : (videos.length - 1) ~/ 4;
        if (_videoPage > lastPage) _videoPage = lastPage;
      });
      if (!videos.any((v) => v.isProcessing)) {
        _pollTimer?.cancel();
      }
    } catch (_) {}
  }

  Future<void> _loadConversations() async {
    setState(() => _loadingConversations = true);
    try {
      final convs = await _qaService.listConversations();
      setState(() {
        _conversations = convs;
        _loadingConversations = false;
        if (_selectedConversation == null && convs.isNotEmpty) {
          _selectConversation(convs.first);
        }
      });
    } catch (e) {
      setState(() {
        _errorMessage = 'Không thể tải lịch sử hỏi đáp: $e';
        _loadingConversations = false;
      });
    }
  }

  Future<void> _selectConversation(QAConversationModel conv) async {
    setState(() {
      _selectedConversation = conv;
      _loadingMessages = true;
      _errorMessage = null;
    });

    try {
      final detail = await _qaService.getConversationDetail(conv.id);
      setState(() {
        _messages = detail.messages;
        _uploadedVideos = detail.uploadedVideos;
        _videoPage = 0;
        if (!_uploadedVideos.any((video) => video.videoId == _selectedScope)) {
          _selectedScope = 'all';
        }
        _loadingMessages = false;
      });
      _checkAndStartPolling();
      _scrollToBottom();
    } catch (e) {
      setState(() {
        _errorMessage = 'Không thể tải tin nhắn: $e';
        _loadingMessages = false;
      });
    }
  }

  Future<void> _createNewConversation() async {
    try {
      final newConv = await _qaService.createConversation(
        title:
            'Hỏi đáp mới (${DateTime.now().hour}:${DateTime.now().minute.toString().padLeft(2, '0')})',
      );
      setState(() {
        _conversations.insert(0, newConv);
        _selectedConversation = newConv;
        _messages = [];
        _uploadedVideos = [];
        _selectedScope = 'all';
        _videoPage = 0;
      });
      _pollTimer?.cancel();
    } catch (e) {
      _showSnackBar('Lỗi tạo phiên hỏi đáp: $e');
    }
  }

  Future<void> _deleteConversation(int id) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Xác nhận xóa phiên hỏi đáp'),
        content: Text(
          'Xóa phiên hỏi đáp này sẽ đồng thời xóa toàn bộ tin nhắn, video đã tải lên và dữ liệu AI đã phân tích của phiên.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text('Xóa'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _qaService.deleteConversation(id);
      setState(() {
        _conversations.removeWhere((c) => c.id == id);
        if (_selectedConversation?.id == id) {
          _selectedConversation = _conversations.isNotEmpty
              ? _conversations.first
              : null;
          if (_selectedConversation != null) {
            _selectConversation(_selectedConversation!);
          } else {
            _messages = [];
            _uploadedVideos = [];
            _selectedScope = 'all';
          }
        }
      });
      _showSnackBar('Đã xóa phiên hỏi đáp và dữ liệu video liên quan');
    } catch (e) {
      _showSnackBar('Không thể xóa: $e');
    }
  }

  Future<void> _pickAndUploadVideo() async {
    if (_uploadingVideo) return;

    // Nếu chưa có conversation, tạo mới trước
    if (_selectedConversation == null) {
      await _createNewConversation();
      if (_selectedConversation == null) return;
    }

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['mp4', 'avi', 'mov', 'mkv', 'webm'],
        withReadStream: true,
      );

      final file = result?.files.single;
      if (file == null) return;
      if (file.readStream == null && file.bytes == null && file.path == null) {
        setState(() {
          _errorMessage = 'Dữ liệu video đã chọn không khả dụng.';
        });
        return;
      }

      setState(() {
        _uploadingVideo = true;
        _errorMessage = null;
      });

      final uploaded = await _qaService.uploadVideo(
        conversationId: _selectedConversation!.id,
        path: file.path,
        stream: file.readStream,
        length: file.size,
        bytes: file.bytes,
        filename: file.name,
      );

      setState(() {
        _uploadedVideos.insert(0, uploaded);
        _selectedScope = uploaded.videoId;
        _videoPage = 0;
        _showVideoRail = true;
        _uploadingVideo = false;
      });

      _showSnackBar(
        'Đã tải video lên. AI đang bắt đầu xử lý và lập chỉ mục frames...',
      );
      _checkAndStartPolling();
    } catch (e) {
      setState(() {
        _uploadingVideo = false;
        _errorMessage = 'Lỗi tải video lên: $e';
      });
      _showSnackBar('Lỗi tải video lên: $e');
    }
  }

  Future<void> _deleteUploadedVideo(QAUploadedVideoModel video) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Xác nhận xóa video'),
        content: Text(
          'Bạn có chắc muốn xóa video "${video.filename}"?\nToàn bộ dữ liệu khung hình và AI nhận dạng liên quan đến video này sẽ được xóa khỏi cơ sở dữ liệu.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text('Xóa'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _qaService.deleteUploadedVideo(video.videoId);
      setState(() {
        _uploadedVideos.removeWhere((v) => v.videoId == video.videoId);
        if (_selectedScope == video.videoId) {
          _selectedScope = 'all';
        }
        final lastPage = _uploadedVideos.isEmpty
            ? 0
            : (_uploadedVideos.length - 1) ~/ 4;
        if (_videoPage > lastPage) _videoPage = lastPage;
      });
      _showSnackBar(
        'Đã xóa video "${video.filename}" và các dữ liệu liên quan',
      );
    } catch (e) {
      _showSnackBar('Lỗi xóa video: $e');
    }
  }

  Future<void> _retryUploadedVideo(QAUploadedVideoModel video) async {
    try {
      final updated = await _qaService.retryVideo(video.videoId);
      setState(() {
        final idx = _uploadedVideos.indexWhere(
          (v) => v.videoId == video.videoId,
        );
        if (idx != -1) {
          _uploadedVideos[idx] = updated;
        }
        _selectedScope = video.videoId;
      });
      _showSnackBar('Đang bắt đầu xử lý lại video "${video.filename}"...');
      _checkAndStartPolling();
    } catch (e) {
      _showSnackBar('Không thể thử lại: $e');
    }
  }

  Future<void> _handleSend([String? presetText]) async {
    final text = presetText ?? _questionController.text.trim();
    if (text.isEmpty || _sending) return;

    if (presetText == null) {
      _questionController.clear();
    }

    setState(() {
      _sending = true;
      _errorMessage = null;
    });

    try {
      final responseMessage = await _qaService.askQuestion(
        question: text,
        conversationId: _selectedConversation?.id,
        sessionOrVideoId: _selectedScope == 'all' ? null : _selectedScope,
        sessionOrVideoIds: _selectedScope == 'all'
            ? _uploadedVideos.map((video) => video.videoId).toList()
            : null,
      );

      setState(() {
        _messages.add(responseMessage);
        _sending = false;
      });
      _scrollToBottom();
      _loadConversations();
    } catch (e) {
      setState(() {
        _errorMessage = 'Lỗi truy vấn AI: $e';
        _sending = false;
      });
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

  void _showSnackBar(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 3)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final viewportWidth = MediaQuery.sizeOf(context).width;
    final isDesktop = viewportWidth >= AppBreakpoints.compact;
    final historySidebarWidth = (viewportWidth * 0.22)
        .clamp(280.0, 340.0)
        .toDouble();

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Row(
        children: [
          // Sidebar lịch sử (nếu là màn hình lớn)
          if (isDesktop && _showHistory)
            Container(
              key: const ValueKey('conversation-history-sidebar'),
              width: historySidebarWidth,
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(right: BorderSide(color: AppColors.border)),
              ),
              child: _buildConversationSidebar(),
            ),

          // Main Chat Area
          Expanded(
            child: Column(
              children: [
                _buildHeader(isDesktop),
                _buildScopeAndPromptsBar(),
                Divider(height: 1, color: AppColors.border),
                Expanded(
                  child:
                      MediaQuery.sizeOf(context).width >= AppBreakpoints.desktop
                      ? _buildWideChatWorkspace()
                      : Column(
                          children: [
                            _buildVideoWorkspace(),
                            Divider(height: 1, color: AppColors.border),
                            Expanded(child: _buildChatBody()),
                            _buildInputBar(),
                          ],
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(bool isDesktop) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          if (isDesktop) ...[
            IconButton(
              onPressed: () => setState(() => _showHistory = !_showHistory),
              icon: Icon(
                _showHistory ? Icons.menu_open_rounded : Icons.history_rounded,
              ),
              color: AppColors.textMuted,
              tooltip: context.tr('Lịch sử hỏi đáp'),
            ),
            const SizedBox(width: 4),
          ],
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppColors.tealSoft,
              borderRadius: BorderRadius.circular(AppRadii.sm),
            ),
            child: Icon(Icons.psychology, color: AppColors.teal, size: 24),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Hỏi đáp video giám sát',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppColors.text,
                  ),
                ),
                Text(
                  'Chọn video, đặt câu hỏi và kiểm tra bằng chứng theo thời gian',
                  style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                ),
              ],
            ),
          ),
          ElevatedButton.icon(
            onPressed: _createNewConversation,
            icon: Icon(Icons.add, size: 18),
            label: Text('Phiên mới'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.teal,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadii.sm),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScopeAndPromptsBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 10, 18, 8),
      color: AppColors.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_errorMessage != null)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: AppColors.danger.withAlpha(20),
                borderRadius: BorderRadius.circular(AppRadii.sm),
                border: Border.all(color: AppColors.danger.withAlpha(50)),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline, size: 18, color: AppColors.danger),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _errorMessage!,
                      style: TextStyle(fontSize: 12, color: AppColors.danger),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close, size: 16, color: AppColors.danger),
                    onPressed: () => setState(() => _errorMessage = null),
                  ),
                ],
              ),
            ),

          Row(
            children: [
              OutlinedButton.icon(
                onPressed: _uploadingVideo ? null : _pickAndUploadVideo,
                icon: _uploadingVideo
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add_rounded, size: 17),
                label: Text(_uploadingVideo ? 'Đang tải...' : 'Thêm video'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.teal,
                  side: BorderSide(color: AppColors.borderStrong),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 10,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadii.sm),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: PopupMenuButton<String>(
                  enabled: _uploadedVideos.isNotEmpty,
                  onSelected: (value) => setState(() {
                    _selectedScope = value;
                    if (value == 'all') _videoPage = 0;
                    if (value != 'all') _showVideoRail = true;
                  }),
                  itemBuilder: (context) => [
                    PopupMenuItem(
                      value: 'all',
                      child: Row(
                        children: [
                          const Icon(Icons.grid_view_rounded, size: 17),
                          const SizedBox(width: 10),
                          Text('Tất cả video (${_uploadedVideos.length})'),
                        ],
                      ),
                    ),
                    const PopupMenuDivider(),
                    for (final video in _uploadedVideos)
                      PopupMenuItem(
                        value: video.videoId,
                        child: Row(
                          children: [
                            Icon(
                              video.isCompleted
                                  ? Icons.check_circle
                                  : video.isFailed
                                  ? Icons.error
                                  : Icons.pending,
                              size: 16,
                              color: video.isCompleted
                                  ? AppColors.success
                                  : video.isFailed
                                  ? AppColors.danger
                                  : AppColors.warning,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                _videoDisplayName(video),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                  child: Container(
                    height: 40,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceSubtle,
                      borderRadius: BorderRadius.circular(AppRadii.sm),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _selectedScope == 'all'
                              ? Icons.grid_view_rounded
                              : Icons.play_circle_outline,
                          size: 17,
                          color: AppColors.teal,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _scopeLabel(),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        const Icon(Icons.expand_more, size: 18),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              IconButton(
                onPressed: _uploadedVideos.isEmpty ? null : _showVideoLibrary,
                icon: const Icon(Icons.video_library_outlined, size: 20),
                tooltip: context.tr('Quản lý video'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _scopeLabel() {
    if (_uploadedVideos.isEmpty) return 'Chưa có video';
    if (_selectedScope == 'all') {
      return 'Hỏi trên tất cả ${_uploadedVideos.length} video';
    }
    final video = _videoForId(_selectedScope);
    return video == null ? 'Chọn video' : _videoDisplayName(video);
  }

  String _videoDisplayName(QAUploadedVideoModel video) {
    final duplicates = _uploadedVideos
        .where((item) => item.filename == video.filename)
        .toList();
    if (duplicates.length <= 1) return video.filename;
    final position = duplicates.indexWhere(
      (item) => item.videoId == video.videoId,
    );
    return '${video.filename} (${position + 1})';
  }

  Future<void> _showVideoLibrary() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.video_library_outlined, size: 22),
            const SizedBox(width: 10),
            Text('Thư viện video (${_uploadedVideos.length})'),
          ],
        ),
        content: SizedBox(
          width: 520,
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: _uploadedVideos.length,
            separatorBuilder: (_, _) => Divider(color: AppColors.border),
            itemBuilder: (context, index) {
              final video = _uploadedVideos[index];
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  video.isCompleted
                      ? Icons.check_circle
                      : video.isFailed
                      ? Icons.error
                      : Icons.pending,
                  color: video.isCompleted
                      ? AppColors.success
                      : video.isFailed
                      ? AppColors.danger
                      : AppColors.warning,
                ),
                title: Text(
                  _videoDisplayName(video),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(
                  video.isCompleted
                      ? '${video.indexedFrames} khung hình đã phân tích'
                      : video.isFailed
                      ? 'Xử lý thất bại'
                      : 'Đang xử lý ${video.processedFrames}/${video.totalFrames}',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted),
                ),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (video.isFailed)
                      IconButton(
                        icon: const Icon(Icons.refresh, size: 19),
                        tooltip: context.tr('Thử lại'),
                        onPressed: () {
                          Navigator.pop(dialogContext);
                          _retryUploadedVideo(video);
                        },
                      ),
                    IconButton(
                      icon: Icon(
                        Icons.delete_outline,
                        size: 19,
                        color: AppColors.danger,
                      ),
                      tooltip: context.tr('Xóa video'),
                      onPressed: () {
                        Navigator.pop(dialogContext);
                        _deleteUploadedVideo(video);
                      },
                    ),
                  ],
                ),
                onTap: () {
                  Navigator.pop(dialogContext);
                  setState(() => _selectedScope = video.videoId);
                },
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text('Đóng'),
          ),
        ],
      ),
    );
  }

  GlobalKey<_QAVideoPlayerCardState> _videoKey(String videoId) {
    return _videoPlayerKeys.putIfAbsent(
      videoId,
      () => GlobalKey<_QAVideoPlayerCardState>(),
    );
  }

  QAUploadedVideoModel? _videoForId(String? videoId) {
    if (videoId == null) return null;
    for (final video in _uploadedVideos) {
      if (video.videoId == videoId) return video;
    }
    return null;
  }

  void _focusEvidence(QAEvidenceModel evidence) {
    final sourceId =
        evidence.sourceVideoId ??
        (_selectedScope == 'all' ? null : _selectedScope);
    final source = _videoForId(sourceId);
    if (source == null) {
      _showSnackBar('Không xác định được video nguồn của bằng chứng này.');
      return;
    }
    setState(() {
      _selectedScope = source.videoId;
      _showVideoRail = true;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _videoKey(source.videoId).currentState?.seekTo(
        Duration(milliseconds: (evidence.startTimestamp * 1000).round()),
      );
    });
  }

  Widget _buildVideoWorkspace() {
    if (_uploadedVideos.isEmpty) {
      return Container(
        height: 138,
        width: double.infinity,
        color: AppColors.surfaceSubtle,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.video_library_outlined,
                color: AppColors.textSubtle,
                size: 34,
              ),
              const SizedBox(height: 8),
              Text(
                'Tải video lên để xem và đặt câu hỏi',
                style: TextStyle(
                  color: AppColors.text,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _uploadingVideo ? null : _pickAndUploadVideo,
                icon: Icon(Icons.upload_file, size: 16),
                label: Text('Chọn video'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.teal,
                ),
              ),
            ],
          ),
        ),
      );
    }

    final selectedVideo = _videoForId(_selectedScope);
    final allMode = _selectedScope == 'all' || selectedVideo == null;
    final pageCount = (_uploadedVideos.length / 4).ceil();
    final currentPage = pageCount == 0
        ? 0
        : (_videoPage >= pageCount ? pageCount - 1 : _videoPage);
    final visibleVideos = allMode
        ? _uploadedVideos.skip(currentPage * 4).take(4).toList()
        : <QAUploadedVideoModel>[selectedVideo];

    return LayoutBuilder(
      builder: (context, constraints) {
        final useTwoColumns =
            allMode && visibleVideos.length > 1 && constraints.maxWidth >= 720;
        final useCarousel =
            allMode && visibleVideos.length > 1 && constraints.maxWidth < 720;
        final columns = useTwoColumns ? 2 : 1;
        final rows = (visibleVideos.length / columns).ceil();
        final tileHeight = useTwoColumns ? 190.0 : 290.0;
        final contentHeight = useCarousel
            ? 240.0
            : rows * tileHeight + (rows - 1) * 8;

        Widget playerCard(QAUploadedVideoModel video) {
          return _QAVideoPlayerCard(
            key: _videoKey(video.videoId),
            video: video,
            displayName: _videoDisplayName(video),
            contentUrl: _qaService.videoContentUrl(video.videoId),
            isQueryTarget: !allMode,
            onSelectForQuery: () {
              setState(() => _selectedScope = video.videoId);
            },
          );
        }

        return Container(
          color: AppColors.surfaceSubtle,
          padding: const EdgeInsets.fromLTRB(18, 10, 18, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    allMode
                        ? Icons.grid_view_rounded
                        : Icons.play_circle_outline,
                    color: AppColors.teal,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      allMode
                          ? '${_uploadedVideos.length} video trong phạm vi truy vấn'
                          : 'Video đang được chọn',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  if (allMode && pageCount > 1) ...[
                    IconButton(
                      visualDensity: VisualDensity.compact,
                      onPressed: currentPage == 0
                          ? null
                          : () => setState(() => _videoPage = currentPage - 1),
                      icon: const Icon(Icons.chevron_left, size: 20),
                    ),
                    Text(
                      '${currentPage * 4 + 1}–${currentPage * 4 + visibleVideos.length} / ${_uploadedVideos.length}',
                      style: TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    IconButton(
                      visualDensity: VisualDensity.compact,
                      onPressed: currentPage >= pageCount - 1
                          ? null
                          : () => setState(() => _videoPage = currentPage + 1),
                      icon: const Icon(Icons.chevron_right, size: 20),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                height: contentHeight,
                child: useCarousel
                    ? ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: visibleVideos.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 8),
                        itemBuilder: (context, index) => SizedBox(
                          width: constraints.maxWidth * 0.82,
                          child: playerCard(visibleVideos[index]),
                        ),
                      )
                    : GridView.builder(
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: visibleVideos.length,
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: columns,
                          mainAxisExtent: tileHeight,
                          crossAxisSpacing: 8,
                          mainAxisSpacing: 8,
                        ),
                        itemBuilder: (context, index) =>
                            playerCard(visibleVideos[index]),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildWideChatWorkspace() {
    return Row(
      children: [
        Expanded(
          child: Column(
            children: [
              Expanded(child: _buildChatBody()),
              _buildInputBar(),
            ],
          ),
        ),
        _buildVideoRail(),
      ],
    );
  }

  Widget _buildVideoRail() {
    const expandedWidth = 360.0;
    const collapsedWidth = 52.0;
    final selectedVideo = _videoForId(_selectedScope);
    final videos = <QAUploadedVideoModel>[
      ?selectedVideo,
      ..._uploadedVideos.where(
        (video) => video.videoId != selectedVideo?.videoId,
      ),
    ];

    return AnimatedSize(
      duration: const Duration(milliseconds: 240),
      curve: Curves.easeInOutCubic,
      alignment: Alignment.centerRight,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        key: const ValueKey('video-rail'),
        width: _showVideoRail ? expandedWidth : collapsedWidth,
        child: _showVideoRail
            ? DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.surfaceSubtle,
                  border: Border(left: BorderSide(color: AppColors.border)),
                ),
                child: Column(
                  children: [
                    Container(
                      height: 52,
                      padding: const EdgeInsets.only(left: 14, right: 4),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        border: Border(
                          bottom: BorderSide(color: AppColors.border),
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            Icons.video_library_outlined,
                            color: AppColors.teal,
                            size: 20,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Video (${_uploadedVideos.length})',
                              style: TextStyle(
                                color: AppColors.text,
                                fontSize: 13,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          IconButton(
                            key: const ValueKey('collapse-video-rail'),
                            onPressed: () =>
                                setState(() => _showVideoRail = false),
                            tooltip: context.tr('Collapse video panel'),
                            icon: const Icon(Icons.keyboard_double_arrow_right),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: videos.isEmpty
                          ? _buildEmptyVideoRail()
                          : ListView.separated(
                              padding: const EdgeInsets.all(10),
                              itemCount: videos.length,
                              separatorBuilder: (_, _) =>
                                  const SizedBox(height: 10),
                              itemBuilder: (context, index) {
                                final video = videos[index];
                                return SizedBox(
                                  height: 200,
                                  child: _QAVideoPlayerCard(
                                    key: _videoKey(video.videoId),
                                    video: video,
                                    displayName: _videoDisplayName(video),
                                    contentUrl: _qaService.videoContentUrl(
                                      video.videoId,
                                    ),
                                    isQueryTarget:
                                        _selectedScope == video.videoId,
                                    onSelectForQuery: () => setState(
                                      () => _selectedScope = video.videoId,
                                    ),
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              )
            : DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  border: Border(left: BorderSide(color: AppColors.border)),
                ),
                child: Align(
                  alignment: Alignment.topCenter,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: IconButton(
                      key: const ValueKey('expand-video-rail'),
                      onPressed: () => setState(() => _showVideoRail = true),
                      tooltip: context.tr('Expand video panel'),
                      color: AppColors.tealDark,
                      icon: const Icon(Icons.keyboard_double_arrow_left),
                    ),
                  ),
                ),
              ),
      ),
    );
  }

  Widget _buildEmptyVideoRail() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.video_library_outlined,
              color: AppColors.textSubtle,
              size: 34,
            ),
            const SizedBox(height: 10),
            Text(
              'Chưa có video',
              style: TextStyle(
                color: AppColors.text,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _uploadingVideo ? null : _pickAndUploadVideo,
              icon: const Icon(Icons.add_rounded, size: 17),
              label: Text(_uploadingVideo ? 'Đang tải...' : 'Thêm video'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConversationSidebar() {
    if (_loadingConversations) {
      return Center(child: CircularProgressIndicator());
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Lịch sử phiên hỏi đáp',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                ),
              ),
              IconButton(
                icon: Icon(Icons.refresh, size: 18),
                onPressed: _loadConversations,
                tooltip: context.tr('Làm mới'),
              ),
            ],
          ),
        ),
        Divider(height: 1, color: AppColors.border),
        Expanded(
          child: _conversations.isEmpty
              ? Center(
                  child: Text(
                    'Chưa có phiên hỏi đáp nào',
                    style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                )
              : ListView.builder(
                  itemCount: _conversations.length,
                  itemBuilder: (context, index) {
                    final conv = _conversations[index];
                    final isSelected = conv.id == _selectedConversation?.id;
                    return Container(
                      color: isSelected
                          ? AppColors.tealSoft
                          : Colors.transparent,
                      child: ListTile(
                        dense: true,
                        contentPadding: const EdgeInsets.only(
                          left: 16,
                          right: 8,
                        ),
                        minLeadingWidth: 24,
                        horizontalTitleGap: 10,
                        minVerticalPadding: 10,
                        leading: Icon(
                          Icons.chat_bubble_outline,
                          size: 18,
                          color: isSelected
                              ? AppColors.teal
                              : AppColors.textMuted,
                        ),
                        title: Text(
                          conv.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: isSelected
                                ? FontWeight.w600
                                : FontWeight.normal,
                            color: isSelected
                                ? AppColors.tealDark
                                : AppColors.text,
                          ),
                        ),
                        subtitle: Text(
                          '${conv.messageCount} tin nhắn',
                          style: TextStyle(
                            fontSize: 11,
                            color: AppColors.textSubtle,
                          ),
                        ),
                        trailing: IconButton(
                          constraints: const BoxConstraints.tightFor(
                            width: 36,
                            height: 36,
                          ),
                          padding: EdgeInsets.zero,
                          icon: Icon(
                            Icons.delete_outline,
                            size: 16,
                            color: AppColors.textSubtle,
                          ),
                          onPressed: () => _deleteConversation(conv.id),
                          tooltip: context.tr('Xóa phiên này'),
                        ),
                        onTap: () => _selectConversation(conv),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildChatBody() {
    if (_loadingMessages) {
      return Center(child: CircularProgressIndicator());
    }

    if (_messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.video_library_outlined,
              size: 56,
              color: AppColors.teal.withAlpha(90),
            ),
            const SizedBox(height: 16),
            Text(
              'Bắt đầu đặt câu hỏi về dữ liệu camera giám sát',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppColors.text,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Ví dụ: "Có ai lấy balo không?", "Có người nào cầm dao không?", "Ai mặc áo đỏ?"',
              style: TextStyle(fontSize: 13, color: AppColors.textMuted),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(16),
      itemCount: _messages.length,
      itemBuilder: (context, index) {
        final msg = _messages[index];
        return _buildMessageItem(msg);
      },
    );
  }

  Widget _buildMessageItem(QAMessageModel msg) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // User Question Bubble (Right aligned)
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 600),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: AppColors.teal,
                borderRadius: BorderRadius.circular(
                  AppRadii.md,
                ).copyWith(bottomRight: Radius.zero),
              ),
              child: Text(
                msg.userQueryVi,
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          ),
          const SizedBox(height: 10),

          // AI Response Card (Left aligned)
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 780),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(AppRadii.md),
                border: Border.all(color: AppColors.border),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withAlpha(10),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Type & Category Badge
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: _getTypeColor(msg.questionType).withAlpha(35),
                          borderRadius: BorderRadius.circular(AppRadii.sm),
                        ),
                        child: Text(
                          _getTypeName(msg.questionType),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: _getTypeColor(msg.questionType),
                          ),
                        ),
                      ),
                      const Spacer(),
                      Text(
                        msg.createdAt,
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.textSubtle,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),

                  _buildResponseContent(msg),

                  // Translation & Reasoning Accordion
                  if (msg.reasoningEn != null &&
                      msg.reasoningEn!.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Theme(
                      data: Theme.of(
                        context,
                      ).copyWith(dividerColor: Colors.transparent),
                      child: ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: Row(
                          children: [
                            Icon(
                              Icons.translate,
                              size: 14,
                              color: AppColors.teal,
                            ),
                            SizedBox(width: 6),
                            Text(
                              'Chi tiết kỹ thuật',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppColors.teal,
                              ),
                            ),
                          ],
                        ),
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceSubtle,
                              borderRadius: BorderRadius.circular(AppRadii.sm),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Query EN: "${msg.translatedQueryEn}"',
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontStyle: FontStyle.italic,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Reasoning: ${msg.reasoningEn}',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],

                  // Evidences section (Timestamps & Snapshots)
                  if (msg.evidences.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Bằng chứng theo thời gian',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textMuted,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      children: msg.evidences
                          .map((ev) => _buildEvidenceCard(ev))
                          .toList(),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResponseContent(QAMessageModel message) {
    final results = _parsePerVideoResults(message.responseVi);
    if (results.isEmpty) {
      return Text(
        message.responseVi,
        style: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          color: AppColors.text,
          height: 1.4,
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Kết quả trên ${results.length} video',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: 10),
        LayoutBuilder(
          builder: (context, constraints) {
            final cardWidth = constraints.maxWidth >= 620
                ? (constraints.maxWidth - 10) / 2
                : constraints.maxWidth;
            return Wrap(
              spacing: 10,
              runSpacing: 10,
              children: results.map((result) {
                final negative = _looksLikeNegativeResult(result.value);
                final statusColor = negative
                    ? AppColors.textMuted
                    : AppColors.success;
                return Container(
                  width: cardWidth,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceSubtle,
                    borderRadius: BorderRadius.circular(AppRadii.sm),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(
                          color: statusColor.withAlpha(24),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          negative ? Icons.remove_rounded : Icons.check_rounded,
                          size: 17,
                          color: statusColor,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              result.key,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: AppColors.text,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              result.value,
                              style: TextStyle(
                                fontSize: 12,
                                height: 1.35,
                                color: AppColors.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            );
          },
        ),
      ],
    );
  }

  List<MapEntry<String, String>> _parsePerVideoResults(String response) {
    if (!response.trimLeft().startsWith('Kết quả theo từng video:')) {
      return const [];
    }
    final labels = <String>[];
    final answers = <StringBuffer>[];
    for (final rawLine in response.split('\n')) {
      final line = rawLine.trim();
      if (line.startsWith('• ')) {
        final separator = line.indexOf(':', 2);
        if (separator <= 2 || separator >= line.length - 1) continue;
        labels.add(line.substring(2, separator).trim());
        answers.add(StringBuffer(line.substring(separator + 1).trim()));
      } else if (line.isNotEmpty && answers.isNotEmpty) {
        answers.last.write(' $line');
      }
    }
    return List.generate(
      labels.length,
      (index) => MapEntry(labels[index], answers[index].toString()),
    );
  }

  bool _looksLikeNegativeResult(String answer) {
    final value = answer.toLowerCase();
    return value.contains('không tìm thấy') ||
        value.contains('không phát hiện') ||
        value.contains('không có') ||
        value.contains('không thấy');
  }

  Widget _buildEvidenceCard(QAEvidenceModel ev) {
    final hasImage = ev.snapshotPath.isNotEmpty;
    final sourceVideo = _videoForId(ev.sourceVideoId);
    final imageUrl = hasImage
        ? '${ApiConfig.baseUrl}/qa/evidences/${ev.id}/snapshot'
        : '';

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _focusEvidence(ev),
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Container(
          width: 220,
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: AppColors.surfaceSubtle,
            borderRadius: BorderRadius.circular(AppRadii.sm),
            border: Border.all(color: AppColors.borderStrong),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (sourceVideo != null) ...[
                Row(
                  children: [
                    Icon(
                      Icons.video_file_outlined,
                      size: 13,
                      color: AppColors.teal,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        _videoDisplayName(sourceVideo),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.tealDark,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
              ],
              // Timestamp badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.black87,
                  borderRadius: BorderRadius.circular(AppRadii.sm),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.timer_outlined, size: 12, color: Colors.white),
                    const SizedBox(width: 4),
                    Text(
                      'Mốc: ${ev.formattedTimeRange}',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 6),

              // Snapshot Image Thumbnail
              ClipRRect(
                borderRadius: BorderRadius.circular(AppRadii.sm),
                child: hasImage
                    ? Image.network(
                        imageUrl,
                        height: 110,
                        width: double.infinity,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) => Container(
                          height: 110,
                          color: Colors.grey.shade300,
                          child: Center(
                            child: Icon(Icons.broken_image, color: Colors.grey),
                          ),
                        ),
                      )
                    : Container(
                        height: 110,
                        color: Colors.grey.shade200,
                        child: Center(
                          child: Icon(Icons.videocam, color: Colors.grey),
                        ),
                      ),
              ),
              if (ev.explanation != null && ev.explanation!.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  ev.explanation!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted),
                ),
              ],
              if (ev.eventType != null || ev.confidence != null) ...[
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    if (ev.eventType != null)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        label: Text(
                          ev.eventType!.replaceAll('_', ' '),
                          style: const TextStyle(fontSize: 11),
                        ),
                      ),
                    if (ev.detectedLabel != null)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        label: Text(
                          ev.detectedLabel!.replaceAll('_', ' '),
                          style: const TextStyle(fontSize: 11),
                        ),
                      ),
                    if (ev.confidence != null)
                      Chip(
                        visualDensity: VisualDensity.compact,
                        label: Text(
                          'Confidence ${(ev.confidence! * 100).toStringAsFixed(1)}%',
                          style: const TextStyle(fontSize: 11),
                        ),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 6),
              Row(
                children: [
                  Icon(
                    Icons.play_circle_outline,
                    size: 14,
                    color: AppColors.teal,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'Mở video tại ${ev.formattedTimeRange}',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.teal,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 10, 18, 14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(10),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.filter_alt_outlined, size: 14, color: AppColors.teal),
              const SizedBox(width: 5),
              Text(
                'Phạm vi: ${_scopeLabel()}',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textMuted,
                ),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _questionController,
                  decoration: InputDecoration(
                    hintText: context.tr('Đặt câu hỏi về video đã chọn...'),
                    hintStyle: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSubtle,
                    ),
                    filled: true,
                    fillColor: AppColors.surfaceSubtle,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.md),
                      borderSide: BorderSide(color: AppColors.border),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.md),
                      borderSide: BorderSide(color: AppColors.border),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadii.md),
                      borderSide: BorderSide(color: AppColors.teal, width: 1.5),
                    ),
                  ),
                  onSubmitted: (_) => _handleSend(),
                ),
              ),
              const SizedBox(width: 10),
              SizedBox(
                height: 46,
                width: 46,
                child: ElevatedButton(
                  onPressed: _sending ? null : () => _handleSend(),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    foregroundColor: Colors.white,
                    padding: EdgeInsets.zero,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadii.md),
                    ),
                  ),
                  child: _sending
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.arrow_upward_rounded, size: 21),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Color _getTypeColor(String type) {
    switch (type) {
      case 'threat':
        return AppColors.danger;
      case 'object_reasoning':
        return AppColors.teal;
      case 'attribute':
        return AppColors.warning;
      case 'identity':
        return AppColors.success;
      default:
        return AppColors.tealDark;
    }
  }

  String _getTypeName(String type) {
    switch (type) {
      case 'threat':
        return 'CẢNH BÁO NGUY HIỂM / VŨ KHÍ';
      case 'object_reasoning':
        return 'SUY LUẬN ĐỒ VẬT & TRỘM CẮP';
      case 'attribute':
        return 'NHẬN DẠNG MÀU ÁO & PHỤ KIỆN';
      case 'identity':
        return 'NHẬN DẠNG QUEN / LẠ';
      case 'count':
        return 'ĐẾM SỐ LƯỢNG NGƯỜI';
      case 'temporal':
        return 'ĐỊNH VỊ MỐC THỜI GIAN';
      default:
        return 'HỎI ĐÁP AN NINH';
    }
  }
}

class _QAVideoPlayerCard extends StatefulWidget {
  const _QAVideoPlayerCard({
    super.key,
    required this.video,
    required this.displayName,
    required this.contentUrl,
    required this.isQueryTarget,
    required this.onSelectForQuery,
  });

  final QAUploadedVideoModel video;
  final String displayName;
  final String contentUrl;
  final bool isQueryTarget;
  final VoidCallback onSelectForQuery;

  @override
  State<_QAVideoPlayerCard> createState() => _QAVideoPlayerCardState();
}

class _QAVideoPlayerCardState extends State<_QAVideoPlayerCard> {
  late final Player _player;
  late final VideoController _controller;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _player = Player();
    _controller = VideoController(_player);
    _openVideo();
  }

  Future<void> _openVideo() async {
    try {
      await _player.open(Media(widget.contentUrl), play: false);
      if (mounted) setState(() => _loading = false);
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = 'Không thể phát video này';
        });
      }
    }
  }

  Future<void> seekTo(Duration position) async {
    await _player.seek(position);
    await _player.play();
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statusColor = widget.video.isCompleted
        ? AppColors.success
        : widget.video.isFailed
        ? AppColors.danger
        : AppColors.warning;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        border: Border.all(
          color: widget.isQueryTarget ? AppColors.teal : Colors.white24,
          width: widget.isQueryTarget ? 2 : 1,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Column(
          children: [
            Container(
              height: 36,
              padding: const EdgeInsets.only(left: 10, right: 4),
              color: const Color(0xFF121B24),
              child: Row(
                children: [
                  Container(
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 7),
                  Expanded(
                    child: Text(
                      widget.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  if (widget.isQueryTarget)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 6),
                      child: Text(
                        'ĐANG CHỌN',
                        style: TextStyle(
                          color: AppColors.teal,
                          fontSize: 9,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    )
                  else
                    IconButton(
                      onPressed: widget.onSelectForQuery,
                      tooltip: 'Chỉ hỏi trên video này',
                      icon: const Icon(
                        Icons.filter_center_focus,
                        color: Colors.white70,
                        size: 17,
                      ),
                    ),
                ],
              ),
            ),
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Video(controller: _controller, fit: BoxFit.contain),
                  if (_loading)
                    const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  if (_error != null)
                    ColoredBox(
                      color: Colors.black87,
                      child: Center(
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text(
                            _error!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
