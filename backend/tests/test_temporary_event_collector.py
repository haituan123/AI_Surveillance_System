import unittest

from backend.ai.contracts import (
    BoundingBox,
    FrameAnalysis,
    TrackAnalysis,
)
from backend.ai.threat_detector import ThreatEvent
from backend.app.models import DetectionStatus
from backend.app.models import ThreatType
from backend.services.temporary_event_collector import TemporaryEventCollector


def analysis(frame_index, timestamp, status, member_id=None, track_id=1):
    return FrameAnalysis(
        frame_index=frame_index,
        timestamp_seconds=timestamp,
        width=20,
        height=20,
        tracks=(
            TrackAnalysis(
                track_id=track_id,
                bounding_box=BoundingBox(1, 1, 10, 10),
                person_confidence=0.9,
                status=status,
                member_id=member_id,
                similarity=0.75 if member_id else 0.2,
                face_confidence=0.9,
            ),
        ),
    )


class TemporaryEventCollectorTestCase(unittest.TestCase):
    def test_knife_threat_has_confidence_bbox_and_is_deduplicated(self):
        collector = TemporaryEventCollector(
            member_names={},
            unknown_confirmation_frames=99,
            security_event_cooldown_seconds=3.0,
        )
        threat = ThreatEvent(
            threat_type=ThreatType.KNIFE_THREAT,
            confidence=0.88,
            description_en="Person detected holding a knife",
            bounding_box=BoundingBox(2, 3, 8, 12),
        )

        first = collector.process(
            analysis(0, 0.0, DetectionStatus.LOW_QUALITY),
            [threat],
        )
        duplicate = collector.process(
            analysis(1, 1.0, DetectionStatus.LOW_QUALITY),
            [threat],
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["event_type"], "knife_threat")
        self.assertEqual(first[0]["detected_label"], "knife")
        self.assertEqual(first[0]["confidence"], 0.88)
        self.assertEqual(first[0]["bounding_box"], [2, 3, 8, 12])
        self.assertTrue(first[0]["is_threat"])
        self.assertTrue(first[0]["event_id"])
        self.assertEqual(duplicate, [])
        self.assertEqual(collector.total_threat_events, 1)

    def test_known_event_is_deduplicated_and_named(self):
        collector = TemporaryEventCollector(
            member_names={7: "Known Member"},
            unknown_confirmation_frames=2,
        )

        first = collector.process(
            analysis(0, 0.0, DetectionStatus.KNOWN, 7)
        )
        duplicate = collector.process(
            analysis(1, 0.1, DetectionStatus.KNOWN, 7)
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["member_name"], "Known Member")
        self.assertEqual(duplicate, [])
        self.assertEqual(collector.total_known_events, 1)

    def test_known_member_is_not_counted_again_after_unknown_flip(self):
        collector = TemporaryEventCollector(
            member_names={7: "Known Member"},
            unknown_confirmation_frames=1,
        )

        first_unknown = collector.process(
            analysis(0, 0.0, DetectionStatus.UNKNOWN)
        )
        first_known = collector.process(
            analysis(1, 1.0, DetectionStatus.KNOWN, 7)
        )
        repeated_unknown = collector.process(
            analysis(2, 2.0, DetectionStatus.UNKNOWN)
        )
        repeated_known = collector.process(
            analysis(3, 3.0, DetectionStatus.KNOWN, 7)
        )

        self.assertEqual(len(first_unknown), 1)
        self.assertEqual(len(first_known), 1)
        self.assertEqual(repeated_unknown, [])
        self.assertEqual(repeated_known, [])
        self.assertEqual([event["status"] for event in collector.events], [
            DetectionStatus.KNOWN,
        ])
        self.assertEqual(collector.total_known_events, 1)
        self.assertEqual(collector.total_unknown_events, 0)

    def test_known_summary_counts_unique_registered_identities(self):
        collector = TemporaryEventCollector(
            member_names={7: "Known Member", 8: "Other Member"},
            unknown_confirmation_frames=1,
        )

        first_track = collector.process(
            analysis(0, 0.0, DetectionStatus.KNOWN, 7, track_id=1)
        )
        same_member_new_track = collector.process(
            analysis(1, 1.0, DetectionStatus.KNOWN, 7, track_id=2)
        )
        different_member = collector.process(
            analysis(2, 2.0, DetectionStatus.KNOWN, 8, track_id=3)
        )

        self.assertEqual(len(first_track), 1)
        self.assertEqual(len(same_member_new_track), 1)
        self.assertEqual(len(different_member), 1)
        self.assertEqual(collector.total_known_events, 2)

    def test_unknown_confirmation_alerts_once_per_visible_track(self):
        collector = TemporaryEventCollector(
            member_names={},
            unknown_confirmation_frames=2,
            unknown_cooldown_seconds=5,
        )

        self.assertEqual(
            collector.process(analysis(0, 0.0, DetectionStatus.UNKNOWN)),
            [],
        )
        first = collector.process(
            analysis(1, 1.0, DetectionStatus.UNKNOWN)
        )
        within_cooldown = collector.process(
            analysis(2, 3.0, DetectionStatus.UNKNOWN)
        )
        repeated_after_cooldown = collector.process(
            analysis(3, 6.0, DetectionStatus.UNKNOWN)
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["event_type"], "unknown_person")
        self.assertEqual(within_cooldown, [])
        self.assertEqual(repeated_after_cooldown, [])
        self.assertEqual(collector.total_unknown_events, 1)

    def test_unknown_track_can_emit_again_after_it_disappears(self):
        collector = TemporaryEventCollector(
            member_names={},
            unknown_confirmation_frames=1,
            unknown_cooldown_seconds=3,
        )

        first = collector.process(
            analysis(0, 0.0, DetectionStatus.UNKNOWN)
        )
        collector.process(
            FrameAnalysis(
                frame_index=1,
                timestamp_seconds=1.0,
                width=20,
                height=20,
                tracks=(),
            )
        )
        second = collector.process(
            analysis(2, 4.0, DetectionStatus.UNKNOWN)
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(collector.total_unknown_events, 2)

    def test_event_list_is_unbounded_by_default(self):
        collector = TemporaryEventCollector(
            member_names={},
            unknown_confirmation_frames=1,
            unknown_cooldown_seconds=0,
        )

        for index in range(4):
            collector.process(
                analysis(
                    index,
                    float(index),
                    DetectionStatus.UNKNOWN,
                    track_id=index + 1,
                )
            )

        self.assertEqual(len(collector.events), 4)
        self.assertFalse(collector.events_truncated)
        self.assertEqual(collector.total_unknown_events, 4)

    def test_event_list_can_be_bounded_with_explicit_limit(self):
        collector = TemporaryEventCollector(
            member_names={},
            unknown_confirmation_frames=1,
            unknown_cooldown_seconds=0,
            max_events=2,
        )

        for index in range(4):
            collector.process(
                analysis(
                    index,
                    float(index),
                    DetectionStatus.UNKNOWN,
                    track_id=index + 1,
                )
            )

        self.assertEqual(len(collector.events), 2)
        self.assertTrue(collector.events_truncated)
        self.assertEqual(collector.total_unknown_events, 2)


if __name__ == "__main__":
    unittest.main()
