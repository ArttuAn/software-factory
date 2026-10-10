import base64
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from factory import Factory, FactoryError
from proof import capture


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-qb", "main", cwd=self.repo)
        self.git("config", "user.name", "Factory tests", cwd=self.repo)
        self.git("config", "user.email", "factory@localhost", cwd=self.repo)
        (self.repo / "sample.py").write_text("def mean(values):\n    return sum(values) / len(values)\n")
        self.commit(self.repo)
        self.workspace = self.root / "worker"
        self.git("worktree", "add", "-qb", "fix-mean", str(self.workspace), cwd=self.repo)
        self.factory = Factory("http://unused", self.root / "state")
        self.factory.save_policy("sample", {"requireProof": True, "requiredChecks": ["test"]})
        self.native = patch.object(self.factory, "api", side_effect=self.response).start()
        self.addCleanup(patch.stopall)
        self.command = [sys.executable, "-B", "-c", "from sample import mean; assert mean([]) is None"]
        self.criterion = "Empty input returns None"

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.workspace,
                              text=True, capture_output=True, check=True).stdout.strip()

    def commit(self, workspace):
        self.git("add", ".", cwd=workspace)
        self.git("commit", "-qm", "Fixture change", cwd=workspace)

    def response(self, path, *args):
        if path == "/api/v1/sessions/app-1":
            return {"session": {"projectId": "sample", "kind": "worker", "branch": "fix-mean"}}
        if path == "/api/v1/projects/sample":
            return {"project": {"path": str(self.repo)}}
        if path == "/api/v1/sessions/app-1/reviews":
            return {"runs": [{"id": "r1", "reviewId": "reviewer", "prUrl": self.pr_url,
                              "targetSha": self.head, "status": "complete", "verdict": "approved"}]}
        self.fail("Unexpected native API path: " + path)

    def record(self, phase, **kwargs):
        return self.factory.capture_proof("app-1", self.workspace, phase, self.criterion,
                                           kwargs.pop("command", self.command), **kwargs)

    def fix(self):
        (self.workspace / "sample.py").write_text("def mean(values):\n    return sum(values) / len(values) if values else None\n")
        self.commit(self.workspace)
        self.head = self.git("rev-parse", "HEAD")

    def pair(self):
        self.record("before", expected_exit=1)
        self.fix()
        return self.record("after")

    def test_actual_failure_then_success_is_bound_to_commits_and_audit(self):
        after = self.pair()
        result = self.factory.proof("app-1", self.head)
        self.assertTrue(result["ready"], result["reasons"])
        pair = result["pairs"][0]
        self.assertEqual(pair["before"]["exitCode"], 1)
        self.assertIn("ZeroDivisionError", pair["before"]["output"])
        self.assertEqual(pair["after"]["exitCode"], 0)
        self.assertTrue(after["data"]["baselineAncestor"])
        self.assertTrue(self.factory.audit.verify()["valid"])
        self.assertEqual(Factory("http://unused", self.factory.state).proof("app-1", self.head), result)

    def test_no_proof_and_an_unpaired_criterion_block(self):
        self.assertFalse(self.factory.proof("app-1", "unknown")["ready"])
        self.pair()
        self.factory.capture_proof("app-1", self.workspace, "before", "Nonempty input", [sys.executable, "-B", "-c", "pass"])
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])

    def test_changed_head_or_command_blocks_previously_valid_proof(self):
        self.pair()
        self.assertFalse(self.factory.proof("app-1", "another-head")["ready"])
        self.record("after", command=[sys.executable, "-B", "-c", "pass"])
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])

    def test_later_failure_and_replaced_baseline_supersede_old_success(self):
        self.pair()
        (self.workspace / "sample.py").write_text("def mean(values):\n    raise RuntimeError('regression')\n")
        self.commit(self.workspace)
        self.head = self.git("rev-parse", "HEAD")
        result = self.record("after")
        self.assertFalse(result["data"]["passed"])
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])
        self.record("before", expected_exit=1)
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])

    def test_dirty_worktree_rejected_and_command_mutations_fail_capture(self):
        (self.workspace / "untracked.txt").write_text("uncommitted")
        with self.assertRaisesRegex(ValueError, "clean"):
            self.record("before")
        (self.workspace / "untracked.txt").unlink()
        result = capture(self.workspace, "before", "No mutations",
                         [sys.executable, "-B", "-c", "from pathlib import Path; Path('oops').write_text('changed')"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["snapshotStable"])

    def test_root_checkout_and_other_branches_cannot_claim_worker_proof(self):
        with self.assertRaises(FactoryError):
            self.factory.capture_proof("app-1", self.repo, "before", self.criterion, self.command)
        self.git("switch", "-c", "unrelated")
        with self.assertRaises(FactoryError):
            self.record("before")

    def test_after_requires_baseline_and_different_commit(self):
        with self.assertRaisesRegex(FactoryError, "before proof"):
            self.record("after")
        command = [sys.executable, "-B", "-c", "pass"]
        self.record("before", command=command)
        self.head = self.git("rev-parse", "HEAD")
        self.record("after", command=command)
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])

    def test_timeout_is_recorded_as_failure(self):
        result = capture(self.workspace, "before", "Bounded command",
                         [sys.executable, "-B", "-c", "import time; time.sleep(30)"], timeout=1)
        self.assertTrue(result["timedOut"])
        self.assertFalse(result["passed"])

    def test_preserved_media_survives_source_overwrite_and_detects_corruption(self):
        image = self.root / "screenshot.png"
        image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII="))
        before = self.record("before", expected_exit=1, artifacts=[image])
        self.fix()
        self.record("after")
        image.write_bytes(b"overwritten source")
        self.assertTrue(self.factory.proof("app-1", self.head)["ready"])
        artifact = before["data"]["artifacts"][0]
        stored = self.factory.state / "proof-artifacts" / artifact["id"]
        self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), artifact["sha256"])
        stored.write_bytes(b"corrupt")
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])
        stored.unlink()
        self.assertFalse(self.factory.proof("app-1", self.head)["ready"])

    def test_gate_requires_proof_for_new_policy_and_preserves_existing_policy(self):
        self.fix()
        self.pr_url = "https://github.com/acme/app/pull/1"
        pr = {"url": self.pr_url, "headRefOid": self.head, "state": "OPEN", "mergeable": "MERGEABLE"}
        checks = [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
        with patch("factory.github_evidence", return_value=(pr, checks, [])), patch("factory.run_json", return_value={"headRefOid": self.head}):
            result = self.factory.gate("app-1", self.pr_url)
            self.assertFalse(result["ready"])
            self.assertTrue(result["proofRequired"])
            self.factory.save_policy("sample", {"requiredChecks": ["test"]})
            result = self.factory.gate("app-1", self.pr_url)
            self.assertTrue(result["ready"])
            self.assertFalse(result["proofRequired"])

    def test_gate_accepts_captured_fix_with_current_review_and_ci(self):
        self.pair()
        self.pr_url = "https://github.com/acme/app/pull/1"
        pr = {"url": self.pr_url, "headRefOid": self.head, "state": "OPEN", "mergeable": "MERGEABLE"}
        checks = [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
        with patch("factory.github_evidence", return_value=(pr, checks, [])), patch("factory.run_json", return_value={"headRefOid": self.head}):
            result = self.factory.gate("app-1", self.pr_url)
        self.assertTrue(result["ready"], result["reasons"])
        self.assertTrue(result["proof"]["ready"])
        self.assertEqual(result["approvedReviewRuns"], ["r1"])


if __name__ == "__main__":
    unittest.main()
