import os
import unittest
from unittest.mock import patch
from review_agent.github import GitHub, added_lines
from test_source import finding


class GitHubTests(unittest.TestCase):
    def test_diff_lines(self):
        self.assertEqual(added_lines("@@ -1,2 +1,3 @@\n old\n-deleted\n+new\n+second\n"), {2, 3})
        self.assertEqual(added_lines("@@ -1 +1 @@\n-a\n+b\n@@ -9 +9 @@\n-c\n+d"), {1, 9})

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test"})
    @patch("review_agent.github.request_json")
    def test_publish_commit_and_duplicate(self, request):
        f = {**finding(), "fingerprint": "finger"}
        report = {"complete": True, "commit": "a" * 40, "conventions_sha256": "x",
                  "findings": [f], "skipped": {}}
        pr = {"state": "open", "head": {"sha": report["commit"]}, "changed_files": 1}
        request.side_effect = [pr, [], [{"filename": "app.py", "patch": "@@ -0,0 +1 @@\n+print(1)"}],
                               [], pr, {"html_url": "url"}]
        gh = GitHub("owner/repo", 1)
        result = gh.publish(report)
        self.assertEqual(result["inline_comments"], 1)
        payload = request.call_args.args[2]
        self.assertEqual(payload["commit_id"], report["commit"])
        self.assertEqual(payload["comments"][0]["line"], 1)
        self.assertFalse(request.call_args.kwargs["retry"])
        request.side_effect = [pr, [{"body": payload["body"]}]]
        self.assertEqual(gh.publish(report)["status"], "already-published")

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test"})
    @patch("review_agent.github.request_json")
    def test_stale_or_incomplete_report(self, request):
        gh = GitHub("owner/repo", 1)
        with self.assertRaises(ValueError):
            gh.publish({"complete": False})
        request.assert_not_called()
        request.return_value = {"state": "open", "head": {"sha": "new"}}
        with self.assertRaises(ValueError):
            gh.publish({"complete": True, "commit": "old"})
