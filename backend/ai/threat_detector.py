from dataclasses import dataclass
from typing import Any

import cv2
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
    "dagger": (ThreatType.KNIFE_THREAT, EntityType.WEAPON, "Dagger detected"),
    "machete": (ThreatType.KNIFE_THREAT, EntityType.WEAPON, "Machete detected"),
    "sword": (ThreatType.KNIFE_THREAT, EntityType.WEAPON, "Sword/Blade detected"),
    "gun": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Firearm detected"),
    "pistol": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Pistol detected"),
    "rifle": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Rifle detected"),
    "firearm": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Firearm detected"),
    "handgun": (ThreatType.WEAPON_DRAWN, EntityType.WEAPON, "Handgun detected"),
    # Fire & Smoke
    "fire": (ThreatType.FIRE_SMOKE, EntityType.OBJECT, "Fire hazard detected"),
    "smoke": (ThreatType.FIRE_SMOKE, EntityType.OBJECT, "Smoke detected"),
}

SURVEILLANCE_OBJECT_CLASSES = {
    # Vehicles (for snatching/theft tracking)
    "motorcycle": EntityType.OBJECT,
    "motorbike": EntityType.OBJECT,
    "bicycle": EntityType.OBJECT,
    "bike": EntityType.OBJECT,
    "scooter": EntityType.OBJECT,
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
    "glasses": EntityType.OBJECT,
    "eyeglasses": EntityType.OBJECT,
    "sunglasses": EntityType.OBJECT,
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
    "drink": EntityType.OBJECT,
    "beverage": EntityType.OBJECT,
    "snack": EntityType.OBJECT,
    "bread": EntityType.OBJECT,
    "hamburger": EntityType.OBJECT,
    "fruit": EntityType.OBJECT,
    # Common Furniture & Objects
    "chair": EntityType.OBJECT,
    "book": EntityType.OBJECT,
}


class ThreatAndObjectDetector:
    """Detects security threats (weapons, fire) and tracked surveillance objects (backpacks, phones)."""

    def __init__(self, confidence_threshold: float = 0.25) -> None:
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def detect_flame_regions(
        frame_bgr: np.ndarray,
        min_area: int = 120,
    ) -> list[tuple[BoundingBox, float]]:
        """Detects active fire/flame regions using combined RGB and HSV color space analysis."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        # 1. RGB condition: Intense red component (R > G > B and R > 165)
        b, g, r = cv2.split(frame_bgr)
        rgb_mask = (r > 165) & (r > g) & (g > b)

        # 2. HSV condition: Hue in red-to-yellow range, strong saturation & high luminance
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        hsv_mask = ((h <= 28) | (h >= 165)) & (s >= 40) & (v >= 150)

        combined = (rgb_mask & hsv_mask).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        filtered = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(filtered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        flames: list[tuple[BoundingBox, float]] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= min_area:
                x, y, w, h_box = cv2.boundingRect(cnt)
                bbox = BoundingBox(x1=x, y1=y, x2=x + w, y2=y + h_box)
                conf = min(0.95, 0.72 + min(0.23, area / 2000.0))
                flames.append((bbox, round(conf, 2)))
        return flames

    def evaluate_detections(
        self,
        raw_detections: list[dict[str, Any]],
        person_boxes: list[BoundingBox] | None = None,
        frame_bgr: np.ndarray | None = None,
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

        # Visual fire detection fallback if no model detected fire directly
        if frame_bgr is not None and not any(o.label == "fire" for o in detected_objects):
            for flame_box, flame_conf in self.detect_flame_regions(frame_bgr):
                detected_objects.append(
                    DetectedObject(
                        label="fire",
                        entity_type=EntityType.OBJECT,
                        bounding_box=flame_box,
                        confidence=flame_conf,
                    )
                )
                threat_events.append(
                    ThreatEvent(
                        threat_type=ThreatType.FIRE_SMOKE,
                        confidence=flame_conf,
                        description_en="Fire hazard detected via visual flame analysis",
                        bounding_box=flame_box,
                    )
                )

        # Check interaction: Person touching/taking object (Theft / Robbery heuristic)
        if person_boxes:
            for obj in detected_objects:
                if obj.label in [
                    "backpack", "handbag", "bag", "suitcase",
                    "cell phone", "phone", "laptop",
                    "motorcycle", "motorbike", "bicycle", "bike", "scooter"
                ]:


                    for pbox in person_boxes:
                        if self._is_interacting(pbox, obj.bounding_box, label=obj.label):
                            if obj.label in ["backpack", "handbag", "bag", "suitcase"]:
                                specific_threat = ThreatType.ROBBERY_BACKPACK
                            elif obj.label in ["cell phone", "phone", "laptop"]:
                                specific_threat = ThreatType.ROBBERY_PHONE
                            elif obj.label in ["motorcycle", "motorbike", "bicycle", "bike", "scooter"]:
                                specific_threat = ThreatType.ROBBERY_MOTORBIKE
                            else:
                                specific_threat = ThreatType.THEFT

                            conf = round(float(obj.confidence), 2)
                            threat_events.append(
                                ThreatEvent(
                                    threat_type=ThreatType.THEFT,
                                    confidence=conf,
                                    description_en=f"Possible object taking interaction with {obj.label}",
                                    bounding_box=pbox,
                                )
                            )
                            if specific_threat != ThreatType.THEFT:
                                threat_events.append(
                                    ThreatEvent(
                                        threat_type=specific_threat,
                                        confidence=conf,
                                        description_en=f"Possible {specific_threat.value} with {obj.label}",
                                        bounding_box=pbox,
                                    )
                                )
                            break

        return detected_objects, threat_events

    @staticmethod
    def _is_interacting(person_box: BoundingBox, object_box: BoundingBox, label: str = "") -> bool:
        """Determines if a person bounding box overlaps or is in close interaction with an object."""
        ix1 = max(person_box.x1, object_box.x1)
        iy1 = max(person_box.y1, object_box.y1)
        ix2 = min(person_box.x2, object_box.x2)
        iy2 = min(person_box.y2, object_box.y2)

        inter_area = 0
        if ix2 > ix1 and iy2 > iy1:
            inter_area = (ix2 - ix1) * (iy2 - iy1)

        obj_area = max(1, (object_box.x2 - object_box.x1) * (object_box.y2 - object_box.y1))
        overlap_ratio = inter_area / float(obj_area)

        # Vehicles: Large objects, person standing/sitting by bike has 15-20% overlap or close proximity
        if any(v in label.lower() for v in ["motorcycle", "motorbike", "bicycle", "bike", "scooter"]):
            if overlap_ratio >= 0.15:
                return True
            pcx = (person_box.x1 + person_box.x2) / 2.0
            pcy = (person_box.y1 + person_box.y2) / 2.0
            ocx = (object_box.x1 + object_box.x2) / 2.0
            ocy = (object_box.y1 + object_box.y2) / 2.0
            max_dist = max(object_box.x2 - object_box.x1, object_box.y2 - object_box.y1) * 0.8
            if ((pcx - ocx)**2 + (pcy - ocy)**2)**0.5 <= max_dist:
                return True
            return False

        # Accessories / Phones / Backpacks: Require significant overlap (>0.35)
        return overlap_ratio > 0.35


def annotate_threat_events(
    frame_bgr: np.ndarray,
    threat_events: list[ThreatEvent],
) -> np.ndarray:
    annotated = frame_bgr.copy()
    for threat in threat_events:
        box = threat.bounding_box
        if box is None:
            continue
        label = f"{threat.threat_type.value} {threat.confidence:.2f}"
        cv2.rectangle(
            annotated,
            (box.x1, box.y1),
            (box.x2, box.y2),
            (0, 0, 255),
            3,
        )
        cv2.putText(
            annotated,
            label,
            (box.x1, max(20, box.y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return annotated
