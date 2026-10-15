from dataclasses import dataclass
from enum import StrEnum


class SurveillanceSessionStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class LiveSurveillanceState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class VideoAnalysisState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DetectionStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    LOW_QUALITY = "low_quality"


class AlertType(StrEnum):
    UNKNOWN_PERSON = "unknown_person"
    RESTRICTED_AREA = "restricted_area"
    LOITERING = "loitering"
    KNIFE_THREAT = "knife_threat"
    WEAPON_DRAWN = "weapon_drawn"
    FIRE_SMOKE = "fire_smoke"
    THEFT = "theft"
    VIOLENCE = "violence"

class EntityType(StrEnum):
    PERSON = "person"
    OBJECT = "object"
    WEAPON = "weapon"
class ThreatType(StrEnum):
    KNIFE_THREAT = "knife_threat"
    WEAPON_DRAWN = "weapon_drawn"
    FIRE_SMOKE = "fire_smoke"
    THEFT = "theft"
    VIOLENCE = "violence"
class QAQuestionType(StrEnum):
    IDENTITY = "identity"
    ATTRIBUTE = "attribute"
    THREAT = "threat"
    TEMPORAL = "temporal"
    COUNT = "count"
    OBJECT_REASONING = "object_reasoning"
    GENERAL = "general"

class QAUploadedVideoStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SavedFaceImage:
    id: int
    image_path: str
    embedding_path: str | None
    created_at: str


@dataclass(frozen=True)
class CameraRecord:
    id: int
    name: str
    source: str
    location: str | None
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SurveillanceSessionRecord:
    id: int
    camera_id: int
    status: SurveillanceSessionStatus
    started_at: str
    ended_at: str | None
    average_fps: float | None
    frames_processed: int
    error_message: str | None


@dataclass(frozen=True)
class DetectionLogRecord:
    id: int
    session_id: int
    camera_id: int
    member_id: int | None
    track_id: int | None
    status: DetectionStatus
    confidence: float | None
    snapshot_path: str | None
    detected_at: str


@dataclass(frozen=True)
class AlertRecord:
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


@dataclass(frozen=True)
class ZoneRecord:
    id: int
    camera_id: int
    name: str
    polygon_json: str
    is_active: bool
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class VideoFrameRecord:
    id: int
    camera_id: int
    session_or_video_id: str
    timestamp_seconds: float
    frame_number: int
    frame_path: str
    person_count: int
    scene_caption_en: str | None
    visual_embedding: str | None
    created_at: str

@dataclass(frozen=True)
class DetectedEntityRecord:
    id: int
    frame_id: int
    track_id: int | None
    member_id: int | None
    entity_type: EntityType
    label: str
    bbox_json: str
    confidence: float | None
    clothing_top_color: str | None
    clothing_bottom_color: str | None
    accessories_json: str | None
    movement_direction: str | None
    action_label: str | None
    created_at: str

@dataclass(frozen=True)
class DangerThreatRecord:
    id: int
    frame_id: int
    threat_type: ThreatType
    confidence: float
    snapshot_path: str
    description_en: str | None
    is_resolved: bool
    created_at: str

@dataclass(frozen=True)
class QAConversationRecord:
    id: int
    title: str
    created_at: str

@dataclass(frozen=True)
class QAMessageRecord:
    id: int
    conversation_id: int
    user_query_vi: str
    translated_query_en: str
    reasoning_en: str | None
    response_vi: str
    question_type: QAQuestionType
    created_at: str

@dataclass(frozen=True)
class QAEvidenceRecord:
    id: int
    message_id: int
    frame_id: int | None
    start_timestamp: float
    end_timestamp: float
    snapshot_path: str
    highlight_bbox_json: str | None
    explanation_vi: str | None

@dataclass(frozen=True)
class QAUploadedVideoRecord:
    id: int
    conversation_id: int
    video_id: str
    filename: str
    file_path: str
    status: QAUploadedVideoStatus
    processed_frames: int
    total_frames: int | None
    error_message: str | None
    created_at: str
    completed_at: str | None
