from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from workflow import DOCUMENTS, ROOT, render


class PortableWorkflowTests(unittest.TestCase):
    def test_bundle_contains_the_complete_contract_in_order(self):
        bundle = render()
        self.assertEqual(bundle, "\n\n---\n\n".join(
            (ROOT / name).read_text(encoding="utf-8").strip() for name in DOCUMENTS
        ) + "\n")
        self.assertIn("independent review context is required", bundle)
        self.assertIn("After must succeed", bundle)
        self.assertIn("baseline must be an ancestor", bundle)

    def test_core_has_no_runtime_commands_or_provider_dependency(self):
        bundle = render().lower()
        for dependency in ("ao review", "factory.py", "trace-link", "agent orchestrator",
                           "codex", "claude", "copilot", "opencode", "greptile",
                           "<worker-session-id>", "factory-policies.json"):
            with self.subTest(dependency=dependency):
                self.assertNotIn(dependency, bundle)

    def test_export_runs_with_only_core_files_and_no_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            isolated = Path(root)
            for name in (*DOCUMENTS, "workflow.py"):
                shutil.copyfile(ROOT / name, isolated / name)
            result = subprocess.run([sys.executable, "-I", str(isolated / "workflow.py")],
                                    cwd=isolated, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, render())
            self.assertEqual(result.stderr, "")

    def test_export_creates_file_but_never_overwrites_it_or_repository_guidance(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "FACTORY.md"
            guidance = Path(root) / "AGENTS.md"
            guidance.write_text("Existing project instructions\n", encoding="utf-8")
            command = [sys.executable, str(ROOT / "workflow.py"), "--output", str(output)]
            first = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, "")
            self.assertEqual(output.read_text(encoding="utf-8"), render())
            output.write_text("Existing user contract\n", encoding="utf-8")
            second = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 1)
            self.assertIn("Could not export workflow", second.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "Existing user contract\n")
            self.assertEqual(guidance.read_text(encoding="utf-8"), "Existing project instructions\n")

    def test_missing_parent_is_reported_without_creating_directories(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "missing" / "FACTORY.md"
            result = subprocess.run([sys.executable, str(ROOT / "workflow.py"), "--output", str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Could not export workflow", result.stderr)
            self.assertFalse(output.parent.exists())


if __name__ == "__main__":
    unittest.main()
