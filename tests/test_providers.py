import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from review_agent.providers import Provider, ProviderError, request_json


class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    @patch("review_agent.providers.request_json")
    def test_openai_contract(self, request):
        request.return_value = {"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"findings":[]}'}]}],
            "usage": {"input_tokens": 12, "output_tokens": 4}}
        p = Provider("openai", "chosen-model", 1)
        self.assertEqual(p.complete("system", {}, {}), {"findings": []})
        payload = request.call_args.args[2]
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(p.usage["input_tokens"], 12)
        with self.assertRaises(ProviderError):
            p.complete("system", {}, {})

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"})
    @patch("review_agent.providers.request_json")
    def test_anthropic_contract_and_truncation(self, request):
        request.return_value = {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": '{"findings":[]}'}]}
        p = Provider("anthropic", "chosen-model")
        self.assertEqual(p.complete("system", {}, {}), {"findings": []})
        self.assertEqual(request.call_args.args[2]["output_config"]["format"]["type"], "json_schema")
        request.return_value = {"stop_reason": "max_tokens"}
        with self.assertRaises(ProviderError):
            p.complete("system", {}, {})

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    @patch("review_agent.providers.request_json")
    def test_refusal(self, request):
        request.return_value = {"status": "completed", "output": [
            {"type": "message", "content": [{"type": "refusal"}]}]}
        with self.assertRaises(ProviderError):
            Provider("openai", "model").complete("system", {}, {})

    @patch("review_agent.providers.time.sleep")
    @patch("review_agent.providers.urllib.request.urlopen")
    def test_retry_and_no_write_retry(self, urlopen, sleep):
        error = HTTPError("https://example.com", 429, "busy", {}, None)
        urlopen.side_effect = [error, io.BytesIO(b'{"ok":true}')]
        self.assertEqual(request_json("https://example.com", {}), {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        urlopen.reset_mock()
        urlopen.side_effect = error
        with self.assertRaises(ProviderError):
            request_json("https://example.com", {}, {}, retry=False)
        self.assertEqual(urlopen.call_count, 1)
