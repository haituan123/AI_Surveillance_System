import os
import sqlite3
from pathlib import Path

from backend.app.config import (
    INSIGHTFACE_MODEL_NAME,
    INSIGHTFACE_ROOT,
    RUNTIME_DIRECTORIES,
    YOLO_MODEL_PATH,
)
from backend.app.database import SCHEMA_VERSION

REQUIRED_TABLES = {
    "people",
    "face_embeddings",
    "cameras",
    "surveillance_sessions",
    "detection_logs",
    "alerts",
    "zones",
    "video_frames",
    "detected_entities",
    "danger_threats",
    "qa_conversations",
    "qa_messages",
    "qa_evidences",
}


class ReadinessService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        runtime_directories: tuple[Path, ...] = RUNTIME_DIRECTORIES,
    ):
        self.connection = connection
        self.runtime_directories = runtime_directories

    def inspect(self) -> dict:
        database = self._database_status()
        storage = self._storage_status()
        ready = database["ready"] and storage["ready"]
        return {
            "status": "ready" if ready else "degraded",
            "database": database,
            "storage": storage,
            "ai_assets": self._ai_asset_status(),
        }

    def _database_status(self) -> dict:
        try:
            version = int(
                self.connection.execute("PRAGMA user_version").fetchone()[0]
            )
            tables = {
                row[0]
                for row in self.connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
            missing = sorted(REQUIRED_TABLES - tables)
            return {
                "ready": version == SCHEMA_VERSION and not missing,
                "schema_version": version,
                "expected_schema_version": SCHEMA_VERSION,
                "missing_tables": missing,
            }
        except sqlite3.Error as exc:
            return {
                "ready": False,
                "schema_version": None,
                "expected_schema_version": SCHEMA_VERSION,
                "missing_tables": sorted(REQUIRED_TABLES),
                "error": str(exc),
            }

    def _storage_status(self) -> dict:
        unavailable = [
            str(path)
            for path in self.runtime_directories
            if not path.is_dir() or not os.access(path, os.W_OK)
        ]
        return {
            "ready": not unavailable,
            "directory_count": len(self.runtime_directories),
            "unavailable_directories": unavailable,
        }

    @staticmethod
    def _ai_asset_status() -> dict:
        insightface_path = (
            INSIGHTFACE_ROOT / "models" / INSIGHTFACE_MODEL_NAME
        )
        yolo_path = Path(YOLO_MODEL_PATH)
        yolo_is_local_path = yolo_path.is_absolute() or yolo_path.parent != Path(
            "."
        )
        return {
            "lazy_loading": True,
            "insightface": (
                "available"
                if insightface_path.is_dir()
                else "download_on_first_use"
            ),
            "yolo": (
                "available"
                if yolo_path.is_file()
                else (
                    "missing_configured_file"
                    if yolo_is_local_path
                    else "download_on_first_use"
                )
            ),
        }
