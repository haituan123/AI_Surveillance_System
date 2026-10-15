import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _load_env_file() -> None:
    for env_path in [BASE_DIR / ".env", BASE_DIR.parent / ".env"]:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip("'\"")
                            if key and key not in os.environ:
                                os.environ[key] = val
            except Exception:
                pass


_load_env_file()


def _path_setting(name: str, default: Path) -> Path:
    configured = os.getenv(name)
    if not configured:
        return default.resolve()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _int_setting(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _float_setting(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = _int_setting("BACKEND_PORT", 8000)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

# Google Gemini API Settings for Video QA
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

DATA_DIR = _path_setting("DATA_DIR", BASE_DIR / "data")
DATABASE_PATH = _path_setting("DATABASE_PATH", BASE_DIR / "database" / "app.db")
DATABASE_DIR = DATABASE_PATH.parent
KNOWN_FACES_DIR = _path_setting(
    "KNOWN_FACES_DIR",
    DATA_DIR / "known_faces",
)
EMBEDDINGS_DIR = _path_setting(
    "EMBEDDINGS_DIR",
    DATA_DIR / "embeddings",
)
SNAPSHOTS_DIR = _path_setting(
    "SNAPSHOTS_DIR",
    DATA_DIR / "snapshots",
)
TEST_VIDEOS_DIR = _path_setting(
    "TEST_VIDEOS_DIR",
    DATA_DIR / "test_videos",
)
TEMP_UPLOADS_DIR = _path_setting(
    "TEMP_UPLOADS_DIR",
    DATA_DIR / "temp_uploads",
)

MODELS_DIR = _path_setting("MODELS_DIR", BASE_DIR / "models")
INSIGHTFACE_ROOT = _path_setting(
    "INSIGHTFACE_ROOT",
    MODELS_DIR / "insightface",
)
INSIGHTFACE_MODEL_NAME = os.getenv("INSIGHTFACE_MODEL_NAME", "buffalo_l")
YOLO_MODELS_DIR = _path_setting("YOLO_MODELS_DIR", MODELS_DIR / "yolo")

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MIN_FACE_IMAGE_WIDTH = _int_setting("MIN_FACE_IMAGE_WIDTH", 80)
MIN_FACE_IMAGE_HEIGHT = _int_setting("MIN_FACE_IMAGE_HEIGHT", 80)
MIN_DETECTED_FACE_SIZE = _int_setting("MIN_DETECTED_FACE_SIZE", 40)
FACE_CROP_PADDING_RATIO = _float_setting("FACE_CROP_PADDING_RATIO", 0.25)
FACE_CROP_SIZE = _int_setting("FACE_CROP_SIZE", 160)
FACE_DETECTION_THRESHOLD = _float_setting("FACE_DETECTION_THRESHOLD", 0.30)
FACE_MATCH_THRESHOLD = _float_setting("FACE_MATCH_THRESHOLD", 0.35)
PERSON_DETECTION_THRESHOLD = _float_setting(
    "PERSON_DETECTION_THRESHOLD",
    0.40,
)
RECOGNITION_BUFFER_SIZE = _int_setting("RECOGNITION_BUFFER_SIZE", 10)
TRACK_FACE_PADDING_RATIO = _float_setting("TRACK_FACE_PADDING_RATIO", 0.40)
INSIGHTFACE_DET_SIZE = (
    _int_setting("INSIGHTFACE_DET_WIDTH", 640),
    _int_setting("INSIGHTFACE_DET_HEIGHT", 640),
)
YOLO_MODEL_PATH = str(
    _path_setting("YOLO_MODEL_PATH", YOLO_MODELS_DIR / "yolov8n.pt")
)
CAMERA_READ_FAILURE_LIMIT = _int_setting("CAMERA_READ_FAILURE_LIMIT", 5)
SURVEILLANCE_STOP_TIMEOUT_SECONDS = _float_setting(
    "SURVEILLANCE_STOP_TIMEOUT_SECONDS",
    5.0,
)
UNKNOWN_CONFIRMATION_FRAMES = _int_setting(
    "UNKNOWN_CONFIRMATION_FRAMES",
    5,
)
ALERT_COOLDOWN_SECONDS = _float_setting("ALERT_COOLDOWN_SECONDS", 10.0)
RESTRICTED_ZONE_DWELL_SECONDS = _float_setting(
    "RESTRICTED_ZONE_DWELL_SECONDS",
    5.0,
)
RESTRICTED_ZONE_ALERT_COOLDOWN_SECONDS = _float_setting(
    "RESTRICTED_ZONE_ALERT_COOLDOWN_SECONDS",
    30.0,
)
VIDEO_UPLOAD_MAX_BYTES = _int_setting(
    "VIDEO_UPLOAD_MAX_BYTES",
    500 * 1024 * 1024,
)
VIDEO_ANALYSIS_RESULT_TTL_SECONDS = _float_setting(
    "VIDEO_ANALYSIS_RESULT_TTL_SECONDS",
    30 * 60,
)
VIDEO_ANALYSIS_STOP_TIMEOUT_SECONDS = _float_setting(
    "VIDEO_ANALYSIS_STOP_TIMEOUT_SECONDS",
    5.0,
)
VIDEO_ANALYSIS_MAX_EVENTS = _int_setting(
    "VIDEO_ANALYSIS_MAX_EVENTS",
    0,
)
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

RUNTIME_DIRECTORIES = (
    DATABASE_DIR,
    KNOWN_FACES_DIR,
    EMBEDDINGS_DIR,
    SNAPSHOTS_DIR,
    TEST_VIDEOS_DIR,
    TEMP_UPLOADS_DIR,
    MODELS_DIR,
    INSIGHTFACE_ROOT,
    YOLO_MODELS_DIR,
)


def ensure_runtime_directories() -> None:
    for directory in RUNTIME_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def serialize_storage_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(resolved)


def resolve_storage_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()
