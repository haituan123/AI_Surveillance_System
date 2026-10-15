import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from backend.ai.contracts import FrameAnalysis, TrackAnalysis
from backend.ai.threat_detector import ThreatAndObjectDetector
from backend.app.config import (
    ALERT_COOLDOWN_SECONDS,
    RESTRICTED_ZONE_ALERT_COOLDOWN_SECONDS,
    RESTRICTED_ZONE_DWELL_SECONDS,
    SNAPSHOTS_DIR,
    UNKNOWN_CONFIRMATION_FRAMES,
    serialize_storage_path,
)
from backend.app.models import AlertType, DetectionStatus
from backend.services.zone_service import RestrictedZone


@dataclass
class _ZoneDwellState:
    entered_at: float
    last_alert_at: float | None = None
    alert_recorded: bool = False


@dataclass
class _TrackEventState:
    unknown_streak: int = 0
    last_log_key: tuple[str, int | None] | None = None
    last_alert_at: float | None = None
    last_seen_at: float | None = None
    unknown_alert_recorded: bool = False
    zone_dwell: dict[int, _ZoneDwellState] | None = None


@dataclass(frozen=True)
class PersistedAlertEvent:
    alert_id: int
    detection_log_id: int
    track_id: int
    snapshot_path: str
    alert_type: AlertType = AlertType.UNKNOWN_PERSON


class LiveEventRecorder:
    """Persist selected events from live mode only."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: int,
        camera_id: int,
        snapshots_dir: Path = SNAPSHOTS_DIR,
        unknown_confirmation_frames: int = UNKNOWN_CONFIRMATION_FRAMES,
        alert_cooldown_seconds: float = ALERT_COOLDOWN_SECONDS,
        restricted_zones: list[RestrictedZone] | None = None,
        restricted_zone_dwell_seconds: float = RESTRICTED_ZONE_DWELL_SECONDS,
        restricted_zone_alert_cooldown_seconds: float = (
            RESTRICTED_ZONE_ALERT_COOLDOWN_SECONDS
        ),
    ) -> None:
        if unknown_confirmation_frames <= 0:
            raise ValueError("Unknown confirmation frames must be positive")
        if alert_cooldown_seconds < 0:
            raise ValueError("Alert cooldown cannot be negative")
        if restricted_zone_dwell_seconds < 0:
            raise ValueError("Restricted-zone dwell time cannot be negative")
        if restricted_zone_alert_cooldown_seconds < 0:
            raise ValueError("Restricted-zone cooldown cannot be negative")
        self.connection = connection
        self.session_id = session_id
        self.camera_id = camera_id
        self.snapshots_dir = snapshots_dir
        self.unknown_confirmation_frames = unknown_confirmation_frames
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.restricted_zones = restricted_zones or []
        self.restricted_zone_dwell_seconds = restricted_zone_dwell_seconds
        self.restricted_zone_alert_cooldown_seconds = (
            restricted_zone_alert_cooldown_seconds
        )
        self.track_state_ttl_seconds = max(alert_cooldown_seconds, 1.0)
        self._track_states: dict[int, _TrackEventState] = {}

    def process(
        self,
        analysis: FrameAnalysis,
        annotated_frame_jpeg: bytes,
    ) -> list[PersistedAlertEvent]:
        pending_logs: list[TrackAnalysis] = []
        pending_alerts: list[tuple[TrackAnalysis, AlertType, str]] = []
        stale_track_ids = [
            track_id
            for track_id, state in self._track_states.items()
            if state.last_seen_at is not None
            and analysis.timestamp_seconds - state.last_seen_at
            >= self.track_state_ttl_seconds
        ]
        for track_id in stale_track_ids:
            self._track_states.pop(track_id, None)

        visible_track_ids = {track.track_id for track in analysis.tracks}
        for track_id, state in self._track_states.items():
            if track_id not in visible_track_ids:
                state.zone_dwell = None

        for track in analysis.tracks:
            state = self._track_states.setdefault(
                track.track_id,
                _TrackEventState(),
            )
            state.last_seen_at = analysis.timestamp_seconds
            if (
                track.status is DetectionStatus.KNOWN
                and track.member_id is not None
            ):
                state.unknown_streak = 0
                state.unknown_alert_recorded = False
                state.zone_dwell = None
                key = (DetectionStatus.KNOWN.value, track.member_id)
                if state.last_log_key != key:
                    pending_logs.append(track)
                continue

            if track.status is DetectionStatus.UNKNOWN:
                state.unknown_streak += 1
                if state.unknown_streak < self.unknown_confirmation_frames:
                    state.zone_dwell = None
                    continue
                if state.unknown_alert_recorded:
                    self._collect_restricted_zone_alerts(
                        analysis,
                        track,
                        state,
                        pending_logs,
                        pending_alerts,
                    )
                    continue
                if self._unknown_alert_due(state, analysis.timestamp_seconds):
                    pending_logs.append(track)
                    pending_alerts.append(
                        (
                            track,
                            AlertType.UNKNOWN_PERSON,
                            "Unknown person detected",
                        )
                    )
                self._collect_restricted_zone_alerts(
                    analysis,
                    track,
                    state,
                    pending_logs,
                    pending_alerts,
                )
            else:
                state.zone_dwell = None

        if not pending_logs:
            return []

        snapshot_path = None
        if pending_alerts:
            snapshot_path = self._save_snapshot(
                annotated_frame_jpeg,
                analysis,
            )

        persisted_alerts: list[PersistedAlertEvent] = []
        detected_at = datetime.now(timezone.utc).isoformat()
        try:
            for track in pending_logs:
                track_alerts = [
                    alert
                    for alert in pending_alerts
                    if alert[0] is track
                ]
                if not track_alerts:
                    self._insert_detection_log(track, None, detected_at)
                    continue

                if snapshot_path is None:
                    continue

                for _, alert_type, message in track_alerts:
                    detection_log_id = self._insert_detection_log(
                        track,
                        snapshot_path,
                        detected_at,
                    )
                    alert_cursor = self.connection.execute(
                        """
                        INSERT INTO alerts (
                            session_id,
                            camera_id,
                            detection_log_id,
                            member_id,
                            alert_type,
                            message,
                            confidence,
                            snapshot_path,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.session_id,
                            self.camera_id,
                            detection_log_id,
                            None,
                            alert_type.value,
                            message,
                            track.similarity,
                            snapshot_path,
                            detected_at,
                        ),
                    )
                    persisted_alerts.append(
                        PersistedAlertEvent(
                            alert_id=int(alert_cursor.lastrowid),
                            detection_log_id=detection_log_id,
                            track_id=track.track_id,
                            snapshot_path=snapshot_path,
                            alert_type=alert_type,
                        )
                    )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            if snapshot_path is not None:
                self._delete_snapshot(snapshot_path)
            raise

        for track in pending_logs:
            state = self._track_states[track.track_id]
            state.last_log_key = (track.status.value, track.member_id)
            track_alert_types = {
                alert_type
                for pending_track, alert_type, _ in pending_alerts
                if pending_track is track
            }
            if AlertType.UNKNOWN_PERSON in track_alert_types:
                state.last_alert_at = analysis.timestamp_seconds
                state.unknown_alert_recorded = True
        return persisted_alerts

    def _insert_detection_log(
        self,
        track: TrackAnalysis,
        snapshot_path: str | None,
        detected_at: str,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                member_id,
                track_id,
                status,
                confidence,
                snapshot_path,
                detected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.session_id,
                self.camera_id,
                track.member_id,
                track.track_id,
                track.status.value,
                track.similarity,
                snapshot_path,
                detected_at,
            ),
        )
        return int(cursor.lastrowid)

    def _unknown_alert_due(
        self,
        state: _TrackEventState,
        timestamp_seconds: float,
    ) -> bool:
        return (
            state.last_alert_at is None
            or timestamp_seconds - state.last_alert_at
            >= self.alert_cooldown_seconds
        )

    def _collect_restricted_zone_alerts(
        self,
        analysis: FrameAnalysis,
        track: TrackAnalysis,
        state: _TrackEventState,
        pending_logs: list[TrackAnalysis],
        pending_alerts: list[tuple[TrackAnalysis, AlertType, str]],
    ) -> None:
        if not self.restricted_zones:
            return

        state.zone_dwell = state.zone_dwell or {}
        timestamp = analysis.timestamp_seconds
        active_zone_ids: set[int] = set()
        for zone in self.restricted_zones:
            if not self._track_overlaps_zone(track, zone):
                continue
            active_zone_ids.add(zone.id)
            dwell = state.zone_dwell.setdefault(
                zone.id,
                _ZoneDwellState(entered_at=timestamp),
            )
            dwell_time = timestamp - dwell.entered_at
            if dwell_time < self.restricted_zone_dwell_seconds:
                continue
            if dwell.alert_recorded:
                continue
            if (
                dwell.last_alert_at is not None
                and timestamp - dwell.last_alert_at
                < self.restricted_zone_alert_cooldown_seconds
            ):
                continue
            if track not in pending_logs:
                pending_logs.append(track)
            
            # Phân biệt cảnh báo vùng cấm (Restricted Area) và Lảng vảng lâu (Loitering)
            alert_type = AlertType.LOITERING if dwell_time >= (self.restricted_zone_dwell_seconds * 1.5) else AlertType.RESTRICTED_AREA
            msg = f"Phát hiện người lảng vảng tại {zone.name} ({dwell_time:.1f}s)" if alert_type is AlertType.LOITERING else f"Phát hiện người trong khu vực {zone.name}"

            pending_alerts.append(
                (
                    track,
                    alert_type,
                    msg,
                )
            )
            dwell.last_alert_at = timestamp
            dwell.alert_recorded = True

        for zone_id in list(state.zone_dwell):
            if zone_id not in active_zone_ids:
                state.zone_dwell.pop(zone_id, None)

    @staticmethod
    def _track_overlaps_zone(track: TrackAnalysis, zone: RestrictedZone) -> bool:
        box = track.bounding_box
        x_values = (
            box.x1,
            (box.x1 + box.x2) // 2,
            box.x2,
        )
        y_values = (
            box.y1,
            (box.y1 + box.y2) // 2,
            box.y2,
        )
        sample_points = tuple((x, y) for x in x_values for y in y_values)
        if any(
            LiveEventRecorder._point_in_zone(point, zone)
            for point in sample_points
        ):
            return True

        return any(
            box.x1 <= point.x <= box.x2 and box.y1 <= point.y <= box.y2
            for point in zone.points
        )

    @staticmethod
    def _point_in_zone(point: tuple[int, int], zone: RestrictedZone) -> bool:
        contour = np.array(
            [[zone_point.x, zone_point.y] for zone_point in zone.points],
            dtype=np.int32,
        )
        return cv2.pointPolygonTest(contour, point, False) >= 0

    def _save_snapshot(
        self,
        content: bytes,
        analysis: FrameAnalysis,
    ) -> str:
        if not content:
            raise ValueError("Annotated snapshot cannot be empty")
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        filename = (
            f"session_{self.session_id}_frame_{analysis.frame_index}_"
            f"{timestamp}_{uuid4().hex}.jpg"
        )
        target = self.snapshots_dir / filename
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return serialize_storage_path(target)

    @staticmethod
    def _delete_snapshot(stored_path: str) -> None:
        from backend.app.config import resolve_storage_path

        path = resolve_storage_path(stored_path)
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass
