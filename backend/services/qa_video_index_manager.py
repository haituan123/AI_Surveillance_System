"""Process-wide lifecycle for persistent Video Q&A indexing workers."""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2

from backend.app.config import QA_SNAPSHOTS_DIR, QA_VIDEO_INDEX_STOP_TIMEOUT_SECONDS
from backend.app.database import get_connection
from backend.app.models import QAUploadedVideoStatus
from backend.services.frame_indexer_service import FrameIndexerService
from backend.services.gallery_service import build_analysis_runtime
from backend.services.qa_snapshot_storage import qa_video_snapshot_dir

logger = logging.getLogger(__name__)


class QAVideoIndexStopTimeoutError(RuntimeError):
    """A worker still owns its input and indexed data; cleanup must not proceed."""


@dataclass
class _IndexJob:
    video_id: str
    file_path: Path
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status_lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None


class QAVideoIndexManager:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
        capture_factory: Callable = cv2.VideoCapture,
        runtime_factory: Callable = build_analysis_runtime,
        indexer_factory: Callable = FrameIndexerService,
        qa_snapshots_dir: Path = QA_SNAPSHOTS_DIR,
        stop_timeout_seconds: float = QA_VIDEO_INDEX_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self.connection_factory = connection_factory
        self.capture_factory = capture_factory
        self.runtime_factory = runtime_factory
        self.indexer_factory = indexer_factory
        self.qa_snapshots_dir = Path(qa_snapshots_dir)
        self.stop_timeout_seconds = stop_timeout_seconds
        # Services hold this across registration/retry/deletion, including commit.
        # Workers never acquire it, so joining while holding it is safe.
        self.lifecycle_lock = threading.RLock()
        self._lock = threading.RLock()
        self._jobs: dict[str, _IndexJob] = {}
        self._shutting_down = False

    def start(self, video_id: str, file_path: Path) -> None:
        with self.lifecycle_lock:
            self.cancel(video_id)
            with self._lock:
                if self._shutting_down:
                    raise RuntimeError("Q&A indexing is shutting down")
                job = _IndexJob(video_id, Path(file_path))
                job.thread = threading.Thread(
                    target=self._run_job,
                    args=(job,),
                    name=f"qa-video-index-{video_id}",
                    daemon=True,
                )
                self._jobs[video_id] = job
                try:
                    job.thread.start()
                except Exception:
                    self._jobs.pop(video_id, None)
                    raise
                # A separate joiner removes even naturally finished jobs, strictly
                # after their worker exits (never from the worker's own finally).
                threading.Thread(
                    target=self._reap_job,
                    args=(job,),
                    name=f"qa-video-index-reaper-{video_id}",
                    daemon=True,
                ).start()

    def cancel(self, video_id: str) -> None:
        self.cancel_many([video_id])

    def cancel_many(self, video_ids: Iterable[str]) -> None:
        with self.lifecycle_lock:
            deadline = time.monotonic() + self.stop_timeout_seconds
            with self._lock:
                jobs = [self._jobs[v] for v in video_ids if v in self._jobs]
            timed_out = False
            for job in jobs:
                # Status commits are atomic with cancellation. A blocked DB
                # commit must also respect the stop deadline, not hold the
                # registry lock and prevent every other job from cancelling.
                if not job.status_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
                    logger.error("Timed out cancelling Q&A status write for %s", job.video_id)
                    timed_out = True
                    continue
                try:
                    job.cancel_event.set()
                finally:
                    job.status_lock.release()
            for job in jobs:
                job.thread.join(timeout=max(0.0, deadline - time.monotonic()))
                if job.thread.is_alive():
                    logger.error("Timed out stopping Q&A indexing for %s", job.video_id)
                    timed_out = True
                else:
                    self._remove_stopped_job(job)
            if timed_out:
                raise QAVideoIndexStopTimeoutError(
                    "Timed out stopping Q&A video indexing; please retry"
                )

    def shutdown(self) -> None:
        with self.lifecycle_lock:
            with self._lock:
                self._shutting_down = True
                video_ids = list(self._jobs)
            self.cancel_many(video_ids)

    def _reap_job(self, job: _IndexJob) -> None:
        job.thread.join()
        self._remove_stopped_job(job)

    def _remove_stopped_job(self, job: _IndexJob) -> None:
        with self._lock:
            if not job.thread.is_alive() and self._jobs.get(job.video_id) is job:
                del self._jobs[job.video_id]

    def _update(self, connection, job, assignments: str, parameters: tuple) -> None:
        # Serialize the cancellation signal with status writes. Cancellation must
        # never be followed by a completed/failed status from this worker.
        with job.status_lock:
            if job.cancel_event.is_set():
                return
            connection.execute(
                f"UPDATE qa_uploaded_videos SET {assignments} WHERE video_id = ?",
                (*parameters, job.video_id),
            )
            connection.commit()

    def _run_job(self, job: _IndexJob) -> None:
        connection = capture = runtime = indexer = None
        cancelled = job.cancel_event.is_set
        try:
            if cancelled():
                return
            connection = self.connection_factory()
            self._update(connection, job, "status = ?", (QAUploadedVideoStatus.PROCESSING,))
            if cancelled():
                return
            capture = self.capture_factory(str(job.file_path))
            if cancelled():
                return
            if not capture.isOpened():
                raise RuntimeError("Could not open Q&A uploaded video")
            input_fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total_frames > 0:
                self._update(connection, job, "total_frames = ?", (total_frames,))
            if cancelled():
                return
            sample_interval = max(1, int(input_fps))
            indexer = self.indexer_factory(
                connection,
                snapshots_dir=qa_video_snapshot_dir(job.video_id, qa_root=self.qa_snapshots_dir),
            )
            if cancelled():
                return
            runtime = self.runtime_factory(connection)
            if cancelled():
                return

            yolo_model = None
            try:
                if hasattr(runtime.engine, "person_tracker") and hasattr(runtime.engine.person_tracker, "_get_model"):
                    yolo_model = runtime.engine.person_tracker._get_model()
            except Exception:
                pass

            frame_index = indexed_count = 0
            while not cancelled():
                success, frame = capture.read()
                if cancelled():
                    return
                if not success or frame is None:
                    break
                if frame_index % sample_interval == 0:
                    timestamp_seconds = frame_index / input_fps if input_fps > 0 else 0.0
                    if cancelled():
                        return
                    analysis = runtime.engine.analyze_frame(
                        frame,
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                    )
                    if cancelled():
                        return
                    raw_detections = []
                    if yolo_model is not None:
                        try:
                            yolo_res = yolo_model(frame, conf=0.30, verbose=False)
                            if yolo_res and len(yolo_res) > 0 and yolo_res[0].boxes is not None:
                                for box in yolo_res[0].boxes:
                                    cls_id = int(box.cls.item())
                                    coords = box.xyxy[0].cpu().numpy().astype(int)
                                    raw_detections.append({
                                        "label": yolo_res[0].names.get(cls_id, ""),
                                        "confidence": float(box.conf.item()),
                                        "x1": int(coords[0]), "y1": int(coords[1]),
                                        "x2": int(coords[2]), "y2": int(coords[3]),
                                    })
                        except Exception:
                            pass
                    elif hasattr(runtime.engine, "_last_yolo_results"):
                        raw_detections = runtime.engine._last_yolo_results
                    if cancelled():
                        return
                    # An index already in flight may finish; cancel joins this
                    # thread before the service collects or deletes any data.
                    indexer.index_frame(
                        frame,
                        camera_id=None,
                        session_or_video_id=job.video_id,
                        timestamp_seconds=timestamp_seconds,
                        frame_number=frame_index,
                        analysis=analysis,
                        raw_object_detections=raw_detections,
                    )
                    indexed_count += 1
                frame_index += 1
                if cancelled():
                    return
                if frame_index % 30 == 0:
                    self._update(connection, job, "processed_frames = ?", (frame_index,))
            if cancelled():
                return
            self._update(
                connection, job,
                "status = ?, processed_frames = ?, completed_at = ?",
                (QAUploadedVideoStatus.COMPLETED, frame_index, datetime.now(timezone.utc).isoformat()),
            )
            logger.info("Q&A indexing finished: %s (%d indexed)", job.video_id, indexed_count)
        except Exception as exc:
            if not cancelled():
                logger.exception("Q&A indexing failed for %s", job.video_id)
                if connection is not None:
                    try:
                        connection.rollback()
                        self._update(
                            connection, job,
                            "status = ?, error_message = ?, completed_at = ?",
                            (QAUploadedVideoStatus.FAILED, str(exc), datetime.now(timezone.utc).isoformat()),
                        )
                    except Exception:
                        logger.exception("Could not persist Q&A indexing failure for %s", job.video_id)
        finally:
            # Never release a VideoCapture concurrently with read() in another
            # thread; a blocked native operation instead triggers the stop timeout.
            for resource in (capture, indexer, runtime.engine if runtime else None):
                if resource is not None:
                    try:
                        if resource is capture:
                            resource.release()
                        else:
                            resource.reset()
                    except Exception:
                        logger.exception("Q&A worker resource cleanup failed for %s", job.video_id)
            if connection is not None:
                connection.close()


qa_video_index_manager = QAVideoIndexManager()
