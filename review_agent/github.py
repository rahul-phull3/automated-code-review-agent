"""Explicit PR publishing, immutable commit anchors and sequential-run deduplication."""
import hashlib
import json
import os
import re
from .providers import request_json
from .reports import safe


def added_lines(patch):
    """Map only added RIGHT-side lines, avoiding ambiguous cross-hunk ranges."""
    result, line = set(), None
    for row in patch.splitlines():
        match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
        if match:
            line = int(match.group(1))
        elif line is not None:
            if row.startswith("+"):
                result.add(line)
                line += 1
            elif row.startswith(" "):
                line += 1
    return result


class GitHub:
    def __init__(self, repository, pr):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or pr < 1:
            raise ValueError("Expected owner/repository and positive PR number")
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("Set GITHUB_TOKEN to publish")
        self.base = f"https://api.github.com/repos/{repository}/pulls/{pr}"
        self.headers = {"Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def get(self, suffix=""):
        return request_json(self.base + suffix, self.headers)

    def pages(self, suffix):
        items = []
        for page in range(1, 101):
            batch = self.get(f"{suffix}?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ValueError("Unexpected GitHub response")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ValueError("GitHub pagination budget exceeded")

    def publish(self, report):
        if not report.get("complete"):
            raise ValueError("Refusing to publish an incomplete review")
        pr = self.get()
        if pr["state"] != "open" or pr["head"]["sha"] != report["commit"]:
            raise ValueError("PR closed or head changed; rerun review against current PR head")
        digest = hashlib.sha256(json.dumps(
            [report["commit"], report["conventions_sha256"], report["findings"]],
            sort_keys=True).encode()).hexdigest()[:24]
        marker = f"<!-- review-agent:{digest} -->"
        reviews = self.pages("/reviews")
        if any(marker in (r.get("body") or "") for r in reviews):
            return {"status": "already-published"}
        changed = self.pages("/files")
        if len(changed) != pr["changed_files"]:
            raise ValueError("GitHub file listing is incomplete; cannot safely publish")
        eligible = {f["filename"]: added_lines(f.get("patch", "")) for f in changed}
        previous = self.pages("/comments")
        comments, outside, duplicate = [], 0, 0
        for f in report["findings"]:
            key = f"<!-- review-agent-finding:{report['commit']}:{f['fingerprint']} -->"
            if any(key in (c.get("body") or "") for c in previous):
                duplicate += 1
                continue
            if f["start_line"] not in eligible.get(f["path"], set()) or len(comments) >= 50:
                outside += 1
                continue
            body = (f"**{safe(f['severity'])}: {safe(f['title'])}**\n\n"
                    f"{safe(f['message'])}\n\nSuggestion: {safe(f['suggestion'])}\n\n"
                    f"Source range: {f['start_line']}-{f['end_line']}. "
                    f"Category: {f['category']}; confidence: {f['confidence']}.")
            if f["category"] == "convention":
                body += (f"\n\nConvention lines {f['convention_start']}-{f['convention_end']}: "
                         + safe(f["convention_quote"]))
            comments.append({"path": f["path"], "line": f["start_line"],
                             "side": "RIGHT", "body": body + "\n\n" + key})
        # Check again immediately before writing. GitHub anchors comments to commit_id.
        if self.get()["head"]["sha"] != report["commit"]:
            raise ValueError("PR head changed during publication")
        payload = {"commit_id": report["commit"], "event": "COMMENT",
                   "body": (f"AI convention/code-quality review: {len(report['findings'])} findings. "
                            f"{len(comments)} inline; {outside} outside added lines or comment cap; "
                            f"{duplicate} previously published. Full locations are in the review artifacts. "
                            f"{len(report['skipped'])} files excluded. Human review required.\n\n{marker}"),
                   "comments": comments}
        # No write retries: a timeout could mean GitHub already accepted the review.
        response = request_json(self.base + "/reviews", self.headers, payload, retry=False)
        return {"status": "published", "url": response.get("html_url"),
                "inline_comments": len(comments), "report_only": outside}
