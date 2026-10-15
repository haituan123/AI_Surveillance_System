import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import SCHEMA_VERSION, create_schema
from backend.main import create_app
from backend.routes.system_routes import get_readiness_service
from backend.services.readiness_service import ReadinessService


class ReadinessTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        create_schema(self.connection)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        runtime_path = Path(self.temporary_directory.name)
        self.service = ReadinessService(
            self.connection,
            runtime_directories=(runtime_path,),
        )
        self.addCleanup(self.connection.close)

    def test_ready_database_and_storage(self):
        result = self.service.inspect()

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["database"]["ready"])
        self.assertEqual(result["database"]["schema_version"], SCHEMA_VERSION)
        self.assertTrue(result["storage"]["ready"])
        self.assertTrue(result["ai_assets"]["lazy_loading"])

    def test_missing_table_is_degraded(self):
        self.connection.execute("DROP TABLE alerts")
        self.connection.commit()

        result = self.service.inspect()

        self.assertEqual(result["status"], "degraded")
        self.assertIn("alerts", result["database"]["missing_tables"])

    def test_readiness_route_reports_worker_state(self):
        app = create_app(initialize_database=False)
        app.dependency_overrides[get_readiness_service] = lambda: self.service
        with TestClient(app) as client:
            response = client.get("/health/readiness")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertIn("live_surveillance_running", body["workers"])
        self.assertIn("video_analysis_running", body["workers"])
