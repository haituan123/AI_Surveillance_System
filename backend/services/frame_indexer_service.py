import json
import sqlite3
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.ai.attribute_extractor import AttributeExtractor
from backend.ai.contracts import FrameAnalysis
from backend.ai.threat_detector import ThreatAndObjectDetector
from backend.app.config import SNAPSHOTS_DIR, serialize_storage_path
from backend.app.models import EntityType, ThreatType


class FrameIndexerService:
    """Indexes video frames, entity attributes, and danger threats into SQLite for fast Video QA."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        snapshots_dir: Path = SNAPSHOTS_DIR,
    ) -> None:
        self.connection = connection
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.attribute_extractor = AttributeExtractor()
        self.threat_detector = ThreatAndObjectDetector()

    def index_frame(
        self,
        frame_bgr: np.ndarray,
        *,
        camera_id: int | None = None,
        session_or_video_id: str,
        timestamp_seconds: float,
        frame_number: int,
        analysis: FrameAnalysis,
        raw_object_detections: list[dict[str, Any]] | None = None,
        scene_caption_en: str | None = None,
    ) -> int:
        """Indexes one frame, its people, objects, and any detected threats."""
        person_boxes = [track.bounding_box for track in analysis.tracks]
        detected_objects, threat_events = self.threat_detector.evaluate_detections(
            raw_object_detections or [],
            person_boxes=person_boxes,
        )

        person_count = len(analysis.tracks)
        frame_snapshot_path = ""

        # Lưu ảnh snapshot nếu có người hoặc có threat
        if person_count > 0 or threat_events:
            snapshot_filename = f"frame_{session_or_video_id}_{frame_number}_{int(timestamp_seconds*1000)}.jpg"
            full_path = self.snapshots_dir / snapshot_filename
            cv2.imwrite(str(full_path), frame_bgr)
            frame_snapshot_path = serialize_storage_path(full_path)

        # 1. Insert video_frames
        cursor = self.connection.execute(
            """
            INSERT INTO video_frames (
                camera_id, session_or_video_id, timestamp_seconds,
                frame_number, frame_path, person_count, scene_caption_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                camera_id,
                session_or_video_id,
                timestamp_seconds,
                frame_number,
                frame_snapshot_path,
                person_count,
                scene_caption_en,
            ),
        )
        frame_id = int(cursor.lastrowid)

        # 2. Insert detected_entities for people (with colors and actions)
        for track in analysis.tracks:
            bbox = track.bounding_box
            attrs = self.attribute_extractor.analyze_person(
                frame_bgr=frame_bgr,
                track_id=track.track_id,
                x1=bbox.x1,
                y1=bbox.y1,
                x2=bbox.x2,
                y2=bbox.y2,
                timestamp_seconds=timestamp_seconds,
            )

            self.connection.execute(
                """
                INSERT INTO detected_entities (
                    frame_id, track_id, member_id, entity_type, label,
                    bbox_json, confidence, clothing_top_color,
                    clothing_bottom_color, movement_direction, action_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frame_id,
                    track.track_id,
                    track.member_id,
                    EntityType.PERSON,
                    "person",
                    json.dumps([bbox.x1, bbox.y1, bbox.x2, bbox.y2]),
                    track.person_confidence,
                    attrs.top_color,
                    attrs.bottom_color,
                    attrs.movement_direction,
                    attrs.action_label,
                ),
            )

        # 3. Insert detected_entities for objects (backpack, knife, phone)
        for obj in detected_objects:
            self.connection.execute(
                """
                INSERT INTO detected_entities (
                    frame_id, entity_type, label, bbox_json, confidence
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    frame_id,
                    obj.entity_type,
                    obj.label,
                    json.dumps([
                        obj.bounding_box.x1,
                        obj.bounding_box.y1,
                        obj.bounding_box.x2,
                        obj.bounding_box.y2,
                    ]),
                    obj.confidence,
                ),
            )

        # 4. Insert danger_threats if any
        for threat in threat_events:
            self.connection.execute(
                """
                INSERT INTO danger_threats (
                    frame_id, threat_type, confidence, snapshot_path, description_en
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    frame_id,
                    threat.threat_type,
                    threat.confidence,
                    frame_snapshot_path,
                    threat.description_en,
                ),
            )

        self.connection.commit()
        return frame_id

    def reset(self) -> None:
        self.attribute_extractor.movement_tracker.reset()
