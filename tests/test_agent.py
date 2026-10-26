import unittest
from review_agent.agent import Config, review
from review_agent.providers import ProviderError
from review_agent.source import Snapshot
from test_source import finding


class Scripted:
    name, model = "fixture", "offline"
    usage = {}
    def __init__(self, outputs, max_calls=100):
        self.outputs, self.calls, self.max_calls = iter(outputs), 0, max_calls
        self.inputs = []
    def complete(self, system, data, schema):
        if self.calls >= self.max_calls:
            raise ProviderError("Model call budget exhausted")
        self.calls += 1
        self.inputs.append(data.copy())
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return result


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.snap = Snapshot("a" * 40, {"app.py": ["print(1)"]}, {})

    def test_verified_finding_and_context(self):
        f = finding()
        provider = Scripted([
            {"requests": [{"path": "app.py", "start_line": 1, "end_line": 1}], "findings": []},
            {"requests": [], "findings": [f, f]},
            {"findings": [f, f]}])
        result = review(self.snap, "Use logging.", provider)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["findings"]), 1)
        self.assertIn("1: print(1)", provider.inputs[1]["context"][0]["source"])

    def test_fabricated_evidence_rejected(self):
        f = {**finding(), "evidence": "invented"}
        result = review(self.snap, "Use logging.", Scripted([{"requests": [], "findings": [f]}]))
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["rejected_findings"], 1)

    def test_verifier_cannot_invent_findings(self):
        f = finding()
        provider = Scripted([{"requests": [], "findings": [f]},
                             {"findings": [{**f, "message": "invented"}]}])
        self.assertEqual(review(self.snap, "Use logging.", provider)["findings"], [])

    def test_failures_are_incomplete(self):
        for outputs in [[ProviderError("rate limited")],
                        [{"requests": [], "findings": [finding()]}, ProviderError("verification failed")]]:
            result = review(self.snap, "Use logging.", Scripted(outputs))
            self.assertFalse(result["complete"])
            self.assertEqual(result["findings"], [])

    def test_context_budget_and_path_escape(self):
        request = {"requests": [{"path": "../secret", "start_line": 1, "end_line": 1}], "findings": []}
        provider = Scripted([request, request])
        result = review(self.snap, "Use logging.", provider, Config(context_rounds=1))
        self.assertFalse(result["complete"])
        self.assertEqual(provider.inputs[1]["context"][0], {"error": "Invalid or unavailable context range"})

    def test_chunk_budget_and_empty_repository(self):
        snap = Snapshot("a", {"a.py": ["a", "b"]}, {})
        result = review(snap, "Rule", Scripted([{"requests": [], "findings": []}]),
                        Config(chunk_lines=1, max_chunks=1))
        self.assertFalse(result["complete"])
        self.assertEqual(result["coverage"]["total_chunks"], 2)
        self.assertFalse(review(Snapshot("a", {}, {}), "Rule", Scripted([]))["complete"])

    def test_convention_size_and_config_validation(self):
        with self.assertRaises(ValueError):
            Config(chunk_lines=0)
        with self.assertRaises(ValueError):
            review(self.snap, "", Scripted([]))
        with self.assertRaises(ValueError):
            review(self.snap, "x" * 60001, Scripted([]))
