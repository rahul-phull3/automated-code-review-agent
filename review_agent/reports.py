"""Portable review artifacts."""
import html
import json
from pathlib import Path
from urllib.parse import quote


def safe(text):
    return html.escape(str(text)).replace("@", "@\u200b")


def markdown(report):
    state = "Complete within configured scope" if report["complete"] else "INCOMPLETE"
    c = report["coverage"]
    output = [f"# Code review: {state}", "",
              f"Commit: {report['commit']}", "",
              f"Reviewed {c['reviewed_chunks']}/{c['total_chunks']} chunks; "
              f"{len(report['findings'])} findings; {len(report['skipped'])} skipped files.", "",
              "AI findings require human review. See JSON for full coverage and errors.", ""]
    for f in report["findings"]:
        location = f"{f['path']}:{f['start_line']}-{f['end_line']}"
        output += [f"## {safe(f['severity'].upper())}: {safe(f['title'])}",
                   f"**{safe(location)}** · {f['category']} · confidence {f['confidence']}", "",
                   safe(f["message"]), "", f"Suggestion: {safe(f['suggestion'])}", "",
                   "<pre>" + safe(f["evidence"]) + "</pre>", ""]
        if f["category"] == "convention":
            output += [f"Convention lines {f['convention_start']}-{f['convention_end']}:",
                       "<pre>" + safe(f["convention_quote"]) + "</pre>", ""]
    if not report["findings"]:
        output += ["No accepted findings. This is not a guarantee of code correctness.", ""]
    for error in report["errors"]:
        output += [f"- Error at {safe(error['path'])}:{error['start_line']}: {safe(error['error'])}"]
    if report["skipped"]:
        output += ["", "## Skipped files", ""]
        output += [f"- {safe(p)}: {safe(reason)}" for p, reason in report["skipped"].items()]
    return "\n".join(output) + "\n"


def sarif(report):
    results = []
    for f in report["findings"]:
        results.append({"ruleId": f["category"], "level": f["severity"],
                        "message": {"text": f["title"] + ": " + f["message"]},
                        "partialFingerprints": {"reviewAgent/v1": f["fingerprint"]},
                        "locations": [{"physicalLocation": {
                            "artifactLocation": {"uri": quote(f["path"], safe="/")},
                            "region": {"startLine": f["start_line"], "endLine": f["end_line"]}
                        }}],
                        "properties": {"confidence": f["confidence"],
                                       "suggestion": f["suggestion"],
                                       "conventionStart": f["convention_start"],
                                       "conventionEnd": f["convention_end"]}})
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "review-agent", "version": "0.1.0",
                        "rules": [{"id": "convention"}, {"id": "quality"}]}},
                      "invocations": [{"executionSuccessful": report["complete"]}],
                      "results": results, "properties": {"commit": report["commit"],
                                                         "coverage": report["coverage"]}}]}


def write_reports(report, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for name, data in (("review.json", report), ("review.sarif", sarif(report))):
        (root / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "review.md").write_text(markdown(report), encoding="utf-8")
