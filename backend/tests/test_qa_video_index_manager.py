import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2

from backend.app.database import create_schema
from backend.app.schemas import QAAskRequest
from backend.services.qa_service import QAService
from backend.services.qa_snapshot_storage import qa_video_snapshot_dir
from backend.services.qa_video_index_manager import (
    QAVideoIndexManager,
    QAVideoIndexStopTimeoutError,
)


class FakeCapture:
    def __init__(self, path, *, frames=1000):
        self.frames = frames
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return 1 if prop == cv2.CAP_PROP_FPS else self.frames

    def read(self):
        if self.frames <= 0:
            return False, None
        self.frames -= 1
        return True, object()

    def release(self):
        self.released = True


class GatedEngine:
    def __init__(self, *, block_at=0, fail=False):
        self.entered = threading.Event()
        self.resume = threading.Event()
        self.block_at = block_at
        self.fail = fail
        self.reset_called = False

    def analyze_frame(self, frame, *, frame_index, timestamp_seconds):
        if frame_index == self.block_at:
            self.entered.set()
            if not self.resume.wait(3):
                raise RuntimeError("Test did not release analysis gate")
            if self.fail:
                raise RuntimeError("Analysis interrupted")
        return object()

    def reset(self):
        self.reset_called = True


class FileIndexer:
    def __init__(self, connection, snapshots, *, gate=None):
        self.connection = connection
        self.snapshots = snapshots
        self.gate = gate

    def index_frame(self, frame, *, session_or_video_id, frame_number, timestamp_seconds, **kwargs):
        if self.gate:
            entered, resume = self.gate
            entered.set()
            if not resume.wait(3):
                raise RuntimeError("Test did not release indexing gate")
        self.snapshots.mkdir(parents=True, exist_ok=True)
        path = self.snapshots / f"{session_or_video_id}_{frame_number}.jpg"
        path.write_bytes(b"snapshot")
        self.connection.execute(
            "INSERT INTO video_frames (session_or_video_id, timestamp_seconds, frame_number, frame_path) "
            "VALUES (?, ?, ?, ?)",
            (session_or_video_id, timestamp_seconds, frame_number, str(path)),
        )
        self.connection.commit()

    def reset(self):
        pass


class QAVideoIndexManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshots = self.root / "snapshots"
        self.uploads = self.root / "uploads"
        self.snapshots.mkdir()
        self.uploads.mkdir()
        self.db = self.root / "app.db"
        with self.connection_factory() as connection:
            create_schema(connection)
            connection.execute("INSERT INTO qa_conversations (title) VALUES ('Test')")
        connection.close()
        self.engines = []
        self.captures = []
        self.errors = []

    def connection_factory(self):
        connection = sqlite3.connect(self.db, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def make_manager(self, engine=None, *, frames=1000, index_gate=None, timeout=1, qa_snapshots_dir=None):
        engine = engine or GatedEngine()
        self.engines.append(engine)
        self.addCleanup(engine.resume.set)

        def capture_factory(path):
            capture = FakeCapture(path, frames=frames)
            self.captures.append(capture)
            return capture

        manager = QAVideoIndexManager(
            connection_factory=self.connection_factory,
            capture_factory=capture_factory,
            runtime_factory=lambda connection: SimpleNamespace(engine=engine),
            indexer_factory=lambda connection, *, snapshots_dir: FileIndexer(connection, snapshots_dir, gate=index_gate),
            qa_snapshots_dir=qa_snapshots_dir if qa_snapshots_dir is not None else self.snapshots / "qa",
            stop_timeout_seconds=timeout,
        )

        def cleanup():
            engine.resume.set()
            if index_gate:
                index_gate[1].set()
            manager.shutdown()

        self.addCleanup(cleanup)
        return manager, engine

    def start(self, manager, video_id="qa_test"):
        path = self.uploads / f"{video_id}.mp4"
        path.write_bytes(b"video")
        connection = self.connection_factory()
        with connection:
            connection.execute(
                "INSERT INTO qa_uploaded_videos (conversation_id, video_id, filename, file_path) "
                "VALUES (1, ?, 'test.mp4', ?)", (video_id, str(path)),
            )
        connection.close()
        manager.start(video_id, path)
        return path

    def status(self, video_id="qa_test"):
        connection = self.connection_factory()
        try:
            return connection.execute(
                "SELECT status, completed_at FROM qa_uploaded_videos WHERE video_id = ?", (video_id,),
            ).fetchone()
        finally:
            connection.close()

    def count_frames(self):
        connection = self.connection_factory()
        try:
            return connection.execute("SELECT COUNT(*) FROM video_frames").fetchone()[0]
        finally:
            connection.close()

    def run_async(self, action):
        def run():
            try:
                action()
            except Exception as exc:
                self.errors.append(exc)
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(thread.join, 3)
        return thread

    def test_cancel_joins_analysis_and_prevents_later_writes_or_terminal_status(self):
        for fail in (False, True):
            with self.subTest(analysis_raises=fail):
                manager, engine = self.make_manager(GatedEngine(fail=fail))
                video_id = f"qa_cancel_{fail}"
                self.start(manager, video_id)
                self.assertTrue(engine.entered.wait(1))
                job = manager._jobs[video_id]
                cancel = self.run_async(lambda: manager.cancel(video_id))
                self.assertTrue(job.cancel_event.wait(1))
                self.assertTrue(cancel.is_alive(), "Cancellation must wait for analysis to exit")
                self.assertTrue(job.thread.is_alive())
                engine.resume.set()
                cancel.join(1)
                self.assertFalse(cancel.is_alive())
                self.assertFalse(job.thread.is_alive())
                self.assertNotIn(video_id, manager._jobs)
                time.sleep(0.05)
                self.assertEqual(self.count_frames(), 0)
                self.assertEqual(list(self.snapshots.rglob("*.jpg")), [])
                self.assertEqual(self.status(video_id)["status"], "processing")
                self.assertIsNone(self.status(video_id)["completed_at"])
                self.assertTrue(engine.reset_called)
                self.assertTrue(self.captures[-1].released)
                self.assertEqual(self.errors, [])

    def test_two_videos_use_distinct_factory_supplied_snapshot_directories(self):
        manager, _ = self.make_manager(GatedEngine(block_at=-1), frames=1)
        self.start(manager, "first")
        self.start(manager, "second")
        deadline = time.monotonic() + 2
        while manager._jobs and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(manager._jobs, {})
        connection = self.connection_factory()
        self.addCleanup(connection.close)
        rows = connection.execute("SELECT session_or_video_id, frame_path FROM video_frames").fetchall()
        self.assertEqual(len(rows), 2)
        directories = set()
        for row in rows:
            directory = qa_video_snapshot_dir(row["session_or_video_id"], qa_root=self.snapshots / "qa")
            self.assertEqual(Path(row["frame_path"]).parent, directory)
            self.assertTrue(Path(row["frame_path"]).is_file())
            directories.add(directory)
        self.assertEqual(len(directories), 2)
        self.assertEqual(list(self.snapshots.glob("*.jpg")), [])

    def test_retry_joins_old_worker_and_removes_directory_before_new_indexing(self):
        manager, engine = self.make_manager(GatedEngine(block_at=1))
        input_path = self.start(manager)
        self.assertTrue(engine.entered.wait(1))
        old_job = manager._jobs["qa_test"]
        directory = qa_video_snapshot_dir("qa_test", qa_root=self.snapshots / "qa")
        orphan = directory / "old_only.jpg"
        orphan.write_bytes(b"old orphan")
        entered, resume = threading.Event(), threading.Event()
        self.addCleanup(resume.set)
        factory_directories = []

        def replacement_indexer(connection, *, snapshots_dir):
            self.assertFalse(directory.exists())
            factory_directories.append(snapshots_dir)
            return FileIndexer(connection, snapshots_dir, gate=(entered, resume))

        manager.indexer_factory = replacement_indexer
        manager.capture_factory = lambda path: FakeCapture(path, frames=1)
        connection = self.connection_factory()
        self.addCleanup(connection.close)
        service = QAService(connection, index_manager=manager, snapshots_dir=self.snapshots, uploads_dir=self.uploads)
        retry = self.run_async(lambda: service.retry_uploaded_video("qa_test"))
        self.assertTrue(old_job.cancel_event.wait(1))
        self.assertTrue(orphan.exists())
        engine.resume.set()
        self.assertTrue(entered.wait(1))
        self.assertFalse(old_job.thread.is_alive())
        self.assertFalse(directory.exists())
        self.assertEqual(factory_directories, [directory])
        self.assertEqual(self.count_frames(), 0)
        resume.set()
        retry.join(1)
        deadline = time.monotonic() + 1
        while manager._jobs and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(manager._jobs, {})
        self.assertFalse(retry.is_alive())
        self.assertEqual(self.errors, [])
        self.assertTrue(input_path.exists())
        self.assertTrue(directory.exists())
        self.assertFalse(orphan.exists())
        self.assertEqual(len(list(directory.glob("*.jpg"))), 1)
        self.assertEqual(self.count_frames(), 1)

    def test_cancel_waits_for_inflight_index_write(self):
        entered, resume = threading.Event(), threading.Event()
        manager, engine = self.make_manager(GatedEngine(block_at=-1), index_gate=(entered, resume), frames=1)
        self.start(manager)
        self.assertTrue(entered.wait(1))
        job = manager._jobs["qa_test"]
        cancel = self.run_async(lambda: manager.cancel("qa_test"))
        self.assertTrue(job.cancel_event.wait(1))
        self.assertTrue(cancel.is_alive())
        resume.set()
        cancel.join(1)
        self.assertFalse(cancel.is_alive())
        self.assertEqual(self.count_frames(), 1)
        time.sleep(0.05)
        self.assertEqual(self.count_frames(), 1)
        self.assertEqual(len(list(self.snapshots.rglob("*.jpg"))), 1)
        self.assertEqual(self.status()["status"], "processing")
        self.assertEqual(self.errors, [])

    def test_stop_timeout_keeps_active_job_and_allows_later_cancel(self):
        manager, engine = self.make_manager(timeout=0.02)
        path = self.start(manager)
        self.assertTrue(engine.entered.wait(1))
        job = manager._jobs["qa_test"]
        with self.assertRaises(QAVideoIndexStopTimeoutError):
            manager.cancel("qa_test")
        self.assertIs(manager._jobs["qa_test"], job)
        self.assertTrue(job.thread.is_alive())
        self.assertTrue(path.exists())
        self.assertEqual(self.status()["status"], "processing")
        engine.resume.set()
        manager.stop_timeout_seconds = 1
        manager.cancel("qa_test")
        self.assertNotIn("qa_test", manager._jobs)

    def test_shutdown_signals_all_jobs_and_joins_them(self):
        manager, engine = self.make_manager()
        self.start(manager, "first")
        self.start(manager, "second")
        self.assertTrue(engine.entered.wait(1))
        jobs = list(manager._jobs.values())
        shutdown = self.run_async(manager.shutdown)
        for job in jobs:
            self.assertTrue(job.cancel_event.wait(1))
        engine.resume.set()
        shutdown.join(1)
        self.assertFalse(shutdown.is_alive())
        self.assertTrue(all(not job.thread.is_alive() for job in jobs))
        self.assertEqual(manager._jobs, {})
        self.assertEqual(self.errors, [])

    def test_blocked_status_commit_cannot_block_cancellation_indefinitely(self):
        entered, resume = threading.Event(), threading.Event()
        manager, engine = self.make_manager(timeout=0.02)
        original_factory = manager.connection_factory

        class BlockingConnection:
            def __init__(self):
                self.connection = original_factory()

            def commit(self):
                entered.set()
                if not resume.wait(3):
                    raise RuntimeError("Test did not release status commit")
                self.connection.commit()

            def __getattr__(self, name):
                return getattr(self.connection, name)

        manager.connection_factory = BlockingConnection
        self.addCleanup(resume.set)
        self.start(manager)
        self.assertTrue(entered.wait(1))
        started = time.monotonic()
        with self.assertRaises(QAVideoIndexStopTimeoutError):
            manager.cancel("qa_test")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertIn("qa_test", manager._jobs)
        resume.set()
        engine.resume.set()
        manager.stop_timeout_seconds = 1
        manager.cancel("qa_test")

    def test_completed_and_failed_workers_are_automatically_reaped(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                engine = GatedEngine(fail=fail)
                engine.resume.set()
                manager, engine = self.make_manager(engine, frames=1)
                video_id = f"qa_finished_{fail}"
                self.start(manager, video_id)
                deadline = time.monotonic() + 1
                while manager._jobs and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertEqual(manager._jobs, {})
                self.assertEqual(self.status(video_id)["status"], "failed" if fail else "completed")

    def test_delete_from_another_service_cannot_be_followed_by_new_data(self):
        # A custom-root frame is on disk; the next analysis is still running.
        manager, engine = self.make_manager(
            GatedEngine(block_at=1), qa_snapshots_dir=self.snapshots / "custom_qa",
        )
        path = self.start(manager)
        self.assertTrue(engine.entered.wait(1))
        self.assertEqual(self.count_frames(), 1)
        directory = qa_video_snapshot_dir("qa_test", qa_root=manager.qa_snapshots_dir)
        self.assertTrue((directory / "qa_test_0.jpg").is_file())
        orphan = directory / "orphan.jpg"
        orphan.write_bytes(b"unreferenced snapshot")
        self.assertFalse((self.snapshots / "qa" / "qa_test").exists())
        connection = self.connection_factory()
        self.addCleanup(connection.close)
        service = QAService(connection, index_manager=manager, snapshots_dir=self.snapshots, uploads_dir=self.uploads)
        job = manager._jobs["qa_test"]
        delete = self.run_async(lambda: service.delete_uploaded_video("qa_test"))
        self.assertTrue(job.cancel_event.wait(1))
        self.assertTrue(path.exists())
        self.assertTrue(delete.is_alive())
        engine.resume.set()
        delete.join(1)
        self.assertFalse(delete.is_alive())
        self.assertEqual(self.errors, [])
        self.assertFalse(path.exists())
        # Longer than a fake processing iteration: no worker can repopulate DB/disk.
        time.sleep(0.15)
        self.assertEqual(self.count_frames(), 0)
        self.assertEqual(list(self.snapshots.rglob("*.jpg")), [])
        self.assertIsNone(self.status())
        self.assertFalse(directory.exists())
        self.assertFalse(orphan.exists())
        self.assertFalse((self.snapshots / "qa" / "qa_test").exists())
        self.assertFalse(job.thread.is_alive())

    def test_delete_timeout_preserves_files_and_database(self):
        manager, engine = self.make_manager(GatedEngine(block_at=1), timeout=0.02)
        path = self.start(manager)
        self.assertTrue(engine.entered.wait(1))
        connection = self.connection_factory()
        self.addCleanup(connection.close)
        service = QAService(connection, index_manager=manager, snapshots_dir=self.snapshots, uploads_dir=self.uploads)
        with self.assertRaises(QAVideoIndexStopTimeoutError):
            service.delete_uploaded_video("qa_test")
        self.assertTrue(path.exists())
        self.assertEqual(self.count_frames(), 1)
        self.assertIsNotNone(self.status())
        self.assertEqual(len(list(self.snapshots.rglob("*.jpg"))), 1)
        engine.resume.set()

    def test_conversation_delete_joins_every_active_worker_before_cleanup(self):
        manager, engine = self.make_manager(GatedEngine(block_at=1))
        paths = [self.start(manager, "first"), self.start(manager, "second")]
        deadline = time.monotonic() + 1
        while self.count_frames() < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(self.count_frames(), 2)
        connection = self.connection_factory()
        self.addCleanup(connection.close)
        service = QAService(connection, index_manager=manager, snapshots_dir=self.snapshots, uploads_dir=self.uploads)
        jobs = list(manager._jobs.values())
        delete = self.run_async(lambda: service.delete_conversation(1))
        for job in jobs:
            self.assertTrue(job.cancel_event.wait(1))
        self.assertTrue(all(path.exists() for path in paths))
        self.assertEqual(len(list(self.snapshots.rglob("*.jpg"))), 2)
        engine.resume.set()
        delete.join(1)
        self.assertFalse(delete.is_alive())
        self.assertEqual(self.errors, [])
        time.sleep(0.05)
        self.assertEqual(self.count_frames(), 0)
        self.assertEqual(list(self.snapshots.rglob("*.jpg")), [])
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertTrue(all(not job.thread.is_alive() for job in jobs))
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM qa_conversations").fetchone()[0], 0)
        self.assertIsNone(self.status("first"))
        self.assertIsNone(self.status("second"))
        for video_id in ("first", "second"):
            self.assertFalse(qa_video_snapshot_dir(video_id, qa_root=self.snapshots / "qa").exists())

    def test_ask_cannot_recreate_evidence_after_delete_during_reasoning(self):
        manager = QAVideoIndexManager(qa_snapshots_dir=self.snapshots / "qa")
        self.addCleanup(manager.shutdown)
        ask_connection = self.connection_factory()
        delete_connection = self.connection_factory()
        self.addCleanup(ask_connection.close)
        self.addCleanup(delete_connection.close)
        ask_service = QAService(
            ask_connection, api_key="", index_manager=manager,
            snapshots_dir=self.snapshots, uploads_dir=self.uploads,
        )
        delete_service = QAService(
            delete_connection, api_key="", index_manager=manager,
            snapshots_dir=self.snapshots, uploads_dir=self.uploads,
        )
        for include_frame_id in (False, True):
            with self.subTest(include_frame_id=include_frame_id):
                video_id = f"qa_ask_race_{include_frame_id}"
                snapshot = qa_video_snapshot_dir(video_id, qa_root=self.snapshots / "qa") / f"{video_id}.jpg"
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                input_path = self.uploads / f"{video_id}.mp4"
                snapshot.write_bytes(b"snapshot")
                input_path.write_bytes(b"video")
                with delete_connection:
                    delete_connection.execute(
                        "INSERT INTO qa_uploaded_videos (conversation_id, video_id, filename, file_path, status) "
                        "VALUES (1, ?, 'test.mp4', ?, 'completed')", (video_id, str(input_path)),
                    )
                    frame_id = delete_connection.execute(
                        "INSERT INTO video_frames (session_or_video_id, timestamp_seconds, frame_number, frame_path) "
                        "VALUES (?, 0, 0, ?)", (video_id, str(snapshot)),
                    ).lastrowid
                entered, resume = threading.Event(), threading.Event()
                results = []

                def reason(**kwargs):
                    self.assertEqual(kwargs["context_data"]["entities"][0]["frame_id"], frame_id)
                    entered.set()
                    if not resume.wait(3):
                        raise RuntimeError("Test did not release reasoning")
                    return {"response_vi": "answer", "evidences": [{
                        "frame_id": frame_id if include_frame_id else None,
                        "snapshot_path": str(snapshot), "start_timestamp": 0, "end_timestamp": 1,
                    }]}

                with patch.object(ask_service, "_reason_with_gemini", side_effect=reason):
                    ask_thread = self.run_async(lambda: results.append(ask_service.ask(QAAskRequest(
                        question="What happened?", conversation_id=1, session_or_video_id=video_id,
                    ))))
                    try:
                        self.assertTrue(entered.wait(1))
                        # Must complete while Gemini is blocked, proving reasoning
                        # does not hold the lifecycle lock.
                        delete_service.delete_uploaded_video(video_id)
                        self.assertFalse(snapshot.exists())
                        self.assertFalse(input_path.exists())
                        self.assertEqual(self.count_frames(), 0)
                        self.assertIsNone(self.status(video_id))
                        self.assertEqual(delete_connection.execute("SELECT COUNT(*) FROM qa_evidences").fetchone()[0], 0)
                    finally:
                        resume.set()
                        ask_thread.join(2)
                self.assertFalse(ask_thread.is_alive())
                self.assertEqual(self.errors, [])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].evidences, [])
                persisted = ask_service.get_conversation_detail(1)
                self.assertTrue(all(message.evidences == [] for message in persisted.messages))
                self.assertFalse(snapshot.exists())
                self.assertFalse(snapshot.parent.exists())
                self.assertEqual(delete_connection.execute("SELECT COUNT(*) FROM qa_evidences").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
