from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.ai.contracts import BoundingBox
from backend.app.models import EntityType, ThreatType


@dataclass(frozen=True)
class DetectedObject:
    label: str
    entity_type: EntityType
    bounding_box: BoundingBox
    confidence: float


@dataclass(frozen=True)
class ThreatEvent:
    threat_type: ThreatType
    confidence: float
    description_en: str
    bounding_box: BoundingBox | None = None


# COCO / Object Detection class mapping for CCTV threats & objects
THREAT_CLASS_MAP = {
    # Weapons & Violence
    "knife": (ThreatType.KNIFE_THREAT, EntityType.WEAPON, "Person detected holding a knife"),
    "scissors": (ThreatType.KNIFE_THREAT, EntityType.WEAPON, "Sharp object detected"),
    "gun": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Firearm detected"),
    # Fire & Smoke
    "fire": (ThreatType.FIRE_SMOKE, EntityType.OBJECT, "Fire hazard detected"),
    "smoke": (ThreatType.FIRE_SMOKE, EntityType.OBJECT, "Smoke detected"),
}

SURVEILLANCE_OBJECT_CLASSES = {
    # Bags & Luggage
    "backpack": EntityType.OBJECT,
    "handbag": EntityType.OBJECT,
    "suitcase": EntityType.OBJECT,
    "bag": EntityType.OBJECT,
    # Electronics
    "cell phone": EntityType.OBJECT,
    "phone": EntityType.OBJECT,
    "laptop": EntityType.OBJECT,
    # Headwear & Accessories (SurveillanceVQA)
    "hat": EntityType.OBJECT,
    "cap": EntityType.OBJECT,
    "helmet": EntityType.OBJECT,
    "umbrella": EntityType.OBJECT,
    # Food & Drinks
    "food": EntityType.OBJECT,
    "bottle": EntityType.OBJECT,
    "cup": EntityType.OBJECT,
    "bowl": EntityType.OBJECT,
    "sandwich": EntityType.OBJECT,
    "pizza": EntityType.OBJECT,
    "cake": EntityType.OBJECT,
    "apple": EntityType.OBJECT,
    "banana": EntityType.OBJECT,
    # Common Furniture & Objects
    "chair": EntityType.OBJECT,
    "book": EntityType.OBJECT,
}


class ThreatAndObjectDetector:
    """Detects security threats (weapons, fire) and tracked surveillance objects (backpacks, phones)."""

    def __init__(self, confidence_threshold: float = 0.35) -> None:
        self.confidence_threshold = confidence_threshold

    def evaluate_detections(
        self,
        raw_detections: list[dict[str, Any]],
        person_boxes: list[BoundingBox] | None = None,
    ) -> tuple[list[DetectedObject], list[ThreatEvent]]:
        detected_objects: list[DetectedObject] = []
        threat_events: list[ThreatEvent] = []

        for det in raw_detections:
            label = str(det.get("label", "")).lower()
            conf = float(det.get("confidence", 0.0))
            if conf < self.confidence_threshold:
                continue

            bbox = BoundingBox(
                x1=int(det["x1"]),
                y1=int(det["y1"]),
                x2=int(det["x2"]),
                y2=int(det["y2"]),
            )

            # Check if it's a security threat
            if label in THREAT_CLASS_MAP:
                threat_type, ent_type, desc = THREAT_CLASS_MAP[label]
                detected_objects.append(
                    DetectedObject(
                        label=label,
                        entity_type=ent_type,
                        bounding_box=bbox,
                        confidence=conf,
                    )
                )
                threat_events.append(
                    ThreatEvent(
                        threat_type=threat_type,
                        confidence=conf,
                        description_en=desc,
                        bounding_box=bbox,
                    )
                )
            elif label in SURVEILLANCE_OBJECT_CLASSES:
                ent_type = SURVEILLANCE_OBJECT_CLASSES[label]
                detected_objects.append(
                    DetectedObject(
                        label=label,
                        entity_type=ent_type,
                        bounding_box=bbox,
                        confidence=conf,
                    )
                )

        # Check interaction: Person touching/taking object (Theft heuristic)
        if person_boxes:
            for obj in detected_objects:
                if obj.label in ["backpack", "handbag", "cell phone", "laptop"]:
                    for pbox in person_boxes:
                        if self._is_interacting(pbox, obj.bounding_box):
                            threat_events.append(
                                ThreatEvent(
                                    threat_type=ThreatType.THEFT,
                                    confidence=0.75,
                                    description_en=f"Possible object taking interaction with {obj.label}",
                                    bounding_box=pbox,
                                )
                            )
                            break

        return detected_objects, threat_events

    @staticmethod
    def _is_interacting(person_box: BoundingBox, object_box: BoundingBox) -> bool:
        """Determines if a person bounding box overlaps significantly with an object."""
        ix1 = max(person_box.x1, object_box.x1)
        iy1 = max(person_box.y1, object_box.y1)
        ix2 = min(person_box.x2, object_box.x2)
        iy2 = min(person_box.y2, object_box.y2)

        if ix2 <= ix1 or iy2 <= iy1:
            return False

        inter_area = (ix2 - ix1) * (iy2 - iy1)
        obj_area = (object_box.x2 - object_box.x1) * (object_box.y2 - object_box.y1)
        if obj_area <= 0:
            return False

        overlap_ratio = inter_area / float(obj_area)
        return overlap_ratio > 0.40
