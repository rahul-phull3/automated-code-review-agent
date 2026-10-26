"""Read immutable Git objects; never execute reviewed code."""
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import hashlib
import subprocess


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, timeout=60,
        check=False,
    )
    if result.returncode:
        raise ValueError("Git operation failed; verify repository and revision")
    return result.stdout


@dataclass
class Snapshot:
    commit: str
    files: dict[str, list[str]]
    skipped: dict[str, str]


EXCLUDED = {"node_modules", "vendor", "dist", "build", ".git", ".venv", "__pycache__"}


def snapshot(root: Path, ref: str = "HEAD", excludes: tuple[str, ...] = (),
             max_file_bytes: int = 150_000, max_total_bytes: int = 5_000_000) -> Snapshot:
    commit = git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    records = git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    files, skipped, total = {}, {}, 0
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        try:
            path = raw_path.decode("utf-8")
        except UnicodeError:
            skipped[repr(raw_path)] = "non-UTF-8 path"
            continue
        parts = path.split("/")
        if mode not in {"100644", "100755"} or kind != "blob":
            skipped[path] = "symlink or submodule"
            continue
        if (any(p in EXCLUDED for p in parts) or any(fnmatch(path, p) for p in excludes)
                or any(p.startswith(".env") for p in parts)
                or path.lower().endswith((".pem", ".key", ".p12", ".lock", "package-lock.json"))):
            skipped[path] = "excluded"
            continue
        size = int(git(root, "cat-file", "-s", oid))
        if size > max_file_bytes or total + size > max_total_bytes:
            skipped[path] = "size budget"
            continue
        data = git(root, "cat-file", "blob", oid)
        try:
            text = data.decode("utf-8")
            if "\0" in text:
                raise UnicodeError()
        except UnicodeError:
            skipped[path] = "binary or non-UTF-8"
            continue
        files[path] = text.splitlines()
        total += size
    return Snapshot(commit, files, skipped)


def numbered(lines: list[str], start: int = 1) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(lines, start))


def validate_finding(f: dict, snap: Snapshot, conventions: list[str], confidence: float) -> bool:
    try:
        lines = snap.files[f["path"]]
        start, end = f["start_line"], f["end_line"]
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            return False
        if f["evidence"] != "\n".join(lines[start - 1:end]) or not f["evidence"].strip():
            return False
        if f["severity"] not in {"error", "warning", "note"}:
            return False
        if type(f["confidence"]) not in {int, float} or not confidence <= f["confidence"] <= 1:
            return False
        if not all(isinstance(f[k], str) and f[k].strip() for k in ("title", "message", "suggestion")):
            return False
        a, b = f["convention_start"], f["convention_end"]
        if type(a) is not int or type(b) is not int:
            return False
        if f["category"] == "convention":
            return (1 <= a <= b <= len(conventions)
                    and f["convention_quote"] == "\n".join(conventions[a-1:b])
                    and bool(f["convention_quote"].strip()))
        return f["category"] == "quality" and a == b == 0 and f["convention_quote"] == ""
    except (KeyError, TypeError, IndexError):
        return False


def fingerprint(f: dict) -> str:
    key = [f[k] for k in ("path", "start_line", "end_line", "category", "title")]
    return hashlib.sha256(repr(key).encode()).hexdigest()[:20]
