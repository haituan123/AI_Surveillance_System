class CameraModel {
  const CameraModel({
    required this.id,
    required this.name,
    required this.source,
    required this.isActive,
    this.location,
  });

  factory CameraModel.fromJson(Map<String, dynamic> json) => CameraModel(
    id: json['id'] as int,
    name: json['name'] as String,
    source: json['source'] as String,
    location: json['location'] as String?,
    isActive: json['is_active'] as bool,
  );

  final int id;
  final String name;
  final String source;
  final String? location;
  final bool isActive;
}

class SurveillanceStatusModel {
  const SurveillanceStatusModel({
    required this.state,
    required this.running,
    required this.framesProcessed,
    required this.fps,
    this.cameraId,
    this.sessionId,
    this.errorMessage,
  });

  factory SurveillanceStatusModel.fromJson(Map<String, dynamic> json) =>
      SurveillanceStatusModel(
        state: json['state'] as String,
        running: json['running'] as bool,
        cameraId: json['camera_id'] as int?,
        sessionId: json['session_id'] as int?,
        framesProcessed: json['frames_processed'] as int,
        fps: (json['fps'] as num).toDouble(),
        errorMessage: json['error_message'] as String?,
      );

  final String state;
  final bool running;
  final int? cameraId;
  final int? sessionId;
  final int framesProcessed;
  final double fps;
  final String? errorMessage;
}

class AnalysisTrackModel {
  const AnalysisTrackModel({
    required this.trackId,
    required this.status,
    required this.personConfidence,
    required this.boundingBox,
    this.memberName,
    this.similarity,
  });

  factory AnalysisTrackModel.fromJson(Map<String, dynamic> json) =>
      AnalysisTrackModel(
        trackId: json['track_id'] as int,
        status: json['status'] as String,
        personConfidence: (json['person_confidence'] as num).toDouble(),
        boundingBox: AnalysisBoundingBoxModel.fromJson(
          json['bounding_box'] as Map<String, dynamic>,
        ),
        memberName: json['member_name'] as String?,
        similarity: (json['similarity'] as num?)?.toDouble(),
      );

  final int trackId;
  final String status;
  final double personConfidence;
  final AnalysisBoundingBoxModel boundingBox;
  final String? memberName;
  final double? similarity;
}

class LatestAnalysisModel {
  const LatestAnalysisModel({
    required this.frameIndex,
    required this.width,
    required this.height,
    required this.tracks,
  });

  factory LatestAnalysisModel.fromJson(Map<String, dynamic> json) =>
      LatestAnalysisModel(
        frameIndex: json['frame_index'] as int,
        width: json['width'] as int,
        height: json['height'] as int,
        tracks: (json['tracks'] as List<dynamic>)
            .map(
              (item) =>
                  AnalysisTrackModel.fromJson(item as Map<String, dynamic>),
            )
            .toList(),
      );

  final int frameIndex;
  final int width;
  final int height;
  final List<AnalysisTrackModel> tracks;
}

class AnalysisBoundingBoxModel {
  const AnalysisBoundingBoxModel({
    required this.x1,
    required this.y1,
    required this.x2,
    required this.y2,
  });

  factory AnalysisBoundingBoxModel.fromJson(Map<String, dynamic> json) =>
      AnalysisBoundingBoxModel(
        x1: json['x1'] as int,
        y1: json['y1'] as int,
        x2: json['x2'] as int,
        y2: json['y2'] as int,
      );

  final int x1;
  final int y1;
  final int x2;
  final int y2;
}

class ZonePointModel {
  const ZonePointModel({required this.x, required this.y});

  factory ZonePointModel.fromJson(Map<String, dynamic> json) =>
      ZonePointModel(x: json['x'] as int, y: json['y'] as int);

  Map<String, dynamic> toJson() => {'x': x, 'y': y};

  final int x;
  final int y;
}

class ZoneModel {
  const ZoneModel({
    required this.id,
    required this.cameraId,
    required this.name,
    required this.points,
    required this.isActive,
  });

  factory ZoneModel.fromJson(Map<String, dynamic> json) => ZoneModel(
    id: json['id'] as int,
    cameraId: json['camera_id'] as int,
    name: json['name'] as String,
    points: (json['points'] as List<dynamic>)
        .map((item) => ZonePointModel.fromJson(item as Map<String, dynamic>))
        .toList(),
    isActive: json['is_active'] as bool,
  );

  final int id;
  final int cameraId;
  final String name;
  final List<ZonePointModel> points;
  final bool isActive;
}

class VideoAnalysisStatusModel {
  const VideoAnalysisStatusModel({
    required this.jobId,
    required this.filename,
    required this.state,
    required this.persistent,
    required this.processedFrames,
    required this.processingFps,
    this.totalFrames,
    this.progress,
    this.errorMessage,
  });

  factory VideoAnalysisStatusModel.fromJson(Map<String, dynamic> json) =>
      VideoAnalysisStatusModel(
        jobId: json['job_id'] as String,
        filename: json['filename'] as String,
        state: json['state'] as String,
        persistent: json['persistent'] as bool,
        processedFrames: json['processed_frames'] as int,
        totalFrames: json['total_frames'] as int?,
        progress: (json['progress'] as num?)?.toDouble(),
        processingFps: (json['processing_fps'] as num).toDouble(),
        errorMessage: json['error_message'] as String?,
      );

  bool get isActive => state == 'queued' || state == 'running';

  final String jobId;
  final String filename;
  final String state;
  final bool persistent;
  final int processedFrames;
  final int? totalFrames;
  final double? progress;
  final double processingFps;
  final String? errorMessage;
}

class TemporaryVideoEventModel {
  const TemporaryVideoEventModel({
    required this.frameIndex,
    required this.timestampSeconds,
    required this.status,
    required this.eventType,
    this.memberName,
    this.similarity,
  });

  factory TemporaryVideoEventModel.fromJson(Map<String, dynamic> json) =>
      TemporaryVideoEventModel(
        frameIndex: json['frame_index'] as int,
        timestampSeconds: (json['timestamp_seconds'] as num).toDouble(),
        status: json['status'] as String,
        eventType: json['event_type'] as String,
        memberName: json['member_name'] as String?,
        similarity: (json['similarity'] as num?)?.toDouble(),
      );

  final int frameIndex;
  final double timestampSeconds;
  final String status;
  final String eventType;
  final String? memberName;
  final double? similarity;
}

class VideoAnalysisResultsModel {
  const VideoAnalysisResultsModel({
    required this.state,
    required this.persistent,
    required this.knownEvents,
    required this.unknownEvents,
    required this.events,
  });

  factory VideoAnalysisResultsModel.fromJson(Map<String, dynamic> json) {
    final summary = json['summary'] as Map<String, dynamic>;
    return VideoAnalysisResultsModel(
      state: json['state'] as String,
      persistent: json['persistent'] as bool,
      knownEvents: summary['known_events'] as int,
      unknownEvents: summary['unknown_events'] as int,
      events: (json['events'] as List<dynamic>)
          .map(
            (item) =>
                TemporaryVideoEventModel.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
    );
  }

  final String state;
  final bool persistent;
  final int knownEvents;
  final int unknownEvents;
  final List<TemporaryVideoEventModel> events;
}

class DetectionLogModel {
  const DetectionLogModel({
    required this.id,
    required this.sessionId,
    required this.status,
    required this.cameraName,
    required this.detectedAt,
    this.trackId,
    this.memberName,
    this.confidence,
  });

  factory DetectionLogModel.fromJson(Map<String, dynamic> json) =>
      DetectionLogModel(
        id: json['id'] as int,
        sessionId: json['session_id'] as int,
        trackId: json['track_id'] as int?,
        status: json['status'] as String,
        memberName: json['member_name'] as String?,
        cameraName: json['camera_name'] as String,
        confidence: (json['confidence'] as num?)?.toDouble(),
        detectedAt: json['detected_at'] as String,
      );

  final int id;
  final int sessionId;
  final int? trackId;
  final String status;
  final String? memberName;
  final String cameraName;
  final double? confidence;
  final String detectedAt;
}

enum AlertCategory {
  unknownPerson,
  restrictedArea,
  loitering,
  knifeThreat,
  weaponDrawn,
  fireSmoke,
  theft,
  violence,
  general,
}

class AlertModel {
  const AlertModel({
    required this.id,
    required this.detectionLogId,
    required this.alertType,
    required this.message,
    required this.cameraName,
    required this.isRead,
    required this.createdAt,
    this.snapshotUrl,
  });

  factory AlertModel.fromJson(Map<String, dynamic> json) => AlertModel(
    id: json['id'] as int,
    detectionLogId: json['detection_log_id'] as int?,
    alertType: json['alert_type'] as String,
    message: json['message'] as String,
    cameraName: json['camera_name'] as String,
    isRead: json['is_read'] as bool,
    createdAt: json['created_at'] as String,
    snapshotUrl: json['snapshot_url'] as String?,
  );

  final int id;
  final int? detectionLogId;
  final String alertType;
  final String message;
  final String cameraName;
  final bool isRead;
  final String createdAt;
  final String? snapshotUrl;

  AlertCategory get category {
    switch (alertType) {
      case 'unknown_person':
        return AlertCategory.unknownPerson;
      case 'restricted_area':
        return AlertCategory.restrictedArea;
      case 'loitering':
        return AlertCategory.loitering;
      case 'knife_threat':
        return AlertCategory.knifeThreat;
      case 'weapon_drawn':
        return AlertCategory.weaponDrawn;
      case 'fire_smoke':
        return AlertCategory.fireSmoke;
      case 'theft':
        return AlertCategory.theft;
      case 'violence':
        return AlertCategory.violence;
      default:
        return AlertCategory.general;
    }
  }

  String get categoryTitle {
    switch (category) {
      case AlertCategory.unknownPerson:
        return 'Người lạ';
      case AlertCategory.restrictedArea:
        return 'Vùng cấm';
      case AlertCategory.loitering:
        return 'Lảng vảng';
      case AlertCategory.knifeThreat:
        return 'Cầm dao / Vũ khí nhọn';
      case AlertCategory.weaponDrawn:
        return 'Vũ khí nguy hiểm';
      case AlertCategory.fireSmoke:
        return 'Cháy nổ / Khói';
      case AlertCategory.theft:
        return 'Lấy trộm đồ vật';
      case AlertCategory.violence:
        return 'Hành vi bạo lực';
      case AlertCategory.general:
        return 'Cảnh báo an ninh';
    }
  }
}

