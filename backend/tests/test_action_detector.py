import unittest
import numpy as np

from backend.ai.action_detector import ActionResult, ActionVerifier
from backend.ai.contracts import BoundingBox
from backend.app.models import ThreatType, SecurityEventType


class ActionVerifierTestCase(unittest.TestCase):
    def setUp(self):
        self.verifier = ActionVerifier()

    def test_empty_frames_returns_normal(self):
        result = self.verifier.verify_clip([])
        self.assertEqual(result.action_type, "normal")
        self.assertFalse(result.is_suspicious)

    def test_static_frames_normal(self):
        frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        frames = [frame.copy() for _ in range(5)]
        result = self.verifier.verify_clip(frames)
        self.assertEqual(result.action_type, "normal")
        self.assertFalse(result.is_suspicious)

    def test_suspected_fighting_with_motion(self):
        # Frame 0: dark, Frame 4: bright (simulating sudden rapid movement/motion)
        frames = [
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 50, dtype=np.uint8),
            np.full((100, 100, 3), 100, dtype=np.uint8),
            np.full((100, 100, 3), 150, dtype=np.uint8),
            np.full((100, 100, 3), 200, dtype=np.uint8),
        ]
        box = BoundingBox(x1=10, y1=10, x2=80, y2=80)
        result = self.verifier.verify_clip(
            frames,
            interaction_box=box,
            suspected_action=ThreatType.FIGHTING,
        )
        self.assertEqual(result.action_type, SecurityEventType.FIGHTING)
        self.assertTrue(result.is_suspicious)
        self.assertGreaterEqual(result.confidence, 0.65)
        self.assertEqual(result.bounding_box, box)

    def test_suspected_shooting(self):
        frames = [
            np.zeros((80, 80, 3), dtype=np.uint8),
            np.full((80, 80, 3), 150, dtype=np.uint8),
        ]
        result = self.verifier.verify_clip(
            frames,
            suspected_action=ThreatType.SHOOTING,
        )
        self.assertEqual(result.action_type, SecurityEventType.SHOOTING)
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.confidence, 0.60)

    def test_suspected_robbery_backpack(self):
        frames = [
            np.zeros((80, 80, 3), dtype=np.uint8),
            np.full((80, 80, 3), 100, dtype=np.uint8),
        ]
        result = self.verifier.verify_clip(
            frames,
            suspected_action=ThreatType.ROBBERY_BACKPACK,
        )
        self.assertEqual(result.action_type, ThreatType.ROBBERY_BACKPACK)
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.confidence, 0.60)


if __name__ == "__main__":
    unittest.main()

