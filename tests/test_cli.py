import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from review_agent.cli import main
from test_agent import Scripted


class CliTests(unittest.TestCase):
    def test_full_offline_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", directory], check=True, capture_output=True)
            (root / "app.py").write_text("print(1)\n")
            subprocess.run(["git", "-C", directory, "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", directory, "-c", "user.name=Test", "-c",
                            "user.email=test@example.com", "commit", "-m", "fixture"],
                           check=True, capture_output=True)
            conventions = root / "conventions.md"
            conventions.write_text("Use logging.")
            args = ["review", directory, "--conventions", str(conventions), "--provider", "openai",
                    "--model", "fixture", "--output", str(root / "reports")]
            with patch("review_agent.cli.Provider", return_value=Scripted([
                    {"requests": [], "findings": []}])), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            report = json.loads((root / "reports/review.json").read_text())
            self.assertTrue(report["complete"])
            sarif = json.loads((root / "reports/review.sarif").read_text())
            self.assertEqual(sarif["version"], "2.1.0")
            self.assertTrue((root / "reports/review.md").exists())
            with patch("review_agent.cli.Provider") as provider, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ["--inventory-only"]), 0)
                provider.assert_not_called()
