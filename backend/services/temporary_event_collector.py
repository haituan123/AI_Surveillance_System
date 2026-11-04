from dataclasses import dataclass, field
from uuid import uuid4

from backend.ai.contracts import FrameAnalysis
from backend.ai.threat_detector import ThreatEvent
from backend.app.config import (
    ALERT_COOLDOWN_SECONDS,
    UNKNOWN_CONFIRMATION_FRAMES,
    VIDEO_ANALYSIS_MAX_EVENTS,
)
from backend.app.models import DetectionStatus


@dataclass
class _TemporaryTrackState:
    unknown_streak: int = 0
    last_log_key: tuple[str, int | None] | None = None
    last_unknown_event_at: float | None = None
    last_seen_at: float | None = None
    unknown_event_recorded: bool = False
    recorded_member_ids: set[int] = field(default_factory=set)
    unknown_event: dict | None = None


class TemporaryEventCollector:
    def __init__(
        self,
        *,
        member_names: dict[int, str],
        unknown_confirmation_frames: int = UNKNOWN_CONFIRMATION_FRAMES,
        unknown_cooldown_seconds: float = ALERT_COOLDOWN_SECONDS,
        max_events: int = VIDEO_ANALYSIS_MAX_EVENTS,
        security_event_cooldown_seconds: float = 3.0,
    ) -> None:
        if unknown_confirmation_frames <= 0:
            raise ValueError("Unknown confirmation frames must be positive")
        if unknown_cooldown_seconds < 0:
            raise ValueError("Unknown cooldown cannot be negative")
        if max_events < 0:
            raise ValueError(
                "Maximum temporary events cannot be negative"
            )
        self.member_names = member_names
        self.unknown_confirmation_frames = unknown_confirmation_frames
        self.unknown_cooldown_seconds = unknown_cooldown_seconds
        self.track_state_ttl_seconds = max(unknown_cooldown_seconds, 1.0)
        self.max_events = max_events
        self.security_event_cooldown_seconds = security_event_cooldown_seconds
        self.events: list[dict] = []
        self.known_member_ids: set[int] = set()
        self.events_truncated = False
        self._track_states: dict[int, _TemporaryTrackState] = {}
        self._last_security_event_at: dict[str, float] = {}

    @property
    def total_known_events(self) -> int:
        return len(self.known_member_ids)

    @property
    def total_unknown_events(self) -> int:
        return sum(
            1
            for event in self.events
            if event["status"] is DetectionStatus.UNKNOWN
        )

    @property
    def total_threat_events(self) -> int:
        return sum(1 for event in self.events if event.get("is_threat"))

    def process(
        self,
        analysis: FrameAnalysis,
        threat_events: list[ThreatEvent] | None = None,
    ) -> list[dict]:
        new_events = []
        stale_track_ids = [
            track_id
            for track_id, state in self._track_states.items()
            if state.last_seen_at is not None
            and analysis.timestamp_seconds - state.last_seen_at
            >= self.track_state_ttl_seconds
        ]
        for track_id in stale_track_ids:
            self._track_states.pop(track_id, None)

        for track in analysis.tracks:
            state = self._track_states.setdefault(
                track.track_id,
                _TemporaryTrackState(),
            )
            state.last_seen_at = analysis.timestamp_seconds
            if (
                track.status is DetectionStatus.KNOWN
                and track.member_id is not None
            ):
                state.unknown_streak = 0
                key = (DetectionStatus.KNOWN.value, track.member_id)
                if track.member_id in state.recorded_member_ids:
                    continue
                state.last_log_key = key
                state.recorded_member_ids.add(track.member_id)
                self.known_member_ids.add(track.member_id)
                if state.unknown_event is not None:
                    self._remove_event(state.unknown_event)
                    state.unknown_event = None
                event = self._event(
                    analysis,
                    track.track_id,
                    DetectionStatus.KNOWN,
                    track.member_id,
                    track.similarity,
                    "detection",
                )
                new_events.append(event)
                continue

            if track.status is DetectionStatus.UNKNOWN:
                state.unknown_streak += 1
                if state.unknown_streak < self.unknown_confirmation_frames:
                    continue
                if state.unknown_event_recorded:
                    continue
                state.last_log_key = (DetectionStatus.UNKNOWN.value, None)
                state.last_unknown_event_at = analysis.timestamp_seconds
                state.unknown_event_recorded = True
                event = self._event(
                    analysis,
                    track.track_id,
                    DetectionStatus.UNKNOWN,
                    None,
                    track.similarity,
                    "unknown_person",
                )
                state.unknown_event = event
                new_events.append(event)

        for threat in threat_events or []:
            event_type = threat.threat_type.value
            last_event_at = self._last_security_event_at.get(event_type)
            if (
                last_event_at is not None
                and analysis.timestamp_seconds - last_event_at
                < self.security_event_cooldown_seconds
            ):
                continue
            self._last_security_event_at[event_type] = analysis.timestamp_seconds
            bbox = threat.bounding_box
            new_events.append(
                {
                    "event_id": uuid4().hex,
                    "frame_index": analysis.frame_index,
                    "timestamp_seconds": analysis.timestamp_seconds,
                    "track_id": None,
                    "status": None,
                    "member_id": None,
                    "member_name": None,
                    "similarity": None,
                    "event_type": event_type,
                    "detected_label": self._label_for_threat(threat),
                    "confidence": threat.confidence,
                    "bounding_box": (
                        [bbox.x1, bbox.y1, bbox.x2, bbox.y2]
                        if bbox is not None
                        else None
                    ),
                    "description": threat.description_en,
                    "is_threat": True,
                    "snapshot_url": None,
                }
            )

        self.events.extend(new_events)
        if self.max_events > 0 and len(self.events) > self.max_events:
            overflow = len(self.events) - self.max_events
            del self.events[:overflow]
            self.events_truncated = True
        return new_events

    def _remove_event(self, event: dict) -> None:
        try:
            self.events.remove(event)
        except ValueError:
            pass

    def _event(
        self,
        analysis: FrameAnalysis,
        track_id: int,
        status: DetectionStatus,
        member_id: int | None,
        similarity: float | None,
        event_type: str,
    ) -> dict:
        return {
            "frame_index": analysis.frame_index,
            "timestamp_seconds": analysis.timestamp_seconds,
            "track_id": track_id,
            "status": status,
            "member_id": member_id,
            "member_name": (
                self.member_names.get(member_id)
                if member_id is not None
                else None
            ),
            "similarity": similarity,
            "event_type": event_type,
            "event_id": None,
            "detected_label": None,
            "confidence": similarity,
            "bounding_box": None,
            "description": None,
            "is_threat": False,
            "snapshot_url": None,
        }

    @staticmethod
    def _label_for_threat(threat: ThreatEvent) -> str:
        description = threat.description_en.lower()
        if "knife" in description:
            return "knife"
        if "sharp" in description:
            return "scissors"
        if "firearm" in description:
            return "gun"
        if "fire" in description:
            return "fire"
        if "smoke" in description:
            return "smoke"
        if "with " in description:
            return description.rsplit("with ", 1)[-1]
        return threat.threat_type.value
