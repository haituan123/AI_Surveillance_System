import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart' hide Text;

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
  String? _errorMessage;
  Timer? _pollTimer;

  // Selected Scope Filter: 'all', 'webcam', or uploaded videoId
  String _selectedScope = 'all';

  final List<String> _quickPrompts = [
    'Trong video có ai lấy chiếc balo trên bàn không?',
    'Có ai cầm dao hoặc hành vi nguy hiểm không?',
    'Người mặc áo đen hoặc áo đỏ xuất hiện lúc mấy giờ?',
    'Có bao nhiêu người xuất hiện trong khung hình?',
    'Có ai để quên đồ vật nào không?',
  ];

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
          const Duration(seconds: 3), (_) => _pollVideoStatuses());
    }
  }

  Future<void> _pollVideoStatuses() async {
    if (_selectedConversation == null) return;
    try {
      final videos =
          await _qaService.listUploadedVideos(_selectedConversation!.id);
      if (!mounted) return;
      setState(() {
        _uploadedVideos = videos;
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
            'Xóa phiên hỏi đáp này sẽ đồng thời xóa toàn bộ tin nhắn, video đã tải lên và dữ liệu AI đã phân tích của phiên.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: Text('Hủy')),
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
          _selectedConversation =
              _conversations.isNotEmpty ? _conversations.first : null;
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
      );

      if (result == null ||
          result.files.isEmpty ||
          result.files.single.path == null) {
        return;
      }

      final filePath = result.files.single.path!;
      final filename = result.files.single.name;

      setState(() {
        _uploadingVideo = true;
        _errorMessage = null;
      });

      final uploaded = await _qaService.uploadVideo(
        conversationId: _selectedConversation!.id,
        filePath: filePath,
        filename: filename,
      );

      setState(() {
        _uploadedVideos.insert(0, uploaded);
        _selectedScope = uploaded.videoId;
        _uploadingVideo = false;
      });

      _showSnackBar(
          'Đã tải video lên. AI đang bắt đầu xử lý và lập chỉ mục frames...');
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
            'Bạn có chắc muốn xóa video "${video.filename}"?\nToàn bộ dữ liệu khung hình và AI nhận dạng liên quan đến video này sẽ được xóa khỏi cơ sở dữ liệu.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: Text('Hủy')),
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
      });
      _showSnackBar(
          'Đã xóa video "${video.filename}" và các dữ liệu liên quan');
    } catch (e) {
      _showSnackBar('Lỗi xóa video: $e');
    }
  }

  Future<void> _retryUploadedVideo(QAUploadedVideoModel video) async {
    try {
      final updated = await _qaService.retryVideo(video.videoId);
      setState(() {
        final idx =
            _uploadedVideos.indexWhere((v) => v.videoId == video.videoId);
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
    final isDesktop =
        MediaQuery.sizeOf(context).width >= AppBreakpoints.compact;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Row(
        children: [
          // Sidebar lịch sử (nếu là màn hình lớn)
          if (isDesktop)
            Container(
              width: 280,
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
                Expanded(child: _buildChatBody()),
                _buildInputBar(),
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
                  'Trợ lý Hỏi - Đáp Video Giám Sát (CCTV QA)',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppColors.text,
                  ),
                ),
                Text(
                  'Hỗ trợ hỏi đáp tự nhiên tiếng Việt • Suy luận vũ khí, trộm cắp, màu áo & mốc thời gian',
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
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: AppColors.surfaceSubtle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Error Banner if any
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

          // Scope selector & Upload button
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                Text(
                  'Phạm vi dữ liệu: ',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 8),

                // Button upload video
                OutlinedButton.icon(
                  onPressed: _uploadingVideo ? null : _pickAndUploadVideo,
                  icon: _uploadingVideo
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Icon(Icons.upload_file, size: 16),
                  label: Text(
                    _uploadingVideo ? 'Đang tải lên...' : 'Upload Video',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                  ),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.teal,
                    side: BorderSide(color: AppColors.teal),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                    ),
                  ),
                ),
                const SizedBox(width: 8),

                // Default scope options
                _buildScopeChip('all', 'Tất cả Camera & Video'),
                const SizedBox(width: 6),
                _buildScopeChip('webcam', 'Webcam Live Stream'),

                // Uploaded videos chips
                for (final video in _uploadedVideos) ...[
                  const SizedBox(width: 6),
                  _buildUploadedVideoChip(video),
                ],
              ],
            ),
          ),
          const SizedBox(height: 8),

          // Quick prompts
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: _quickPrompts.map((prompt) {
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ActionChip(
                    avatar: Icon(Icons.bolt, size: 14, color: AppColors.teal),
                    label: Text(prompt, style: TextStyle(fontSize: 12)),
                    backgroundColor: AppColors.surface,
                    side: BorderSide(color: AppColors.border),
                    onPressed: () => _handleSend(prompt),
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUploadedVideoChip(QAUploadedVideoModel video) {
    final isSelected = _selectedScope == video.videoId;
    Widget statusIcon;
    String tooltipStatus;

    if (video.isProcessing) {
      statusIcon = const SizedBox(
        width: 12,
        height: 12,
        child: CircularProgressIndicator(
          strokeWidth: 1.5,
          color: AppColors.teal,
        ),
      );
      tooltipStatus = video.totalFrames > 0
          ? 'Đang phân tích: ${video.processedFrames}/${video.totalFrames} frames'
          : 'Đang chuẩn bị xử lý...';
    } else if (video.isCompleted) {
      statusIcon = Icon(Icons.check_circle, size: 14, color: AppColors.success);
      tooltipStatus = 'Đã hoàn tất phân tích (${video.processedFrames} frames)';
    } else {
      statusIcon = Icon(Icons.error, size: 14, color: AppColors.danger);
      tooltipStatus =
          'Xử lý thất bại: ${video.errorMessage ?? "Lỗi không xác định"}';
    }

    final displayName = video.filename.length > 20
        ? '${video.filename.substring(0, 17)}...'
        : video.filename;

    return Tooltip(
      message: context.tr('${video.filename}\n$tooltipStatus'),
      child: FilterChip(
        avatar: statusIcon,
        label: Text(
          displayName,
          style: TextStyle(
            fontSize: 11,
            color: isSelected ? Colors.white : AppColors.text,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
        selected: isSelected,
        selectedColor: AppColors.teal,
        backgroundColor: AppColors.surface,
        side: BorderSide(
          color: isSelected
              ? AppColors.teal
              : (video.isFailed ? AppColors.danger : AppColors.border),
        ),
        onSelected: (selected) async {
          if (video.isFailed) {
            final shouldRetry = await showDialog<bool>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: Text('Video bị lỗi khi xử lý'),
                content: Text(
                    'Lỗi: ${video.errorMessage ?? "Không xác định"}\n\nBạn có muốn thử phân tích lại video này không?'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx, false),
                    child: Text('Đóng'),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.pop(ctx, true),
                    child: Text('Thử lại'),
                  ),
                ],
              ),
            );
            if (shouldRetry == true) {
              _retryUploadedVideo(video);
            }
          } else if (selected) {
            setState(() => _selectedScope = video.videoId);
          }
        },
        deleteIcon: Icon(Icons.close, size: 14),
        onDeleted: () => _deleteUploadedVideo(video),
        deleteButtonTooltipMessage:
            context.tr('Xóa video và dữ liệu liên quan'),
      ),
    );
  }

  Widget _buildScopeChip(String value, String label) {
    final isSelected = _selectedScope == value;
    return ChoiceChip(
      label: Text(label,
          style: TextStyle(
              fontSize: 11, color: isSelected ? Colors.white : AppColors.text)),
      selected: isSelected,
      selectedColor: AppColors.teal,
      backgroundColor: AppColors.surface,
      side: BorderSide(color: isSelected ? AppColors.teal : AppColors.border),
      onSelected: (selected) {
        if (selected) setState(() => _selectedScope = value);
      },
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
              Text(
                'Lịch sử phiên hỏi đáp',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
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
                  child: Text('Chưa có phiên hỏi đáp nào',
                      style:
                          TextStyle(color: AppColors.textMuted, fontSize: 12)),
                )
              : ListView.builder(
                  itemCount: _conversations.length,
                  itemBuilder: (context, index) {
                    final conv = _conversations[index];
                    final isSelected = conv.id == _selectedConversation?.id;
                    return Container(
                      color:
                          isSelected ? AppColors.tealSoft : Colors.transparent,
                      child: ListTile(
                        dense: true,
                        leading: Icon(
                          Icons.chat_bubble_outline,
                          size: 18,
                          color:
                              isSelected ? AppColors.teal : AppColors.textMuted,
                        ),
                        title: Text(
                          conv.title,
                          maxLines: 1,
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
                              fontSize: 11, color: AppColors.textSubtle),
                        ),
                        trailing: IconButton(
                          icon: Icon(Icons.delete_outline,
                              size: 16, color: AppColors.textSubtle),
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
            Icon(Icons.video_library_outlined,
                size: 56, color: AppColors.teal.withAlpha(90)),
            const SizedBox(height: 16),
            Text(
              'Bắt đầu đặt câu hỏi về dữ liệu camera giám sát',
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: AppColors.text),
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
                borderRadius: BorderRadius.circular(AppRadii.md).copyWith(
                  bottomRight: Radius.zero,
                ),
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
                            horizontal: 8, vertical: 3),
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
                            fontSize: 11, color: AppColors.textSubtle),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),

                  // Main Answer in Vietnamese
                  Text(
                    msg.responseVi,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: AppColors.text,
                      height: 1.4,
                    ),
                  ),

                  // Translation & Reasoning Accordion
                  if (msg.reasoningEn != null &&
                      msg.reasoningEn!.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Theme(
                      data: Theme.of(context)
                          .copyWith(dividerColor: Colors.transparent),
                      child: ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: Row(
                          children: [
                            Icon(Icons.translate,
                                size: 14, color: AppColors.teal),
                            SizedBox(width: 6),
                            Text(
                              'Bản dịch & Suy luận AI (Reasoning EN)',
                              style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  color: AppColors.teal),
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
                                Text('Query EN: "${msg.translatedQueryEn}"',
                                    style: TextStyle(
                                        fontSize: 12,
                                        fontStyle: FontStyle.italic)),
                                const SizedBox(height: 4),
                                Text('Reasoning: ${msg.reasoningEn}',
                                    style: TextStyle(
                                        fontSize: 12,
                                        color: AppColors.textMuted)),
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
                      'Bằng chứng xác thực (Evidence Clips & Timestamps):',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textMuted),
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

  Widget _buildEvidenceCard(QAEvidenceModel ev) {
    final hasImage = ev.snapshotPath.isNotEmpty;
    final imageUrl =
        hasImage ? '${ApiConfig.baseUrl}/qa/evidences/${ev.id}/snapshot' : '';

    return Container(
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
                      fontWeight: FontWeight.bold),
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
                          child: Icon(Icons.broken_image, color: Colors.grey)),
                    ),
                  )
                : Container(
                    height: 110,
                    color: Colors.grey.shade200,
                    child:
                        Center(child: Icon(Icons.videocam, color: Colors.grey)),
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
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _questionController,
              decoration: InputDecoration(
                hintText: context.tr(
                    'Nhập câu hỏi bằng tiếng Việt về video camera (VD: Có ai lấy balo không?)...'),
                hintStyle: TextStyle(fontSize: 13, color: AppColors.textSubtle),
                filled: true,
                fillColor: AppColors.surfaceSubtle,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
          const SizedBox(width: 12),
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
                          color: Colors.white, strokeWidth: 2))
                  : Icon(Icons.send_rounded, size: 20),
            ),
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
