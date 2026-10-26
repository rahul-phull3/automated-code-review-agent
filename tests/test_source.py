import subprocess
import tempfile
import unittest
from pathlib import Path
from review_agent.source import Snapshot, snapshot, validate_finding


def finding():
    return dict(path="app.py", start_line=1, end_line=1, evidence="print(1)",
                severity="warning", confidence=0.95, title="Avoid print", message="Use logger",
                suggestion="Use logger.info", category="convention", convention_start=1,
                convention_end=1, convention_quote="Use logging.")


class SourceTests(unittest.TestCase):
    def test_evidence_and_rule_validation(self):
        snap = Snapshot("a", {"app.py": ["print(1)"]}, {})
        self.assertTrue(validate_finding(finding(), snap, ["Use logging."], .8))
        for key, value in [("path", "../secret"), ("start_line", 0), ("end_line", 9),
                           ("evidence", "invented"), ("convention_quote", "invented"),
                           ("confidence", float("nan")), ("start_line", True)]:
            f = finding()
            f[key] = value
            self.assertFalse(validate_finding(f, snap, ["Use logging."], .8))

    def test_snapshot_uses_commit_not_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(*args):
                return subprocess.run(["git", "-C", directory, *args], check=True, capture_output=True)
            run("init")
            (root / "app.py").write_text("print(1)\n")
            (root / ".env").write_text("SECRET=value")
            run("add", ".")
            run("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "fixture")
            (root / "app.py").write_text("changed")
            snap = snapshot(root)
            self.assertEqual(snap.files["app.py"], ["print(1)"])
            self.assertEqual(snap.skipped[".env"], "excluded")


if __name__ == "__main__":
    unittest.main()
