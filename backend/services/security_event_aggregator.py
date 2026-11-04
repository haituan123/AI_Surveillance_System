import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from backend.ai.contracts import BoundingBox, FrameAnalysis


EVENT_TYPE_MAP = {
    "knife_threat": "knife_present",
    "weapon_drawn": "weapon_present",
    "fire_smoke": "fire_smoke",
    "theft": "possible_theft",
    "violence": "violence",
}


@dataclass
class _EventState:
    event_type: str
    detected_label: str
    start_timestamp: float
    last_seen_timestamp: float
    confirmations: int
    best_confidence: float
    best_frame_id: int
    best_snapshot_path: str
    best_bbox: list[int] | None
    camera_id: int | None
    actor_track_ids: set[int] = field(default_factory=set)
    descriptions: set[str] = field(default_factory=set)
    event_id: int | None = None


class SecurityEventAggregator:
    """Combines repeated frame-level threats into persistent video events."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        session_or_video_id: str,
        min_confirmations: int = 2,
        max_gap_seconds: float = 1.0,
        model_version: str = "rule-v1",
    ) -> None:
        self.connection = connection
        self.session_or_video_id = session_or_video_id
        self.min_confirmations = max(1, int(min_confirmations))
        self.max_gap_seconds = max(0.0, float(max_gap_seconds))
        self.model_version = model_version
        self._states: dict[tuple[str, str], _EventState] = {}

    def process_frame(
        self,
        *,
        frame_id: int,
        timestamp_seconds: float,
        analysis: FrameAnalysis,
    ) -> None:
        frame = self.connection.execute(
            """
            SELECT camera_id, frame_path
            FROM video_frames
            WHERE id = ?
            """,
            (frame_id,),
        ).fetchone()
        if frame is None:
            raise ValueError(f"Video frame {frame_id} not found")

        threat_rows = self.connection.execute(
            """
            SELECT threat_type, confidence, description_en, bbox_json
            FROM danger_threats
            WHERE frame_id = ?
            ORDER BY confidence DESC
            """,
            (frame_id,),
        ).fetchall()

        observations: dict[tuple[str, str], dict[str, Any]] = {}
        for row in threat_rows:
            raw_type = str(row["threat_type"])
            event_type = EVENT_TYPE_MAP.get(raw_type, raw_type)
            description = str(row["description_en"] or "")
            label = self._infer_label(raw_type, description)
            key = (event_type, label)
            bbox = self._parse_bbox(row["bbox_json"])
            observation = {
                "event_type": event_type,
                "label": label,
                "confidence": float(row["confidence"]),
                "description": description,
                "bbox": bbox,
                "track_ids": self._related_track_ids(analysis, bbox),
            }
            previous = observations.get(key)
            if previous is None or observation["confidence"] > previous["confidence"]:
                observations[key] = observation

        observed_keys = set(observations)
        self._close_expired(timestamp_seconds, observed_keys)

        for key, observation in observations.items():
            state = self._states.get(key)
            if (
                state is None
                or timestamp_seconds - state.last_seen_timestamp
                > self.max_gap_seconds
            ):
                if state is not None:
                    self._close_state(state)
                state = _EventState(
                    event_type=observation["event_type"],
                    detected_label=observation["label"],
                    start_timestamp=timestamp_seconds,
                    last_seen_timestamp=timestamp_seconds,
                    confirmations=0,
                    best_confidence=-1.0,
                    best_frame_id=frame_id,
                    best_snapshot_path=str(frame["frame_path"] or ""),
                    best_bbox=observation["bbox"],
                    camera_id=frame["camera_id"],
                )
                self._states[key] = state

            state.confirmations += 1
            state.last_seen_timestamp = timestamp_seconds
            state.actor_track_ids.update(observation["track_ids"])
            if observation["description"]:
                state.descriptions.add(observation["description"])
            if observation["confidence"] > state.best_confidence:
                state.best_confidence = observation["confidence"]
                state.best_frame_id = frame_id
                state.best_snapshot_path = str(frame["frame_path"] or "")
                state.best_bbox = observation["bbox"]

            if state.event_id is None and state.confirmations >= self.min_confirmations:
                state.event_id = self._insert_state(state)
            elif state.event_id is not None:
                self._update_state(state)

        self.connection.commit()

    def flush(self) -> None:
        """Close all confirmed events when video processing finishes."""
        for state in self._states.values():
            self._close_state(state)
        self._states.clear()
        self.connection.commit()

    def _close_expired(
        self,
        timestamp_seconds: float,
        observed_keys: set[tuple[str, str]],
    ) -> None:
        expired = [
            key
            for key, state in self._states.items()
            if key not in observed_keys
            and timestamp_seconds - state.last_seen_timestamp
            > self.max_gap_seconds
        ]
        for key in expired:
            self._close_state(self._states.pop(key))

    def _insert_state(self, state: _EventState) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO security_events (
                session_or_video_id, camera_id, event_type,
                start_timestamp, end_timestamp, confidence,
                primary_frame_id, snapshot_path, actor_track_ids_json,
                object_labels_json, bbox_json, metadata_json,
                model_version, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', CURRENT_TIMESTAMP)
            """,
            self._state_values(state),
        )
        return int(cursor.lastrowid)

    def _update_state(self, state: _EventState) -> None:
        self.connection.execute(
            """
            UPDATE security_events
            SET camera_id = ?, end_timestamp = ?, confidence = ?,
                primary_frame_id = ?, snapshot_path = ?,
                actor_track_ids_json = ?, object_labels_json = ?,
                bbox_json = ?, metadata_json = ?, model_version = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                state.camera_id,
                state.last_seen_timestamp,
                state.best_confidence,
                state.best_frame_id,
                state.best_snapshot_path,
                json.dumps(sorted(state.actor_track_ids)),
                json.dumps([state.detected_label]),
                json.dumps(state.best_bbox) if state.best_bbox else None,
                self._metadata_json(state),
                self.model_version,
                state.event_id,
            ),
        )

    def _close_state(self, state: _EventState) -> None:
        if state.event_id is None:
            return
        self._update_state(state)
        self.connection.execute(
            """
            UPDATE security_events
            SET status = 'closed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (state.event_id,),
        )

    def _state_values(self, state: _EventState) -> tuple[Any, ...]:
        return (
            self.session_or_video_id,
            state.camera_id,
            state.event_type,
            state.start_timestamp,
            state.last_seen_timestamp,
            state.best_confidence,
            state.best_frame_id,
            state.best_snapshot_path,
            json.dumps(sorted(state.actor_track_ids)),
            json.dumps([state.detected_label]),
            json.dumps(state.best_bbox) if state.best_bbox else None,
            self._metadata_json(state),
            self.model_version,
        )

    def _metadata_json(self, state: _EventState) -> str:
        return json.dumps(
            {
                "confirmations": state.confirmations,
                "descriptions": sorted(state.descriptions),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _parse_bbox(raw_bbox: Any) -> list[int] | None:
        if not raw_bbox:
            return None
        try:
            parsed = json.loads(raw_bbox) if isinstance(raw_bbox, str) else raw_bbox
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, list) or len(parsed) != 4:
            return None
        return [int(value) for value in parsed]

    @staticmethod
    def _infer_label(threat_type: str, description: str) -> str:
        text = description.lower()
        if threat_type == "knife_threat":
            return "scissors" if "sharp" in text else "knife"
        if threat_type == "weapon_drawn":
            return "gun"
        if threat_type == "fire_smoke":
            return "smoke" if "smoke" in text else "fire"
        if threat_type == "theft":
            for label in ("backpack", "handbag", "cell phone", "laptop"):
                if label in text:
                    return label
            return "object"
        return threat_type

    @staticmethod
    def _related_track_ids(
        analysis: FrameAnalysis,
        bbox: list[int] | None,
    ) -> set[int]:
        if bbox is None:
            return set()
        event_box = BoundingBox(*bbox)
        related: set[int] = set()
        for track in analysis.tracks:
            person_box = track.bounding_box
            if (
                min(person_box.x2, event_box.x2)
                > max(person_box.x1, event_box.x1)
                and min(person_box.y2, event_box.y2)
                > max(person_box.y1, event_box.y1)
            ):
                related.add(track.track_id)
        return related
