import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from observability import AuditStore, Collector, operational_eval, redact
from benchmarks import FIXTURE, grade, grade_plan, grade_review, catalog
from factory import Factory, FactoryError


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = AuditStore(self.temp.name)

    def test_concurrent_appends_are_ordered_chained_and_persistent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: self.store.append("agent", "test", {"i": i}), range(80)))
        other = AuditStore(self.temp.name)
        self.assertTrue(other.verify()["valid"])
        self.assertEqual(other.verify()["events"], 80)
        self.assertEqual(len({e["data"]["i"] for e in other.all_events()}), 80)

    def test_event_updates_and_deletes_block_and_tampering_detected(self):
        self.store.append("agent", "test", {"result": "pass"})
        with self.store.connect() as db:
            for query in ("UPDATE events SET hash='x'", "DELETE FROM events"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(query)
            db.execute("DROP TRIGGER immutable_events_update")
            db.execute("UPDATE events SET hash='x'")
        self.assertFalse(self.store.verify()["valid"])

    def test_secret_filtering_before_disk_and_export(self):
        secret = "ghp_1234567890abcdefghijk"
        self.store.append("agent", "message", {"password": "abc", "text": f"TOKEN={secret} API_KEY=xyz Bearer abcdef", "usage": {"totalTokens": 20}})
        text = json.dumps(list(self.store.all_events()))
        for raw in (secret, "xyz", "abcdef", '"abc"'):
            self.assertNotIn(raw, text)
        self.assertIn("20", text)

    def test_observation_dedup_keeps_revisions_and_return_to_prior_state(self):
        for state in ("running", "running", "complete", "running"):
            self.store.observe("agent", "turn", {"id": "t1", "state": state})
        self.assertEqual([e["data"]["state"] for e in self.store.all_events()], ["running", "complete", "running"])
        restarted = AuditStore(self.temp.name)
        self.assertIsNone(restarted.observe("agent", "turn", {"id": "t1", "state": "running"}))

    def test_subject_filters_and_cursors_never_mix_agents(self):
        for i in range(12):
            self.store.append("odd" if i % 2 else "even", "message", {"i": i})
        page = self.store.events("odd", 0, 2)
        more = self.store.events("odd", page[-1]["seq"], 20)
        self.assertEqual([e["data"]["i"] for e in page + more], list(range(1, 12, 2)))

    def test_parent_trace_and_metadata_are_in_journal(self):
        self.store.subject("orchestrator", role="orchestrator")
        self.store.subject("worker", role="worker", parentId="orchestrator")
        self.store.subject("reviewer:r1", role="reviewer", parentId="worker")
        event = self.store.append("reviewer:r1", "review.run", {"id": "run1"})
        self.assertEqual(event["traceId"], "orchestrator")
        self.assertTrue(list(self.store.all_events("worker", ["subject.metadata"])))

    def test_linked_trace_includes_other_roles_and_correlated_intent_only(self):
        self.store.subject("worker", role="worker")
        self.store.subject("reviewer:r", role="reviewer", parentId="worker")
        self.store.append("factory", "requested", {}, correlation="task")
        self.store.append("worker", "created", {}, correlation="task")
        self.store.append("reviewer:r", "review", {})
        self.store.append("unrelated", "message", {})
        trace = self.store.trace_events("reviewer:r")
        self.assertIn("factory", [e["subjectId"] for e in trace])
        self.assertIn("worker", [e["subjectId"] for e in trace])
        self.assertNotIn("unrelated", [e["subjectId"] for e in trace])

    def test_external_checkpoint_accepts_append_and_detects_tail_deletion(self):
        self.store.append("w", "created", {})
        checkpoint = self.store.verify()
        self.store.append("w", "finished", {})
        self.assertTrue(self.store.verify(checkpoint)["valid"])
        later = self.store.verify()
        with self.store.connect() as db:
            db.execute("DROP TRIGGER immutable_events_delete")
            db.execute("DELETE FROM events WHERE seq=2")
        self.assertTrue(self.store.verify()["valid"])
        self.assertFalse(self.store.verify(later)["valid"])


class CollectorTests(unittest.TestCase):
    setUp = AuditTests.setUp
    def test_history_paging_reviews_usage_and_restart_dedup(self):
        def api(path):
            if path == "/api/v1/sessions":
                return {"sessions": [{"id": "w", "kind": "worker", "harness": "codex", "projectId": "p"}]}
            if path.endswith("/reviews"):
                return {"runs": [{"id": "pass1", "reviewId": "r1", "harness": "codex", "prUrl": "https://github.com/a/b/pull/1", "targetSha": "abc", "status": "complete", "verdict": "approved"}]}
            if "/reviews/r1/" in path:
                return {"messages": [{"id": "rmessage", "text": "Reviewed"}], "hasMoreBefore": False}
            if "beforeSequence" in path:
                return {"conversationId": "c", "messages": [{"id": "old", "sequence": 1, "text": "Task"}], "hasMoreBefore": False}
            return {"conversationId": "c", "messages": [{"id": "new", "sequence": 5, "text": "Done"}],
                    "turns": [{"id": "turn1", "state": "completed"}], "activities": [{"id": "cmd1", "activityKind": "command", "detail": {"exitCode": 0, "outputMayBePartial": True}}],
                    "usage": {"totalTokens": 42}, "oldestSequence": 5, "hasMoreBefore": True}
        collector = Collector(self.store, api)
        collector.collect()
        count = self.store.verify()["events"]
        collector.collect()
        self.assertEqual(self.store.verify()["events"], count)
        self.assertEqual(len(self.store.events("w", kinds=["message"])), 2)
        reviewer = next(s for s in self.store.subjects() if s["role"] == "reviewer")
        self.assertEqual(reviewer["parentId"], "w")
        self.assertEqual(next(s for s in self.store.subjects() if s["id"] == "w")["usage"]["totalTokens"], 42)
        self.assertEqual(self.store.events("reviewer:r1", kinds=["message"])[0]["data"]["text"], "Reviewed")

    def test_missing_conversation_and_pagination_loop_mark_partial(self):
        collector = Collector(self.store, lambda _: {"hasMoreBefore": True, "oldestSequence": 3})
        collector.capture_conversation("w", "/conversation")
        self.assertEqual(self.store.subjects()[0]["conversationCoverage"], "unavailable or partial")
        self.assertTrue(self.store.events("w", kinds=["coverage.error"]))

    def test_unknown_evidence_not_success_and_revisions_not_double_counted(self):
        subject = self.store.subject("w", role="worker")
        self.assertEqual(operational_eval(self.store, subject)["status"], "unknown")
        self.store.observe("w", "turn", {"id": "t", "state": "running"})
        self.store.observe("w", "turn", {"id": "t", "state": "completed", "startedAt": "2026-10-09T10:00:00Z", "completedAt": "2026-10-09T10:00:05Z"})
        self.store.observe("w", "activity", {"id": "a", "activityKind": "command", "status": "completed", "detail": {"exitCode": 0}})
        result = operational_eval(self.store, subject)
        self.assertEqual(result["metrics"]["turns"], 1)
        self.assertEqual(result["metrics"]["completedTurnSeconds"], 5)
        self.assertEqual(result["metrics"]["costUsd"], None)


class RoleProbeTests(unittest.TestCase):
    def test_reviewer_precision_recall_penalize_false_positives_and_omissions(self):
        good = [{"function": f, "case": c, "explanation": "Concrete reproducible defect in the implementation"} for f, c in (("page", "truncation"), ("page", "invalid-bounds"), ("mean", "empty-input"))]
        checks, metrics = grade_review({"findings": good})
        self.assertTrue(all(ok for _, ok in checks))
        self.assertEqual(metrics, {"precision": 1, "recall": 1})
        checks, metrics = grade_review({"findings": good[:1] + [{"function": "is_even", "case": "parity"}]})
        self.assertEqual(metrics["precision"], .5)
        self.assertLess(metrics["recall"], 1)
        self.assertFalse(dict(checks)["No false positives"])

    def test_orchestrator_rejects_cycles_overlaps_and_missing_dependencies(self):
        plan = {"tasks": [
            {"id": "code", "files": ["sample.py"], "dependsOn": [], "acceptance": "Pagination respects every documented boundary"},
            {"id": "tests", "files": ["tests/test_page.py"], "dependsOn": ["code"], "acceptance": "All boundary regression tests pass"},
            {"id": "docs", "files": ["README.md"], "dependsOn": ["tests"], "acceptance": "Document tested behavior and usage"}]}
        self.assertTrue(all(ok for _, ok in grade_plan(plan)))
        plan["tasks"][0]["dependsOn"] = ["docs"]
        self.assertFalse(dict(grade_plan(plan))["Acyclic known dependencies"])
        plan["tasks"][0]["files"].append("README.md")
        self.assertFalse(dict(grade_plan(plan))["No overlapping file ownership"])

    def test_worker_external_assertions_reject_buggy_fixture_and_accept_fix(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "sample.py"
            p.write_text(FIXTURE)
            self.assertEqual(grade("worker", root, "")["status"], "fail")
            p.write_text(FIXTURE.replace('return items[offset:offset + limit - 1]', 'if offset < 0 or limit < 0: raise ValueError("bounds")\n    return items[offset:offset + limit]').replace('return sum(values) / len(values)', 'return sum(values) / len(values) if values else None'))
            (Path(root) / "test_sample.py").write_text("import unittest\nfrom sample import page\nclass PageTest(unittest.TestCase):\n    def test_boundary(self):\n        self.assertEqual(page([1,2,3],0,2),[1,2])\n")
            self.assertEqual(grade("worker", root, "")["status"], "pass")

    def test_catalog_stable_and_malformed_answers_never_pass(self):
        self.assertEqual(catalog()["datasetHash"], catalog()["datasetHash"])
        with self.assertRaises(ValueError):
            grade("reviewer", "/tmp", "I think it is fine")


class FactoryAuditTests(unittest.TestCase):
    def test_production_board_excludes_probe_projects_but_audit_keeps_them(self):
        from factory import handler
        from email.message import Message
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            factory.save_policy("production", {"harness": "codex"})
            def api(path):
                if path == "/healthz":
                    return {"ok": True}
                if path.endswith("projects"):
                    return {"projects": [{"id": "production"}, {"id": "probe"}]}
                return {"sessions": [{"id": "real", "projectId": "production"}, {"id": "test", "projectId": "probe"}]}
            Handler = handler(factory, 48080)
            instance = object.__new__(Handler)
            instance.headers = Message()
            instance.headers["Host"] = "127.0.0.1:48080"
            instance.reply = MagicMock()
            instance.path = "/api/state"
            with patch.object(factory, "api", side_effect=api):
                instance.do_GET()
            payload = instance.reply.call_args.args[0]
            self.assertEqual([s["id"] for s in payload["sessions"]], ["real"])
            self.assertEqual([p["id"] for p in payload["projects"]], ["production"])

    def test_probe_records_are_evaluated_as_probes_not_production_reviewers(self):
        with tempfile.TemporaryDirectory() as root:
            store = AuditStore(root)
            subject = store.subject("benchmark:b", role="reviewer", executionKind="benchmark-worker")
            store.append("benchmark:b", "benchmark.completed", {"status": "pass", "score": 1, "checks": [{"name": "Seeded defects found", "status": "pass"}]})
            report = operational_eval(store, subject)
            self.assertEqual(report["suite"], "role-probe-record-v1")
            self.assertEqual(report["status"], "pass")
            self.assertNotIn("Review is bound to a PR and commit", [c["name"] for c in report["checks"]])

    def test_mutation_success_and_failure_have_correlated_intents(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            with patch("factory.ao_request", return_value={"session": {"id": "w"}}):
                factory.api("/api/v1/sessions", {"prompt": "Do work"})
            events = list(factory.audit.all_events())
            self.assertEqual(events[0]["correlationId"], events[1]["correlationId"])
            self.assertEqual(events[1]["subjectId"], "w")
            with patch("factory.ao_request", side_effect=FactoryError("daemon unavailable")):
                with self.assertRaises(FactoryError):
                    factory.api("/api/v1/sessions/w/conversation/interrupt", {})
            self.assertEqual(list(factory.audit.all_events())[-1]["kind"], "native.failed")

    def test_delegation_validates_native_roles_project_and_persists(self):
        with tempfile.TemporaryDirectory() as root:
            factory = Factory("http://unused", root)
            def api(path):
                return {"session": {"id": "o" if path.endswith("/o") else "w", "kind": "orchestrator" if path.endswith("/o") else "worker", "projectId": "p"}}
            with patch.object(factory, "api", side_effect=api):
                factory.trace_link("o", "w")
                factory.trace_link("o", "w")
            self.assertEqual(len(factory.audit.events("o", kinds=["delegation.recorded"])), 1)
            with patch.object(factory, "api", return_value={"session": {"kind": "worker", "projectId": "other"}}):
                with self.assertRaises(FactoryError):
                    factory.trace_link("o", "z")


if __name__ == "__main__":
    unittest.main()
