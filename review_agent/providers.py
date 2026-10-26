"""Small REST adapters with bounded retry; no third-party runtime dependencies."""
import json
import os
import time
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def request_json(url, headers, payload=None, method=None, retry=True):
    data = None if payload is None else json.dumps(payload).encode()
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if retry and exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"Remote API returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("Remote API connection failed") from None
        except (ValueError, UnicodeError):
            raise ProviderError("Remote API returned invalid JSON") from None
    raise ProviderError("Retry limit reached")


class Provider:
    def __init__(self, name, model, max_calls=100):
        self.name, self.model = name, model
        self.max_calls, self.calls = max_calls, 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        variable = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[name]
        self.key = os.environ.get(variable)
        if not self.key:
            raise ProviderError(f"Set {variable} in your environment")

    def complete(self, system, data, schema):
        if self.calls >= self.max_calls:
            raise ProviderError("Model call budget exhausted")
        self.calls += 1
        prompt = json.dumps(data, ensure_ascii=False)
        if self.name == "openai":
            response = request_json("https://api.openai.com/v1/responses",
                {"Authorization": f"Bearer {self.key}"},
                {"model": self.model, "store": False, "instructions": system,
                 "input": prompt, "max_output_tokens": 6000,
                 "text": {"format": {"type": "json_schema", "name": "review",
                                    "strict": True, "schema": schema}}})
            if response.get("status") != "completed":
                raise ProviderError("OpenAI response incomplete")
            blocks = [b for o in response.get("output", []) if o.get("type") == "message"
                      for b in o.get("content", [])]
            if any(b.get("type") == "refusal" for b in blocks):
                raise ProviderError("Model declined the review")
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "output_text")
        else:
            response = request_json("https://api.anthropic.com/v1/messages",
                {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                {"model": self.model, "max_tokens": 6000, "system": system,
                 "messages": [{"role": "user", "content": prompt}],
                 "output_config": {"format": {"type": "json_schema", "schema": schema}}})
            if response.get("stop_reason") != "end_turn":
                raise ProviderError("Anthropic response incomplete or declined")
            text = "".join(b.get("text", "") for b in response.get("content", [])
                           if b.get("type") == "text")
        usage = response.get("usage", {})
        for key in self.usage:
            self.usage[key] += usage.get(key, 0)
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            raise ProviderError("Model returned invalid structured content") from None
