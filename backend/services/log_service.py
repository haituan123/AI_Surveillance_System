import json
import sqlite3

from backend.app.models import DetectionStatus
from backend.app.config import resolve_storage_path


class LogService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_logs(
        self,
        *,
        status: DetectionStatus | None = None,
        camera_id: int | None = None,
        session_id: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
        conditions = []
        parameters: list[object] = []
        if status is not None:
            conditions.append("d.status = ?")
            parameters.append(status.value)
        if camera_id is not None:
            conditions.append("d.camera_id = ?")
            parameters.append(camera_id)
        if session_id is not None:
            conditions.append("d.session_id = ?")
            parameters.append(session_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT
                d.id,
                d.session_id,
                d.camera_id,
                d.member_id,
                d.track_id,
                d.status,
                d.confidence,
                d.snapshot_path,
                d.detected_at,
                p.name AS member_name,
                c.name AS camera_name
            FROM detection_logs d
            JOIN cameras c ON c.id = d.camera_id
            LEFT JOIN people p ON p.id = d.member_id
            {where}
            ORDER BY d.detected_at DESC, d.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_log(self) -> dict | None:
        logs = self.list_logs(limit=1)
        return logs[0] if logs else None

    def list_security_events(
        self,
        *,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions = []
        parameters: list[object] = []
        if event_type:
            conditions.append("se.event_type = ?")
            parameters.append(event_type)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT se.id, se.session_or_video_id AS source_id,
                   CASE WHEN qv.id IS NOT NULL THEN 'qa_video' ELSE 'camera' END
                       AS source_type,
                   COALESCE(qv.filename, c.name, se.session_or_video_id) AS source_name,
                   c.name AS camera_name, se.event_type,
                   se.start_timestamp, se.end_timestamp, se.confidence,
                   se.object_labels_json, se.actor_track_ids_json,
                   se.status, se.created_at
            FROM security_events se
            LEFT JOIN qa_uploaded_videos qv
                ON qv.video_id = se.session_or_video_id
            LEFT JOIN cameras c ON c.id = se.camera_id
            {where}
            ORDER BY se.created_at DESC, se.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            try:
                labels = json.loads(item.pop("object_labels_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                labels = []
            try:
                track_ids = json.loads(item.pop("actor_track_ids_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                track_ids = []
            item["detected_label"] = labels[0] if labels else None
            item["actor_track_ids"] = [int(value) for value in track_ids]
            events.append(item)
        return events

    def delete_log(self, log_id: int) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, snapshot_path
            FROM detection_logs
            WHERE id = ?
            """,
            (log_id,),
        ).fetchone()
        if row is None:
            return None

        snapshot_path = row["snapshot_path"]
        self.connection.execute(
            "DELETE FROM detection_logs WHERE id = ?",
            (log_id,),
        )
        self.connection.commit()

        deleted_snapshot = False
        if snapshot_path and not self._snapshot_is_referenced(snapshot_path):
            path = resolve_storage_path(snapshot_path)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted_snapshot = True
            except OSError:
                deleted_snapshot = False

        return {
            "message": "Detection log deleted",
            "deleted_log_id": log_id,
            "deleted_snapshot": deleted_snapshot,
        }

    def delete_all_logs(self) -> dict:
        rows = self.connection.execute(
            """
            SELECT snapshot_path
            FROM detection_logs
            WHERE snapshot_path IS NOT NULL
            """
        ).fetchall()
        snapshot_paths = {
            str(row["snapshot_path"])
            for row in rows
            if row["snapshot_path"]
        }
        cursor = self.connection.execute("DELETE FROM detection_logs")
        self.connection.commit()

        deleted_snapshots = sum(
            1
            for snapshot_path in snapshot_paths
            if self._delete_snapshot_if_unreferenced(snapshot_path)
        )
        return {
            "message": "Detection logs deleted",
            "deleted_count": int(cursor.rowcount),
            "deleted_snapshots": deleted_snapshots,
        }

    def _snapshot_is_referenced(self, snapshot_path: str) -> bool:
        log_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM detection_logs
            WHERE snapshot_path = ?
            """,
            (snapshot_path,),
        ).fetchone()[0]
        alert_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM alerts
            WHERE snapshot_path = ?
            """,
            (snapshot_path,),
        ).fetchone()[0]
        return int(log_count) > 0 or int(alert_count) > 0

    def _delete_snapshot_if_unreferenced(self, snapshot_path: str) -> bool:
        if self._snapshot_is_referenced(snapshot_path):
            return False
        path = resolve_storage_path(snapshot_path)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                return True
        except OSError:
            return False
        return False
