class QAEvidenceModel {
  const QAEvidenceModel({
    required this.id,
    required this.messageId,
    this.frameId,
    required this.startTimestamp,
    required this.endTimestamp,
    required this.snapshotPath,
    this.highlightBbox,
    this.explanation,
  });

  final int id;
  final int messageId;
  final int? frameId;
  final double startTimestamp;
  final double endTimestamp;
  final String snapshotPath;
  final List<int>? highlightBbox;
  final String? explanation;

  factory QAEvidenceModel.fromJson(Map<String, dynamic> json) {
    return QAEvidenceModel(
      id: json['id'] as int,
      messageId: json['message_id'] as int,
      frameId: json['frame_id'] as int?,
      startTimestamp: (json['start_timestamp'] as num).toDouble(),
      endTimestamp: (json['end_timestamp'] as num).toDouble(),
      snapshotPath: json['snapshot_path'] as String? ?? '',
      highlightBbox: (json['highlight_bbox'] as List<dynamic>?)
          ?.map((e) => (e as num).toInt())
          .toList(),
      explanation: json['explanation'] as String?,
    );
  }

  String get formattedTimeRange {
    final startMin = (startTimestamp / 60).floor();
    final startSec = (startTimestamp % 60).floor();
    final endMin = (endTimestamp / 60).floor();
    final endSec = (endTimestamp % 60).floor();

    final sMinStr = startMin.toString().padLeft(2, '0');
    final sSecStr = startSec.toString().padLeft(2, '0');
    final eMinStr = endMin.toString().padLeft(2, '0');
    final eSecStr = endSec.toString().padLeft(2, '0');

    if (startTimestamp == endTimestamp) {
      return '$sMinStr:$sSecStr';
    }
    return '$sMinStr:$sSecStr – $eMinStr:$eSecStr';
  }
}

class QAMessageModel {
  const QAMessageModel({
    required this.id,
    required this.conversationId,
    required this.userQueryVi,
    required this.translatedQueryEn,
    this.reasoningEn,
    required this.responseVi,
    required this.questionType,
    required this.createdAt,
    this.evidences = const [],
  });

  final int id;
  final int conversationId;
  final String userQueryVi;
  final String translatedQueryEn;
  final String? reasoningEn;
  final String responseVi;
  final String questionType;
  final String createdAt;
  final List<QAEvidenceModel> evidences;

  factory QAMessageModel.fromJson(Map<String, dynamic> json) {
    return QAMessageModel(
      id: json['id'] as int,
      conversationId: json['conversation_id'] as int,
      userQueryVi: json['user_query_vi'] as String? ?? '',
      translatedQueryEn: json['translated_query_en'] as String? ?? '',
      reasoningEn: json['reasoning_en'] as String?,
      responseVi: json['response_vi'] as String? ?? '',
      questionType: json['question_type'] as String? ?? 'general',
      createdAt: json['created_at'] as String? ?? '',
      evidences: (json['evidences'] as List<dynamic>?)
              ?.map((e) => QAEvidenceModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}

class QAConversationModel {
  const QAConversationModel({
    required this.id,
    required this.title,
    required this.createdAt,
    this.messageCount = 0,
  });

  final int id;
  final String title;
  final String createdAt;
  final int messageCount;

  factory QAConversationModel.fromJson(Map<String, dynamic> json) {
    return QAConversationModel(
      id: json['id'] as int,
      title: json['title'] as String? ?? 'Phiên hỏi đáp',
      createdAt: json['created_at'] as String? ?? '',
      messageCount: json['message_count'] as int? ?? 0,
    );
  }
}

class QAUploadedVideoModel {
  const QAUploadedVideoModel({
    required this.id,
    required this.conversationId,
    required this.videoId,
    required this.filename,
    required this.status,
    this.processedFrames = 0,
    this.totalFrames = 0,
    this.errorMessage,
    required this.createdAt,
    this.completedAt,
  });

  final int id;
  final int conversationId;
  final String videoId;
  final String filename;
  final String status;
  final int processedFrames;
  final int totalFrames;
  final String? errorMessage;
  final String createdAt;
  final String? completedAt;

  bool get isProcessing => status == 'processing' || status == 'queued';
  bool get isCompleted => status == 'completed';
  bool get isFailed => status == 'failed';

  factory QAUploadedVideoModel.fromJson(Map<String, dynamic> json) {
    return QAUploadedVideoModel(
      id: json['id'] as int,
      conversationId: json['conversation_id'] as int,
      videoId: json['video_id'] as String? ?? '',
      filename: json['filename'] as String? ?? '',
      status: json['status'] as String? ?? 'queued',
      processedFrames: json['processed_frames'] as int? ?? 0,
      totalFrames: json['total_frames'] as int? ?? 0,
      errorMessage: json['error_message'] as String?,
      createdAt: json['created_at'] as String? ?? '',
      completedAt: json['completed_at'] as String?,
    );
  }
}

class QAConversationDetailModel {
  const QAConversationDetailModel({
    required this.conversation,
    required this.messages,
    this.uploadedVideos = const [],
  });

  final QAConversationModel conversation;
  final List<QAMessageModel> messages;
  final List<QAUploadedVideoModel> uploadedVideos;

  factory QAConversationDetailModel.fromJson(Map<String, dynamic> json) {
    return QAConversationDetailModel(
      conversation: QAConversationModel.fromJson(
        json['conversation'] as Map<String, dynamic>,
      ),
      messages: (json['messages'] as List<dynamic>?)
              ?.map((e) => QAMessageModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      uploadedVideos: (json['uploaded_videos'] as List<dynamic>?)
              ?.map((e) => QAUploadedVideoModel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}
