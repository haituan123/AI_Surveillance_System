import sqlite3
from collections.abc import Iterator

from backend.app.config import DATABASE_PATH, ensure_runtime_directories

SCHEMA_VERSION = 4


def get_connection() -> sqlite3.Connection:
    ensure_runtime_directories()
    connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def db_session() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def _migrate_video_frames_null_camera(connection: sqlite3.Connection) -> None:
    """Migrate video_frames to make camera_id nullable if it was created with NOT NULL constraint."""
    try:
        table_info = connection.execute("PRAGMA table_info(video_frames)").fetchall()
        if not table_info:
            return
        needs_migration = False
        for col in table_info:
            col_name = col[1] if isinstance(col, tuple) else col["name"]
            is_not_null = col[3] if isinstance(col, tuple) else col["notnull"]
            if col_name == "camera_id" and is_not_null == 1:
                needs_migration = True
                break

        if needs_migration:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                CREATE TABLE video_frames_migrated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER,
                    session_or_video_id TEXT NOT NULL,
                    timestamp_seconds REAL NOT NULL,
                    frame_number INTEGER NOT NULL,
                    frame_path TEXT NOT NULL,
                    person_count INTEGER NOT NULL DEFAULT 0,
                    scene_caption_en TEXT,
                    visual_embedding TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO video_frames_migrated (
                    id, camera_id, session_or_video_id, timestamp_seconds,
                    frame_number, frame_path, person_count, scene_caption_en,
                    visual_embedding, created_at
                )
                SELECT
                    id, camera_id, session_or_video_id, timestamp_seconds,
                    frame_number, frame_path, person_count, scene_caption_en,
                    visual_embedding, created_at
                FROM video_frames
                """
            )
            connection.execute("DROP TABLE video_frames")
            connection.execute("ALTER TABLE video_frames_migrated RENAME TO video_frames")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_video_frames_cam_time
                ON video_frames(camera_id, timestamp_seconds)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_video_frames_session
                ON video_frames(session_or_video_id)
                """
            )
            connection.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS face_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            embedding_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            location TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS surveillance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK(status IN ('running', 'stopped', 'failed')),
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT,
            average_fps REAL CHECK(average_fps IS NULL OR average_fps >= 0),
            frames_processed INTEGER NOT NULL DEFAULT 0
                CHECK(frames_processed >= 0),
            error_message TEXT,
            FOREIGN KEY(camera_id) REFERENCES cameras(id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS detection_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            camera_id INTEGER NOT NULL,
            member_id INTEGER,
            track_id INTEGER,
            status TEXT NOT NULL
                CHECK(status IN ('known', 'unknown', 'low_quality')),
            confidence REAL CHECK(
                confidence IS NULL OR (confidence >= -1.0 AND confidence <= 1.0)
            ),
            snapshot_path TEXT,
            detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id)
                REFERENCES surveillance_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(camera_id) REFERENCES cameras(id),
            FOREIGN KEY(member_id) REFERENCES people(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            camera_id INTEGER NOT NULL,
            detection_log_id INTEGER,
            member_id INTEGER,
            alert_type TEXT NOT NULL
                CHECK(alert_type IN (
                    'unknown_person',
                    'restricted_area',
                    'loitering',
                    'knife_threat',
                    'weapon_drawn',
                    'fire_smoke',
                    'theft',
                    'violence'
                )),
            message TEXT NOT NULL,
            confidence REAL CHECK(
                confidence IS NULL OR (confidence >= -1.0 AND confidence <= 1.0)
            ),
            snapshot_path TEXT,
            is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id)
                REFERENCES surveillance_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(camera_id) REFERENCES cameras(id),
            FOREIGN KEY(detection_log_id)
                REFERENCES detection_logs(id) ON DELETE SET NULL,
            FOREIGN KEY(member_id) REFERENCES people(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            polygon_json TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
            UNIQUE(camera_id, name)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_face_embeddings_person
        ON face_embeddings(person_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_camera_started
        ON surveillance_sessions(camera_id, started_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_detection_logs_session_time
        ON detection_logs(session_id, detected_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_detection_logs_camera_time
        ON detection_logs(camera_id, detected_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alerts_created
        ON alerts(created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alerts_camera_created
        ON alerts(camera_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alerts_unread
        ON alerts(is_read, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_zones_camera
        ON zones(camera_id, is_active)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS video_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id INTEGER,
            session_or_video_id TEXT NOT NULL,
            timestamp_seconds REAL NOT NULL,
            frame_number INTEGER NOT NULL,
            frame_path TEXT NOT NULL,
            person_count INTEGER NOT NULL DEFAULT 0,
            scene_caption_en TEXT,
            visual_embedding TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(camera_id) REFERENCES cameras(id) ON DELETE CASCADE
        )
        """
    )
    _migrate_video_frames_null_camera(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS detected_entities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame_id INTEGER NOT NULL,
            track_id INTEGER,
            member_id INTEGER,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('person', 'object', 'weapon')),
            label TEXT NOT NULL,
            bbox_json TEXT NOT NULL,
            confidence REAL,
            clothing_top_color TEXT,
            clothing_bottom_color TEXT,
            accessories_json TEXT,
            movement_direction TEXT,
            action_label TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(frame_id) REFERENCES video_frames(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES people(id) ON DELETE SET NULL
        ) 
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS danger_threats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame_id INTEGER NOT NULL,
            threat_type TEXT NOT NULL CHECK(threat_type IN (
                'knife_threat', 'weapon_drawn', 'fire_smoke', 'theft', 'violence'
            )),
            confidence REAL NOT NULL,
            snapshot_path TEXT NOT NULL,
            description_en TEXT,
            is_resolved INTEGER NOT NULL DEFAULT 0 CHECK(is_resolved IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(frame_id) REFERENCES video_frames(id) ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Phiên hỏi đáp an ninh',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            user_query_vi TEXT NOT NULL,
            translated_query_en TEXT NOT NULL,
            reasoning_en TEXT,
            response_vi TEXT NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'general' CHECK(question_type IN (
                'identity', 'attribute', 'threat', 'temporal', 'count', 'object_reasoning', 'general'
            )),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES qa_conversations(id) ON DELETE CASCADE
        )
        """
    )
    
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_evidences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            frame_id INTEGER,
            start_timestamp REAL NOT NULL,
            end_timestamp REAL NOT NULL,
            snapshot_path TEXT NOT NULL,
            highlight_bbox_json TEXT,
            explanation_vi TEXT,
            FOREIGN KEY(message_id) REFERENCES qa_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(frame_id) REFERENCES video_frames(id) ON DELETE SET NULL
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_uploaded_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            video_id TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN (
                'queued', 'processing', 'completed', 'failed'
            )),
            processed_frames INTEGER NOT NULL DEFAULT 0,
            total_frames INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY(conversation_id) REFERENCES qa_conversations(id) ON DELETE CASCADE
        )
        """
    )

    # Các index tối ưu hóa tốc độ tìm kiếm
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_frames_cam_time
        ON video_frames(camera_id, timestamp_seconds)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_detected_entities_frame
        ON detected_entities(frame_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_detected_entities_attrs
        ON detected_entities(clothing_top_color, label, action_label)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_danger_threats_type
        ON danger_threats(threat_type, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_qa_messages_conv
        ON qa_messages(conversation_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_qa_uploaded_videos_conv
        ON qa_uploaded_videos(conversation_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_frames_session
        ON video_frames(session_or_video_id)
        """
    )

    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def init_db() -> None:
    ensure_runtime_directories()
    connection = get_connection()
    try:
        create_schema(connection)
    finally:
        connection.close()
