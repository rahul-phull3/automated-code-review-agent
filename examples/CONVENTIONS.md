# Example Python conventions

- Use the logging module instead of print statements in application code.
- Do not catch Exception without logging or re-raising the error.
- Never use mutable default arguments.
- Functions that access external resources must use explicit timeouts where supported.
- Keep credentials in environment variables or a secret manager, never source code.
