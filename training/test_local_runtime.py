"""Passage selection never lets model output invent source coordinates or quotes."""

import json
import unittest

from local_runtime_server import Rejected, Runtime


EVIDENCE = [{"id": "E1", "path": "src/example.py", "start_line": 1,
             "end_line": 2, "commit_sha": "a" * 40,
             "text": "def answer():\n    return 42\n"}]
REQUEST = {"instructions": "Cite exact source lines.",
           "question": "What does answer return?", "evidence": EVIDENCE}
VALID = '{"claims":[{"text":"answer returns 42","passage_id":"P01"}]}'


class PassageSelectionTests(unittest.TestCase):
    def test_server_derives_exact_quote_and_coordinates(self):
        passages = Runtime._passages(EVIDENCE)
        output = Runtime._check_selection(VALID, passages)
        citation = output["claims"][0]["citations"][0]
        self.assertEqual(citation, {"evidence_id": "E1", "start_line": 1,
                                    "end_line": 2,
                                    "quote": "def answer():\n    return 42"})

    def test_unknown_reused_and_conflicting_ids_reject(self):
        passages = Runtime._passages(EVIDENCE)
        for claims in (
            [{"text": "wrong", "passage_id": "P99"}],
            [{"text": "a", "passage_id": "P01"},
             {"text": "b", "passage_id": "P01"}],
            [{"text": "wrong", "passage_id": "P01", "quote": "fake"}],
        ):
            with self.subTest(claims=claims), self.assertRaises(Rejected):
                Runtime._check_selection(json.dumps({"claims": claims}), passages)
        with self.assertRaises(Rejected):
            Runtime._check_selection(
                '{"claims":[],"claims":[{"text":"a","passage_id":"P01"}]}',
                passages)

    def test_one_repair_accepts_valid_second_generation(self):
        runtime = Runtime.__new__(Runtime)
        replies = iter(("not json", VALID))
        calls = []

        def generate(messages):
            calls.append(messages)
            return next(replies)

        runtime._generate = generate
        result = runtime.answer(REQUEST)
        self.assertEqual(result["claims"][0]["citations"][0]["quote"],
                         "def answer():\n    return 42")
        self.assertEqual(len(calls), 2)

    def test_two_invalid_generations_reject_without_fallback(self):
        runtime = Runtime.__new__(Runtime)
        calls = []

        def generate(messages):
            calls.append(messages)
            return "not json"

        runtime._generate = generate
        with self.assertRaises(Rejected):
            runtime.answer(REQUEST)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
