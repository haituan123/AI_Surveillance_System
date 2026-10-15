from pydantic import BaseModel, Field

from backend.app.models import (
    AlertType,
    DetectionStatus,
    LiveSurveillanceState,
    SurveillanceSessionStatus,
    VideoAnalysisState,
)


class FaceImage(BaseModel):
    id: int
    image_path: str
    embedding_path: str | None = None
    created_at: str


class Member(BaseModel):
    id: int
    name: str
    created_at: str
    image_count: int


class MemberDetail(Member):
    images: list[FaceImage]


class RegistrationImageResult(BaseModel):
    filename: str
    status: str
    reason: str


class RegisterMemberResponse(BaseModel):
    member: MemberDetail
    message: str
    accepted_images: list[RegistrationImageResult]
    rejected_images: list[RegistrationImageResult]


class DeleteMemberResponse(BaseModel):
    message: str


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=2048)
    location: str | None = Field(default=None, max_length=255)


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source: str | None = Field(default=None, min_length=1, max_length=2048)
    location: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class Camera(BaseModel):
    id: int
    name: str
    source: str
    location: str | None
    is_active: bool
    created_at: str
    updated_at: str


class CameraDeleteResponse(BaseModel):
    message: str
    camera: Camera


class CameraTestResponse(BaseModel):
    available: bool
    width: int
    height: int
    message: str


class SurveillanceSession(BaseModel):
    id: int
    camera_id: int
    status: SurveillanceSessionStatus
    started_at: str
    ended_at: str | None
    average_fps: float | None
    frames_processed: int
    error_message: str | None


class SurveillanceStartRequest(BaseModel):
    camera_id: int = Field(gt=0)


class SurveillanceStatus(BaseModel):
    state: LiveSurveillanceState
    running: bool
    camera_id: int | None
    session_id: int | None
    frames_processed: int
    fps: float
    started_at: str | None
    error_message: str | None


class AnalysisBoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class AnalysisTrack(BaseModel):
    track_id: int
    bounding_box: AnalysisBoundingBox
    person_confidence: float
    status: DetectionStatus
    member_id: int | None
    member_name: str | None
    similarity: float | None
    face_confidence: float | None


class LatestFrameAnalysis(BaseModel):
    frame_index: int
    timestamp_seconds: float
    width: int
    height: int
    tracks: list[AnalysisTrack]


class VideoAnalysisStatus(BaseModel):
    job_id: str
    filename: str
    state: VideoAnalysisState
    persistent: bool
    processed_frames: int
    total_frames: int | None
    progress: float | None
    processing_fps: float
    created_at: str
    completed_at: str | None
    error_message: str | None


class TemporaryVideoEvent(BaseModel):
    frame_index: int
    timestamp_seconds: float
    track_id: int
    status: DetectionStatus
    member_id: int | None
    member_name: str | None
    similarity: float | None
    event_type: str


class VideoAnalysisSummary(BaseModel):
    total_frames: int
    duration_seconds: float
    average_processing_fps: float
    known_events: int
    unknown_events: int
    events_truncated: bool


class VideoAnalysisResults(BaseModel):
    job_id: str
    filename: str
    state: VideoAnalysisState
    persistent: bool
    summary: VideoAnalysisSummary
    events: list[TemporaryVideoEvent]
    error_message: str | None


class VideoAnalysisDeleteResponse(BaseModel):
    message: str
    job_id: str


class DetectionLog(BaseModel):
    id: int
    session_id: int
    camera_id: int
    member_id: int | None
    track_id: int | None
    status: DetectionStatus
    confidence: float | None
    snapshot_path: str | None
    detected_at: str


class DetectionLogView(DetectionLog):
    member_name: str | None
    camera_name: str


class DeleteLogResponse(BaseModel):
    message: str
    deleted_log_id: int
    deleted_snapshot: bool


class DeleteLogsResponse(BaseModel):
    message: str
    deleted_count: int
    deleted_snapshots: int


class Alert(BaseModel):
    id: int
    session_id: int
    camera_id: int
    detection_log_id: int | None
    member_id: int | None
    alert_type: AlertType
    message: str
    confidence: float | None
    snapshot_path: str | None
    is_read: bool
    created_at: str


class AlertView(Alert):
    member_name: str | None
    camera_name: str
    snapshot_url: str | None


class DeleteAlertResponse(BaseModel):
    message: str
    deleted_alert_id: int
    deleted_snapshot: bool


class DeleteAlertsResponse(BaseModel):
    message: str
    deleted_count: int
    deleted_snapshots: int


class AlertReadUpdate(BaseModel):
    is_read: bool = True


class ZonePoint(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class ZoneCreate(BaseModel):
    camera_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    points: list[ZonePoint] = Field(min_length=4, max_length=4)


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    points: list[ZonePoint] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
    )
    is_active: bool | None = None


class Zone(BaseModel):
    id: int
    camera_id: int
    name: str
    points: list[ZonePoint]
    is_active: bool
    created_at: str
    updated_at: str


# ==================== QA QUESTION ANSWERING SCHEMAS ====================
class QAConversationCreate(BaseModel):
    title: str = Field(default="Phiên hỏi đáp an ninh", max_length=200)


class QAConversation(BaseModel):
    id: int
    title: str
    created_at: str
    message_count: int = 0


class QAAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: int | None = None
    camera_id: int | None = None
    session_or_video_id: str | None = None


class QAEvidence(BaseModel):
    id: int
    message_id: int
    frame_id: int | None = None
    start_timestamp: float
    end_timestamp: float
    snapshot_path: str
    highlight_bbox: list[int] | None = None
    explanation: str | None = None


class QAMessage(BaseModel):
    id: int
    conversation_id: int
    user_query_vi: str
    translated_query_en: str
    reasoning_en: str | None = None
    response_vi: str
    question_type: str
    created_at: str
    evidences: list[QAEvidence] = []


class QAConversationDetail(BaseModel):
    conversation: QAConversation
    messages: list[QAMessage]
    uploaded_videos: list["QAUploadedVideo"] = []


class QAUploadedVideo(BaseModel):
    id: int
    conversation_id: int
    video_id: str
    filename: str
    status: str
    processed_frames: int = 0
    total_frames: int | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None
