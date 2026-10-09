import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from email.message import Message
from io import BytesIO

from factory import Factory, FactoryError, evaluate, github_evidence, parse_pr, handler


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.pr = {"url": "https://github.com/acme/app/pull/1", "headRefOid": "abc123",
                   "state": "OPEN", "isDraft": True, "mergeable": "MERGEABLE", "reviewDecision": ""}
        self.checks = [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
        self.reviews = [{"id": "r1", "reviewId": "reviewer1", "prUrl": self.pr["url"], "targetSha": "abc123",
                         "status": "complete", "verdict": "approved", "createdAt": "2026-10-09T12:00:00Z"}]

    def gate(self, **overrides):
        args = dict(pr=self.pr, checks=self.checks, threads=[], reviews=self.reviews, required=["test"])
        args.update(overrides)
        return evaluate(**args)

    def test_current_commit_success_is_handoff_ready(self):
        result = self.gate()
        self.assertTrue(result["ready"])
        self.assertTrue(result["draft"])
        self.assertEqual(result["approvedReviewRuns"], ["r1"])

    def test_each_unproven_boundary_blocks(self):
        changes = [dict(required=[]), dict(checks=[]), dict(reviews=[]),
                   dict(threads=[{"isResolved": False}]),
                   dict(pr={**self.pr, "mergeable": "UNKNOWN"}),
                   dict(pr={**self.pr, "state": "CLOSED"}),
                   dict(pr={**self.pr, "headRefOid": "new-head"}),
                   dict(pr={**self.pr, "reviewDecision": None, "outstandingChangeRequests": ["reviewer"]}),
                   dict(pr={**self.pr, "reviewDecision": "CHANGES_REQUESTED"})]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(self.gate(**change)["ready"])

    def test_failure_pending_skipped_neutral_and_unknown_do_not_pass(self):
        for status, conclusion in [("COMPLETED", "FAILURE"), ("IN_PROGRESS", "SUCCESS"),
                                    ("COMPLETED", "SKIPPED"), ("COMPLETED", "NEUTRAL"), (None, None)]:
            with self.subTest(status=status, conclusion=conclusion):
                self.assertFalse(self.gate(checks=[{**self.checks[0], "status": status, "conclusion": conclusion}])["ready"])

    def test_optional_failed_check_blocks_even_with_required_green(self):
        self.assertFalse(self.gate(checks=self.checks + [{"name": "security", "state": "FAILURE"}])["ready"])

    def test_status_context_success_supported(self):
        self.assertTrue(self.gate(checks=[{"__typename": "StatusContext", "context": "test", "state": "SUCCESS"}])["ready"])

    def test_approval_from_different_pr_never_counts(self):
        self.assertFalse(self.gate(reviews=[{**self.reviews[0], "prUrl": "https://github.com/acme/other/pull/1"}])["ready"])

    def test_rerun_supersedes_previous_approval(self):
        for status, verdict in [("running", ""), ("failed", ""), ("complete", "changes_requested"), ("complete", "")]:
            later = {**self.reviews[0], "id": "r2", "createdAt": "2026-10-09T13:00:00Z", "status": status, "verdict": verdict}
            with self.subTest(status=status, verdict=verdict):
                self.assertFalse(self.gate(reviews=self.reviews + [later])["ready"])

    def test_other_reviewer_change_request_blocks(self):
        review = {**self.reviews[0], "id": "r2", "reviewId": "reviewer2", "verdict": "changes_requested"}
        self.assertFalse(self.gate(reviews=self.reviews + [review])["ready"])

    def test_resolved_threads_and_delivered_review_pass(self):
        self.assertTrue(self.gate(threads=[{"isResolved": True}], reviews=[{**self.reviews[0], "status": "delivered"}])["ready"])

    def test_all_input_facts_unchanged(self):
        before = copy.deepcopy((self.pr, self.checks, self.reviews))
        self.gate()
        self.assertEqual(before, (self.pr, self.checks, self.reviews))


class IntegrationBoundaryTests(unittest.TestCase):
    def test_supervisor_rejects_cross_origin_and_missing_csrf_before_dispatch(self):
        factory = MagicMock()
        Handler = handler(factory, 48080)
        for headers in [
            {"Host": "evil.test"},
            {"Host": "127.0.0.1:48080", "Origin": "https://evil.test"},
            {"Host": "127.0.0.1:48080", "Origin": "http://127.0.0.1:48080"},
            {"Host": "127.0.0.1:48080", "X-Factory-Token": "wrong"},
        ]:
            with self.subTest(headers=headers):
                instance = object.__new__(Handler)
                instance.headers = Message()
                for key, value in headers.items():
                    instance.headers[key] = value
                instance.reply = MagicMock()
                instance.do_POST()
                self.assertEqual(instance.reply.call_args.args[1], 403)
                factory.spawn.assert_not_called()
                factory.add.assert_not_called()

    def test_supervisor_accepts_same_origin_token_and_dispatches_exact_task(self):
        factory = MagicMock()
        Handler = handler(factory, 48080)
        instance = object.__new__(Handler)
        instance.headers = Message()
        instance.headers["Host"] = "127.0.0.1:48080"
        instance.reply = MagicMock()
        instance.path = "/api/state"
        instance.do_GET()
        token = instance.reply.call_args.args[0]["token"]
        body = {"projectId": "test", "prompt": "Do the task", "requestId": "stable-request"}
        raw = json.dumps(body).encode()
        instance.headers["X-Factory-Token"] = token
        instance.headers["Origin"] = "http://127.0.0.1:48080"
        instance.headers["Content-Length"] = str(len(raw))
        instance.rfile = BytesIO(raw)
        instance.path = "/api/spawn"
        instance.do_POST()
        factory.spawn.assert_called_once_with(body)

    def test_pr_url_cannot_inject_cli_arguments(self):
        self.assertEqual(parse_pr("https://github.com/acme/app/pull/23"), ("acme/app", 23))
        for value in ["file:///tmp/x", "https://github.com/acme/app/pull/1;id", "https://evil.test/acme/app/pull/1", "--help"]:
            with self.assertRaises(FactoryError):
                parse_pr(value)

    def test_onboarding_configures_native_engine_and_keeps_policy(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            with patch.object(factory, "api", return_value={"project": {"id": "sample"}}) as native:
                factory.add({"path": root, "requiredChecks": ["test", "lint", "test"]})
            path, body = native.call_args.args
            self.assertEqual(path, "/api/v1/projects")
            self.assertTrue(body["config"]["autoReview"])
            self.assertTrue(body["config"]["workersRequestReview"])
            self.assertEqual(body["config"]["reviewers"][0]["harness"], "codex")
            self.assertEqual(factory.policies()["sample"]["requiredChecks"], ["test", "lint"])

    def test_missing_check_policy_blocks_onboarding_before_native_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            with patch.object(factory, "api") as native:
                with self.assertRaises(FactoryError):
                    factory.add({"path": root, "requiredChecks": []})
                native.assert_not_called()

    def test_dispatch_forwards_stable_retry_key(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            factory.save_policy("sample", {"harness": "codex"})
            with patch.object(factory, "api", return_value={"session": {"id": "sample-1"}}) as native:
                factory.spawn({"projectId": "sample", "prompt": "Fix regression", "requestId": "stable-request"})
                body = native.call_args.args[1]
                self.assertEqual(body["clientRequestId"], "stable-request")
                self.assertEqual(body["mode"], "chat")
                self.assertNotEqual(body["approvalMode"], "bypass-permissions")

    def test_native_failed_create_never_saves_factory_policy(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            with patch.object(factory, "api", side_effect=FactoryError("bad repository")):
                with self.assertRaises(FactoryError):
                    factory.add({"path": root, "requiredChecks": ["test"]})
            self.assertEqual(factory.policies(), {})

    def test_github_evidence_pages_threads_and_checks_and_rejects_head_change(self):
        pr = {"headRefOid": "abc"}
        def response(field, page):
            return {"data": {"repository": {"pullRequest": {"headRefOid": "abc", field: page}}}}
        threads1 = {"nodes": [{"isResolved": True}], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}
        threads2 = {"nodes": [{"isResolved": False}], "pageInfo": {"hasNextPage": False}}
        def checks_page(name, more):
            return response("commits", {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {
                "nodes": [{"name": name}], "pageInfo": {"hasNextPage": more, "endCursor": "next"}}}}}]})
        review_page = {"nodes": [
            {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-10-08"},
            {"author": {"login": "alice"}, "state": "COMMENTED", "submittedAt": "2026-10-09"}],
            "pageInfo": {"hasNextPage": False}}
        with patch("factory.run_json", side_effect=[pr, response("reviewThreads", threads1), response("reviewThreads", threads2), checks_page("first", True), checks_page("late-failure", False), response("reviews", review_page)]) as gh:
            _, checks, threads = github_evidence("https://github.com/acme/app/pull/1")
            self.assertEqual([c["name"] for c in checks], ["first", "late-failure"])
            self.assertEqual(len(threads), 2)
            self.assertEqual(gh.call_count, 6)
            self.assertEqual(pr["outstandingChangeRequests"], ["alice"])
        changed = response("reviewThreads", threads1)
        changed["data"]["repository"]["pullRequest"]["headRefOid"] = "new"
        with patch("factory.run_json", side_effect=[pr, changed]):
            with self.assertRaisesRegex(FactoryError, "head changed"):
                github_evidence("https://github.com/acme/app/pull/1")

    def test_gate_rechecks_head_after_collecting_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            with patch.object(factory, "api", side_effect=[{"session": {"projectId": "sample"}}, {"runs": []}]), \
                 patch("factory.github_evidence", return_value=({"headRefOid": "old"}, [], [])), \
                 patch("factory.run_json", return_value={"headRefOid": "new"}):
                with self.assertRaisesRegex(FactoryError, "head changed"):
                    factory.gate("sample-1", "https://github.com/acme/app/pull/1")


if __name__ == "__main__":
    unittest.main()
