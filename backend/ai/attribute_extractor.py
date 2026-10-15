import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

COLOR_PALETTE = {
    "red": (np.array([0, 70, 50]), np.array([10, 255, 255])),
    "red_alt": (np.array([170, 70, 50]), np.array([180, 255, 255])),
    "pink": (np.array([145, 50, 150]), np.array([170, 255, 255])),
    "purple": (np.array([125, 50, 40]), np.array([150, 255, 255])),
    "blue": (np.array([90, 50, 50]), np.array([125, 255, 255])),
    "green": (np.array([35, 50, 50]), np.array([85, 255, 255])),
    "yellow": (np.array([21, 70, 70]), np.array([35, 255, 255])),
    "orange": (np.array([11, 70, 150]), np.array([20, 255, 255])),
    "brown": (np.array([6, 60, 20]), np.array([20, 255, 149])),
    "white": (np.array([0, 0, 180]), np.array([180, 40, 255])),
    "black": (np.array([0, 0, 0]), np.array([180, 255, 50])),
    "grey": (np.array([0, 0, 50]), np.array([180, 40, 180])),
}


@dataclass(frozen=True)
class PersonAttributes:
    top_color: str
    bottom_color: str
    movement_direction: str
    action_label: str
    speed_px_per_sec: float


class ColorAnalyzer:
    """Classifies dominant color of upper and lower body crops in HSV space."""

    @staticmethod
    def get_dominant_color(crop_bgr: np.ndarray) -> str:
        if crop_bgr is None or crop_bgr.size == 0:
            return "unknown"

        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        total_pixels = hsv.shape[0] * hsv.shape[1]
        if total_pixels == 0:
            return "unknown"

        color_scores: dict[str, int] = {}
        for color_name, (lower, upper) in COLOR_PALETTE.items():
            mask = cv2.inRange(hsv, lower, upper)
            count = int(cv2.countNonZero(mask))
            actual_name = "red" if color_name == "red_alt" else color_name
            color_scores[actual_name] = color_scores.get(actual_name, 0) + count

        best_color, best_count = max(color_scores.items(), key=lambda item: item[1])
        if best_count / total_pixels < 0.15:
            # Nếu không có màu nào chiếm ưu thế rõ ràng, phân loại theo độ sáng
            mean_v = float(np.mean(hsv[:, :, 2]))
            if mean_v < 60:
                return "black"
            if mean_v > 180:
                return "white"
            return "grey"

        return best_color

    @classmethod
    def extract_clothing_colors(cls, person_crop_bgr: np.ndarray) -> tuple[str, str]:
        if person_crop_bgr is None or person_crop_bgr.size == 0:
            return ("unknown", "unknown")

        h, w = person_crop_bgr.shape[:2]
        if h < 10 or w < 10:
            return ("unknown", "unknown")

        # Upper body (20% to 55% height to skip face/head and get shirt/torso)
        upper_start = int(h * 0.20)
        upper_end = int(h * 0.55)
        upper_crop = person_crop_bgr[upper_start:upper_end, :]

        # Lower body (55% to 90% height to get pants/skirt)
        lower_start = int(h * 0.55)
        lower_end = int(h * 0.90)
        lower_crop = person_crop_bgr[lower_start:lower_end, :]

        top_color = cls.get_dominant_color(upper_crop)
        bottom_color = cls.get_dominant_color(lower_crop)
        return top_color, bottom_color


class MovementTracker:
    """Tracks position trajectory per track_id to compute direction and action."""

    def __init__(self, history_size: int = 15) -> None:
        self.history_size = history_size
        # track_id -> list of (timestamp_seconds, center_x, center_y, box_w, box_h)
        self.tracks_history: dict[int, list[tuple[float, float, float, float, float]]] = {}

    def update(
        self,
        track_id: int,
        timestamp_seconds: float,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> tuple[str, str, float]:
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        bw = float(x2 - x1)
        bh = float(y2 - y1)

        history = self.tracks_history.setdefault(track_id, [])
        history.append((timestamp_seconds, cx, cy, bw, bh))
        if len(history) > self.history_size:
            history.pop(0)

        if len(history) < 2:
            return ("standing", "standing", 0.0)

        dt = history[-1][0] - history[0][0]
        if dt <= 0.01:
            return ("standing", "standing", 0.0)

        dx = history[-1][1] - history[0][1]
        dy = history[-1][2] - history[0][2]
        dist_px = math.sqrt(dx * dx + dy * dy)
        speed = dist_px / dt

        # Direction calculation
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        direction = "standing"

        if dist_px < 15:
            direction = "stationary"
            action = "standing"
        elif abs_dx >= abs_dy:
            direction = "left_to_right" if dx > 0 else "right_to_left"
            action = "running" if speed > 120 else "walking"
        else:
            direction = "towards_camera" if dy > 0 else "away_from_camera"
            action = "running" if speed > 120 else "walking"

        return direction, action, speed

    def reset(self) -> None:
        self.tracks_history.clear()


class AttributeExtractor:
    """Full attribute extractor for CCTV surveillance QA."""

    def __init__(self) -> None:
        self.color_analyzer = ColorAnalyzer()
        self.movement_tracker = MovementTracker()

    def analyze_person(
        self,
        frame_bgr: np.ndarray,
        track_id: int,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        timestamp_seconds: float,
    ) -> PersonAttributes:
        h, w = frame_bgr.shape[:2]
        clamped_x1 = max(0, min(x1, w))
        clamped_y1 = max(0, min(y1, h))
        clamped_x2 = max(0, min(x2, w))
        clamped_y2 = max(0, min(y2, h))

        crop = frame_bgr[clamped_y1:clamped_y2, clamped_x1:clamped_x2]
        top_color, bottom_color = self.color_analyzer.extract_clothing_colors(crop)
        direction, action, speed = self.movement_tracker.update(
            track_id=track_id,
            timestamp_seconds=timestamp_seconds,
            x1=clamped_x1,
            y1=clamped_y1,
            x2=clamped_x2,
            y2=clamped_y2,
        )

        return PersonAttributes(
            top_color=top_color,
            bottom_color=bottom_color,
            movement_direction=direction,
            action_label=action,
            speed_px_per_sec=speed,
        )
