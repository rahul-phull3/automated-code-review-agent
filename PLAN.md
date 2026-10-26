# Delivery plan

1. Foundation: immutable Git snapshots, exclusions and resource limits, evidence-grounded file/line findings; test and publish.
2. Agent: provider-neutral inspect/context/review/verify loop, OpenAI and Anthropic adapters, structured outputs, retries and failure handling.
3. Delivery: Markdown/JSON/SARIF, commit-aware GitHub PR publishing, CLI, CI, examples and detailed README; test and publish.

Architecture: CLI -> Git snapshot -> numbered conventions -> chunk scheduler -> agent -> bounded context reader -> verifier -> deterministic validation -> exporters -> optional GitHub publisher.

Code is untrusted data and is never executed. Findings cite exact source excerpts and one-based ranges. Convention findings cite original Markdown lines. Partial reviews are never reported as clean. Both providers use an explicitly selected model. Offline tests do not imply live-model validation.

Approved destination: rahul-phull3/automated-code-review-agent. Push stable tested milestones during implementation.
