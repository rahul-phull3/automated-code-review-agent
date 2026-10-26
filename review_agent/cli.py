"""Command-line entry points."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from .agent import Config, review
from .github import GitHub
from .providers import Provider, ProviderError
from .reports import write_reports
from .source import snapshot


@contextmanager
def repository(source):
    if source.startswith("https://"):
        url = urlsplit(source)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTPS Git URL without credentials, query or fragment")
        with tempfile.TemporaryDirectory(prefix="review-agent-") as directory:
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "clone", "--bare", "--", source, directory],
                capture_output=True, timeout=180,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if result.returncode:
                raise ValueError("Clone failed; for private repositories use a local authenticated clone")
            yield Path(directory)
    else:
        root = Path(source).resolve()
        if not root.is_dir():
            raise ValueError("Repository directory does not exist")
        yield root


def parser():
    p = argparse.ArgumentParser(description="Review Git code against Markdown conventions")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("review", help="Review an immutable Git commit")
    run.add_argument("repository", help="Local Git directory or HTTPS clone URL")
    run.add_argument("--conventions", required=True, type=Path)
    run.add_argument("--provider", choices=["openai", "anthropic"], required=True)
    run.add_argument("--model", required=True, help="Model ID supporting structured JSON output")
    run.add_argument("--ref", default="HEAD")
    run.add_argument("--output", type=Path, default=Path("reports"))
    run.add_argument("--exclude", action="append", default=[], help="Repeatable repository-relative glob")
    run.add_argument("--max-calls", type=int, default=100)
    run.add_argument("--max-chunks", type=int, default=100)
    run.add_argument("--chunk-lines", type=int, default=180)
    run.add_argument("--context-rounds", type=int, default=2)
    run.add_argument("--confidence", type=float, default=.8)
    run.add_argument("--fail-on", choices=["error", "warning", "note", "none"], default="error")
    run.add_argument("--inventory-only", action="store_true", help="Inspect scope without API calls")
    pub = sub.add_parser("publish", help="Explicitly publish a completed report as a PR review")
    pub.add_argument("report", type=Path)
    pub.add_argument("--repo", required=True, help="owner/repository")
    pub.add_argument("--pr", required=True, type=int)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "publish":
            report = json.loads(args.report.read_text(encoding="utf-8"))
            print(json.dumps(GitHub(args.repo, args.pr).publish(report), indent=2))
            return 0
        cfg = Config(args.chunk_lines, args.max_chunks, args.context_rounds, args.confidence)
        if not 1 <= args.max_calls <= 10000:
            raise ValueError("--max-calls must be between 1 and 10000")
        conventions = args.conventions.read_text(encoding="utf-8-sig")
        with repository(args.repository) as root:
            snap = snapshot(root, args.ref, tuple(args.exclude))
        if args.inventory_only:
            print(json.dumps({"commit": snap.commit, "files": list(snap.files),
                              "skipped": snap.skipped}, indent=2))
            return 0
        provider = Provider(args.provider, args.model, args.max_calls)
        result = review(snap, conventions, provider, cfg)
        write_reports(result, args.output)
        print(f"{len(result['findings'])} findings; complete={result['complete']}; "
              f"reports: {args.output.resolve()}")
        if not result["complete"]:
            return 2
        severity = {"error": 3, "warning": 2, "note": 1, "none": 4}
        return int(any(severity[f["severity"]] >= severity[args.fail_on] for f in result["findings"]))
    except (ValueError, OSError, ProviderError, subprocess.TimeoutExpired, KeyError, TypeError) as exc:
        print(f"review-agent: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
