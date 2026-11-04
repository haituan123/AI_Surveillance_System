import sqlite3
import threading
import time
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2

from backend.ai.analysis_engine import annotate_frame
from backend.ai.contracts import FrameAnalysis
from backend.app.config import (
    CAMERA_READ_FAILURE_LIMIT,
    SURVEILLANCE_STOP_TIMEOUT_SECONDS,
)
from backend.app.database import get_connection
from backend.app.models import LiveSurveillanceState
from backend.camera.webcam import open_camera_capture, resolve_camera_source
from backend.services.gallery_service import (
    AnalysisRuntime,
    build_analysis_runtime,
)
from backend.services.live_event_service import LiveEventRecorder
from backend.services.zone_service import RestrictedZone, ZoneService


logger = logging.getLogger(__name__)


class SurveillanceError(RuntimeError):
    pass


class SurveillanceAlreadyRunningError(SurveillanceError):
    pass


class SurveillanceNotRunningError(SurveillanceError):
    pass


class SurveillanceStopTimeoutError(SurveillanceError):
    pass


class SurveillanceCameraNotFoundError(SurveillanceError):
    pass


class SurveillanceCameraInactiveError(SurveillanceError):
    pass


@dataclass(frozen=True)
class SurveillanceStatusSnapshot:
    state: LiveSurveillanceState
    running: bool
    camera_id: int | None
    session_id: int | None
    frames_processed: int
    fps: float
    started_at: str | None
    error_message: str | None


@dataclass(frozen=True)
class LatestAnalysisSnapshot:
    analysis: FrameAnalysis
    member_names: dict[int, str]


class LiveSurveillanceManager:
    def __init__(
        self,
        *,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
        capture_factory: Callable = cv2.VideoCapture,
        runtime_factory: Callable[
            [sqlite3.Connection], AnalysisRuntime
        ] = build_analysis_runtime,
        event_recorder_factory: Callable[
            [
                sqlite3.Connection,
                int,
                int,
                list[RestrictedZone] | None,
            ],
            LiveEventRecorder,
        ] | None = None,
        read_failure_limit: int = CAMERA_READ_FAILURE_LIMIT,
        stop_timeout_seconds: float = SURVEILLANCE_STOP_TIMEOUT_SECONDS,
    ) -> None:
        if read_failure_limit <= 0:
            raise ValueError("Camera read failure limit must be positive")
        self.connection_factory = connection_factory
        self.capture_factory = capture_factory
        self.runtime_factory = runtime_factory
        self.event_recorder_factory = (
            event_recorder_factory or self._build_event_recorder
        )
        self.read_failure_limit = read_failure_limit
        self.stop_timeout_seconds = stop_timeout_seconds

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._starting = False
        self._state = LiveSurveillanceState.IDLE
        self._camera_id: int | None = None
        self._session_id: int | None = None
        self._frames_processed = 0
        self._fps = 0.0
        self._started_at: str | None = None
        self._error_message: str | None = None
        self._latest_analysis: FrameAnalysis | None = None
        self._latest_frame_jpeg: bytes | None = None
        self._member_names: dict[int, str] = {}
        self._capture = None

    def start(self, camera_id: int) -> SurveillanceStatusSnapshot:
        with self._lock:
            if self._starting or (
                self._thread is not None and self._thread.is_alive()
            ):
                raise SurveillanceAlreadyRunningError(
                    "Live surveillance is already running"
                )
            self._starting = True

        try:
            connection = self.connection_factory()
            try:
                camera = connection.execute(
                    """
                    SELECT id, source, is_active
                    FROM cameras
                    WHERE id = ?
                    """,
                    (camera_id,),
                ).fetchone()
                if camera is None:
                    raise SurveillanceCameraNotFoundError("Camera not found")
                if not bool(camera["is_active"]):
                    raise SurveillanceCameraInactiveError("Camera is inactive")

                cursor = connection.execute(
                    """
                    INSERT INTO surveillance_sessions (camera_id, status)
                    VALUES (?, 'running')
                    """,
                    (camera_id,),
                )
                connection.commit()
                session_id = int(cursor.lastrowid)
                session = connection.execute(
                    """
                    SELECT started_at
                    FROM surveillance_sessions
                    WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
            finally:
                connection.close()
        except Exception:
            with self._lock:
                self._starting = False
            raise

        with self._lock:
            self._stop_event = threading.Event()
            self._state = LiveSurveillanceState.RUNNING
            self._camera_id = camera_id
            self._session_id = session_id
            self._frames_processed = 0
            self._fps = 0.0
            self._started_at = str(session["started_at"])
            self._error_message = None
            self._latest_analysis = None
            self._latest_frame_jpeg = None
            self._member_names = {}
            self._thread = threading.Thread(
                target=self._run_worker,
                args=(
                    str(camera["source"]),
                    camera_id,
                    session_id,
                    self._stop_event,
                ),
                name=f"live-surveillance-{session_id}",
                daemon=True,
            )
            self._starting = False
            self._thread.start()
            return self.status()

    def stop(self) -> SurveillanceStatusSnapshot:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                raise SurveillanceNotRunningError(
                    "Live surveillance is not running"
                )
            self._stop_event.set()
            capture = self._capture

        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

        thread.join(timeout=self.stop_timeout_seconds)
        return self.status()

    def shutdown(self) -> None:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return
            self._stop_event.set()
        thread.join(timeout=self.stop_timeout_seconds)

    def status(self) -> SurveillanceStatusSnapshot:
        with self._lock:
            running = (
                self._state is LiveSurveillanceState.RUNNING
                and self._thread is not None
                and self._thread.is_alive()
                and not self._stop_event.is_set()
            )
            return SurveillanceStatusSnapshot(
                state=self._state,
                running=running,
                camera_id=self._camera_id,
                session_id=self._session_id,
                frames_processed=self._frames_processed,
                fps=self._fps,
                started_at=self._started_at,
                error_message=self._error_message,
            )

    def latest_analysis(self) -> LatestAnalysisSnapshot | None:
        with self._lock:
            if self._latest_analysis is None:
                return None
            return LatestAnalysisSnapshot(
                analysis=self._latest_analysis,
                member_names=dict(self._member_names),
            )

    def latest_frame_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_frame_jpeg

    def is_camera_running(self, camera_id: int) -> bool:
        status = self.status()
        return status.running and status.camera_id == camera_id

    def _run_worker(
        self,
        source: str,
        camera_id: int,
        session_id: int,
        stop_event: threading.Event,
    ) -> None:
        connection = self.connection_factory()
        capture = None
        runtime = None
        restricted_zones: list[RestrictedZone] = []
        started = time.perf_counter()
        error_message = None
        final_state = LiveSurveillanceState.STOPPED

        try:
            runtime = self.runtime_factory(connection)
            zone_service = ZoneService(connection)
            restricted_zones = zone_service.list_active_restricted_zones(
                camera_id
            )
            event_recorder = self.event_recorder_factory(
                connection,
                session_id,
                camera_id,
                restricted_zones,
            )
            capture = open_camera_capture(
                resolve_camera_source(source),
                capture_factory=self.capture_factory,
            )
            if not capture.isOpened():
                raise RuntimeError(f"Could not open camera source: {source}")
            with self._lock:
                self._capture = capture

            frame_index = 0
            consecutive_failures = 0
            while not stop_event.is_set():
                success, frame = capture.read()
                if not success or frame is None or frame.size == 0:
                    consecutive_failures += 1
                    if consecutive_failures >= self.read_failure_limit:
                        raise RuntimeError(
                            f"Camera stopped returning frames: {source}"
                        )
                    time.sleep(0.01)
                    continue

                consecutive_failures = 0
                elapsed = time.perf_counter() - started
                preview_encoded, preview_buffer = cv2.imencode(".jpg", frame)
                if preview_encoded:
                    with self._lock:
                        self._latest_frame_jpeg = preview_buffer.tobytes()
                if stop_event.is_set():
                    break

                analysis = runtime.engine.analyze_frame(
                    frame,
                    frame_index=frame_index,
                    timestamp_seconds=elapsed,
                )
                if frame_index % 15 == 0:
                    restricted_zones = zone_service.list_active_restricted_zones(
                        camera_id
                    )
                    event_recorder.restricted_zones = restricted_zones
                annotated = annotate_frame(
                    frame,
                    analysis,
                    member_names=runtime.member_names,
                    restricted_zones=restricted_zones,
                )
                encoded, buffer = cv2.imencode(".jpg", annotated)
                if not encoded:
                    raise RuntimeError("Could not encode live surveillance frame")
                encoded_bytes = buffer.tobytes()
                event_recorder.process(analysis, encoded_bytes)

                frame_index += 1
                current_elapsed = max(time.perf_counter() - started, 1e-9)
                with self._lock:
                    self._frames_processed = frame_index
                    self._fps = frame_index / current_elapsed
                    self._latest_analysis = analysis
                    self._latest_frame_jpeg = encoded_bytes
                    self._member_names = dict(runtime.member_names)

        except Exception as exc:
            final_state = LiveSurveillanceState.FAILED
            error_message = str(exc)
            logger.exception("Live surveillance worker failed")
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
                with self._lock:
                    if self._capture is capture:
                        self._capture = None
            if runtime is not None:
                try:
                    runtime.engine.reset()
                except Exception as exc:
                    if error_message is None:
                        final_state = LiveSurveillanceState.FAILED
                        error_message = f"Analysis cleanup failed: {exc}"

            elapsed = max(time.perf_counter() - started, 1e-9)
            with self._lock:
                frames_processed = self._frames_processed
                average_fps = frames_processed / elapsed
                self._fps = average_fps
                self._state = final_state
                self._error_message = error_message

            try:
                connection.execute(
                    """
                    UPDATE surveillance_sessions
                    SET status = ?,
                        ended_at = ?,
                        average_fps = ?,
                        frames_processed = ?,
                        error_message = ?
                    WHERE id = ?
                    """,
                    (
                        final_state.value,
                        datetime.now(timezone.utc).isoformat(),
                        average_fps,
                        frames_processed,
                        error_message,
                        session_id,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def _build_event_recorder(
        connection: sqlite3.Connection,
        session_id: int,
        camera_id: int,
        restricted_zones: list[RestrictedZone] | None = None,
    ) -> LiveEventRecorder:
        return LiveEventRecorder(
            connection,
            session_id=session_id,
            camera_id=camera_id,
            restricted_zones=restricted_zones,
        )


surveillance_manager = LiveSurveillanceManager()
