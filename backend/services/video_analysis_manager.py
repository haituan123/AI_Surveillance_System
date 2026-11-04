import sqlite3
import threading
import time
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2

from backend.ai.analysis_engine import annotate_frame
from backend.ai.threat_detector import (
    ThreatAndObjectDetector,
    annotate_threat_events,
)
from backend.app.config import (
    VIDEO_ANALYSIS_RESULT_TTL_SECONDS,
    VIDEO_ANALYSIS_STOP_TIMEOUT_SECONDS,
)
from backend.app.database import get_connection
from backend.app.models import VideoAnalysisState
from backend.services.gallery_service import (
    AnalysisRuntime,
    build_analysis_runtime,
)
from backend.services.temporary_event_collector import TemporaryEventCollector


logger = logging.getLogger(__name__)


class VideoAnalysisError(RuntimeError):
    pass


class VideoAnalysisBusyError(VideoAnalysisError):
    pass


class VideoAnalysisNotFoundError(VideoAnalysisError):
    pass


class VideoAnalysisStopTimeoutError(VideoAnalysisError):
    pass


@dataclass
class _VideoJob:
    job_id: str
    filename: str
    input_path: Path
    state: VideoAnalysisState
    created_at: str
    processed_frames: int = 0
    total_frames: int | None = None
    progress: float | None = None
    processing_fps: float = 0.0
    completed_at: str | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0
    known_events: int = 0
    unknown_events: int = 0
    threat_events: int = 0
    events_truncated: bool = False
    events: list[dict] = field(default_factory=list)
    latest_frame_jpeg: bytes | None = None
    event_snapshots: dict[str, bytes] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    completed_monotonic: float | None = None


class VideoAnalysisManager:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
        capture_factory: Callable = cv2.VideoCapture,
        runtime_factory: Callable[
            [sqlite3.Connection], AnalysisRuntime
        ] = build_analysis_runtime,
        result_ttl_seconds: float = VIDEO_ANALYSIS_RESULT_TTL_SECONDS,
        stop_timeout_seconds: float = VIDEO_ANALYSIS_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self.connection_factory = connection_factory
        self.capture_factory = capture_factory
        self.runtime_factory = runtime_factory
        self.result_ttl_seconds = result_ttl_seconds
        self.stop_timeout_seconds = stop_timeout_seconds
        self._lock = threading.RLock()
        self._jobs: dict[str, _VideoJob] = {}

    def submit(self, input_path: Path, filename: str) -> dict:
        self.cleanup_expired()
        with self._lock:
            if self.has_active_job():
                raise VideoAnalysisBusyError(
                    "Another uploaded video is already being analyzed"
                )
            job_id = uuid4().hex
            job = _VideoJob(
                job_id=job_id,
                filename=filename,
                input_path=input_path,
                state=VideoAnalysisState.QUEUED,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            job.thread = threading.Thread(
                target=self._run_job,
                args=(job_id,),
                name=f"video-analysis-{job_id}",
                daemon=True,
            )
            self._jobs[job_id] = job
            job.thread.start()
            return self._status_dict(job)

    def status(self, job_id: str) -> dict:
        self.cleanup_expired()
        with self._lock:
            return self._status_dict(self._get_job(job_id))

    def results(self, job_id: str) -> dict:
        self.cleanup_expired()
        with self._lock:
            job = self._get_job(job_id)
            return {
                "job_id": job.job_id,
                "filename": job.filename,
                "state": job.state,
                "persistent": False,
                "summary": {
                    "total_frames": job.processed_frames,
                    "duration_seconds": job.duration_seconds,
                    "average_processing_fps": job.processing_fps,
                    "known_events": job.known_events,
                    "unknown_events": job.unknown_events,
                    "threat_events": job.threat_events,
                    "events_truncated": job.events_truncated,
                },
                "events": list(job.events),
                "error_message": job.error_message,
            }

    def latest_frame(self, job_id: str) -> bytes | None:
        self.cleanup_expired()
        with self._lock:
            return self._get_job(job_id).latest_frame_jpeg

    def event_snapshot(self, job_id: str, event_id: str) -> bytes | None:
        self.cleanup_expired()
        with self._lock:
            job = self._get_job(job_id)
            return job.event_snapshots.get(event_id)

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._get_job(job_id)
            thread = job.thread
            if thread is not None and thread.is_alive():
                job.cancel_event.set()

        if thread is not None and thread.is_alive():
            thread.join(timeout=self.stop_timeout_seconds)
            if thread.is_alive():
                raise VideoAnalysisStopTimeoutError(
                    "Timed out while cancelling uploaded-video analysis"
                )

        with self._lock:
            removed = self._jobs.pop(job_id, None)
        if removed is not None:
            self._delete_input_file(removed.input_path)

    def has_active_job(self) -> bool:
        with self._lock:
            return any(
                job.state
                in {VideoAnalysisState.QUEUED, VideoAnalysisState.RUNNING}
                for job in self._jobs.values()
            )

    def shutdown(self) -> None:
        with self._lock:
            jobs = list(self._jobs.values())
            for job in jobs:
                if job.thread is not None and job.thread.is_alive():
                    job.cancel_event.set()
        for job in jobs:
            if job.thread is not None and job.thread.is_alive():
                job.thread.join(timeout=self.stop_timeout_seconds)
            self._delete_input_file(job.input_path)

    def cleanup_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.completed_monotonic is not None
                and now - job.completed_monotonic >= self.result_ttl_seconds
            ]
            removed = [self._jobs.pop(job_id) for job_id in expired]
        for job in removed:
            self._delete_input_file(job.input_path)

    def _run_job(self, job_id: str) -> None:
        connection = None
        capture = None
        runtime = None
        started = time.perf_counter()
        input_fps = 0.0

        with self._lock:
            job = self._jobs[job_id]
            job.state = VideoAnalysisState.RUNNING

        try:
            connection = self.connection_factory()
            runtime = self.runtime_factory(connection)
            collector = TemporaryEventCollector(
                member_names=runtime.member_names
            )
            threat_detector = ThreatAndObjectDetector()
            object_detection_available = True
            capture = self.capture_factory(str(job.input_path))
            if not capture.isOpened():
                raise RuntimeError("Could not open uploaded video")

            input_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            total_frames_value = int(
                capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            )
            with self._lock:
                job.total_frames = total_frames_value or None

            frame_index = 0
            while not job.cancel_event.is_set():
                success, frame = capture.read()
                if not success or frame is None:
                    break

                timestamp_seconds = (
                    frame_index / input_fps
                    if input_fps > 0
                    else time.perf_counter() - started
                )
                preview_encoded, preview_buffer = cv2.imencode(".jpg", frame)
                if preview_encoded:
                    with self._lock:
                        job.latest_frame_jpeg = preview_buffer.tobytes()
                        job.processed_frames = frame_index + 1
                        job.processing_fps = (
                            (frame_index + 1)
                            / max(time.perf_counter() - started, 1e-9)
                        )
                        job.progress = (
                            min((frame_index + 1) / job.total_frames, 1.0)
                            if job.total_frames
                            else None
                        )
                if job.cancel_event.is_set():
                    break

                analysis = runtime.engine.analyze_frame(
                    frame,
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                )
                raw_detections = []
                person_tracker = getattr(runtime.engine, "person_tracker", None)
                if (
                    object_detection_available
                    and person_tracker is not None
                    and hasattr(person_tracker, "detect_objects")
                ):
                    try:
                        raw_detections = person_tracker.detect_objects(frame)
                    except Exception as exc:
                        object_detection_available = False
                        logger.warning(
                            "Security-object detection is unavailable: %s",
                            exc,
                        )
                _, threat_events = threat_detector.evaluate_detections(
                    raw_detections,
                    person_boxes=[
                        track.bounding_box for track in analysis.tracks
                    ],
                )
                new_events = collector.process(analysis, threat_events)
                annotated = annotate_frame(
                    frame,
                    analysis,
                    member_names=runtime.member_names,
                )
                annotated = annotate_threat_events(annotated, threat_events)
                encoded, buffer = cv2.imencode(".jpg", annotated)
                if not encoded:
                    raise RuntimeError(
                        "Could not encode uploaded-video analysis frame"
                    )

                frame_index += 1
                elapsed = max(time.perf_counter() - started, 1e-9)
                with self._lock:
                    encoded_bytes = buffer.tobytes()
                    for event in new_events:
                        event_id = event.get("event_id")
                        if event.get("is_threat") and event_id:
                            event["snapshot_url"] = (
                                f"/video-analysis/{job_id}/events/"
                                f"{event_id}/snapshot"
                            )
                            job.event_snapshots[event_id] = encoded_bytes
                    job.processed_frames = frame_index
                    job.processing_fps = frame_index / elapsed
                    job.progress = (
                        min(frame_index / job.total_frames, 1.0)
                        if job.total_frames
                        else None
                    )
                    job.latest_frame_jpeg = encoded_bytes
                    job.events = list(collector.events)
                    job.known_events = collector.total_known_events
                    job.unknown_events = collector.total_unknown_events
                    job.threat_events = collector.total_threat_events
                    job.events_truncated = collector.events_truncated

            if frame_index == 0 and not job.cancel_event.is_set():
                raise RuntimeError(
                    "Uploaded video did not contain any readable frames"
                )
            with self._lock:
                if job.cancel_event.is_set():
                    job.state = VideoAnalysisState.CANCELLED
                else:
                    job.state = VideoAnalysisState.COMPLETED

        except Exception as exc:
            logger.exception("Uploaded-video analysis failed")
            with self._lock:
                job.state = VideoAnalysisState.FAILED
                job.error_message = str(exc)
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
            if runtime is not None:
                try:
                    runtime.engine.reset()
                except Exception:
                    pass
            if connection is not None:
                connection.close()
            self._delete_input_file(job.input_path)

            elapsed = max(time.perf_counter() - started, 1e-9)
            with self._lock:
                job.processing_fps = job.processed_frames / elapsed
                job.duration_seconds = (
                    job.processed_frames / input_fps
                    if input_fps > 0
                    else elapsed
                )
                if job.total_frames and job.state is VideoAnalysisState.COMPLETED:
                    job.progress = 1.0
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.completed_monotonic = time.monotonic()

    def _get_job(self, job_id: str) -> _VideoJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        return job

    @staticmethod
    def _status_dict(job: _VideoJob) -> dict:
        return {
            "job_id": job.job_id,
            "filename": job.filename,
            "state": job.state,
            "persistent": False,
            "processed_frames": job.processed_frames,
            "total_frames": job.total_frames,
            "progress": job.progress,
            "processing_fps": job.processing_fps,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
        }

    @staticmethod
    def _delete_input_file(path: Path) -> None:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass


video_analysis_manager = VideoAnalysisManager()
