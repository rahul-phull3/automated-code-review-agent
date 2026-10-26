# Automated Code Review Agent

Implementation in progress, delivered in tested milestones.

A Python agent for reviewing Git repositories against Markdown coding conventions, with exact file/line findings. Supports OpenAI and Anthropic through replaceable provider adapters.

Architecture: immutable Git snapshot -> numbered conventions -> bounded review and context loop -> verification -> evidence validation -> Markdown/JSON/SARIF -> optional GitHub PR comments.

The initial foundation validates source and convention citations and reads committed Git objects without executing repository code. Upcoming milestones add provider integrations, reporting, CLI, tests and a full operating guide.
