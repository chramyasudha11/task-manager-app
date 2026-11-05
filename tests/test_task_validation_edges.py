import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tasks import create_tasks_app, _validate_edit


class TestTaskValidationEdges(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_tasks_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": str(Path(self.temp_dir.name) / "users.db"),
        })
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()
        self.temp_dir.cleanup()

    def test_zero_recurrence_interval(self):
        clean, error = _validate_edit(
            {"title": "Test task", "recurrence_interval": 0},
            creating=True
        )
        self.assertIsNotNone(error)

    def test_negative_recurrence_interval(self):
        clean, error = _validate_edit(
            {"title": "Test task", "recurrence_interval": -1},
            creating=True
        )
        self.assertIsNotNone(error)

    def test_boolean_recurrence_interval(self):
        clean, error = _validate_edit(
            {"title": "Test task", "recurrence_interval": True},
            creating=True
        )
        self.assertIsNotNone(error)

    def test_whitespace_title(self):
        clean, error = _validate_edit(
            {"title": "   "},
            creating=True
        )
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()