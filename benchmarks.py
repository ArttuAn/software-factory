"""Small versioned role probes with deterministic grading, executed by real AO workers.

Role probes measure a narrow ability; they do not exercise production delegation
or the native PR reviewer. Graders live outside the agent's fixture worktree.
"""
import json
import contextvars
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from observability import digest

SUITE = "factory-role-probes-v1"
GRADER_HASH = digest(Path(__file__).read_text())
FIXTURE = '''def page(items, offset, limit):
    """Return at most limit items starting at offset; reject invalid bounds."""
    return items[offset:offset + limit - 1]


def mean(values):
    """Return None for empty input, otherwise the arithmetic mean."""
    return sum(values) / len(values)


def is_even(value):
    return value % 2 == 0
'''
PROMPTS = {
    "worker": "Fix page() and mean() in sample.py to satisfy their docstrings, including zero limit, negative offset and negative limit (raise ValueError). Preserve is_even(). Add Python unittest regression tests discoverable from the repository root and run them. Do not publish a PR, use the network, or modify other repositories. Finish by explaining your validation.",
    "reviewer": "Review sample.py without modifying any file. Find concrete bugs against its docstrings; page() must reject negative offset or limit with ValueError. Return ONLY JSON: {\"findings\":[{\"function\":\"page\",\"case\":\"truncation\",\"explanation\":\"...\"}]}. Allowed case labels are truncation, invalid-bounds, empty-input, parity. Do not flag correct behavior. Do not publish a PR or use the network.",
    "orchestrator": "Plan implementing robust pagination without changing files, delegating, or using the network. Changes must cover sample.py, tests/test_page.py, README.md. Return ONLY JSON: {\"tasks\":[{\"id\":\"implement\",\"files\":[\"sample.py\"],\"dependsOn\":[],\"acceptance\":\"...\"}]}. Assign each file to exactly one task, give tasks concrete acceptance criteria, and make README.md depend (directly or transitively) on both implementation and tests. Use at least two tasks. Do not publish a PR."
}


def catalog():
    return {"suite": SUITE, "roles": list(PROMPTS), "datasetHash": digest([SUITE, FIXTURE, PROMPTS]), "graderHash": GRADER_HASH,
            "meaning": "Narrow synthetic role probes executed in dedicated native worker sessions. Not production success rates.",
            "limits": "Trusted local execution; graders are external to the worktree, not a security sandbox. Provider usage is billed normally."}


def parse_answer(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def grade_plan(answer):
    tasks = answer.get("tasks", [])
    if not isinstance(tasks, list) or any(not isinstance(t, dict) for t in tasks):
        raise ValueError("tasks must be a list of objects")
    ids = [t.get("id") for t in tasks]
    if any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("Every task needs a string id")
    nodes = {t["id"]: t for t in tasks}
    files = [f for t in tasks for f in t.get("files", [])]
    def ancestors(key, trail=()):
        if key in trail or key not in nodes:
            raise ValueError("Dependencies contain a cycle or unknown task")
        result = set()
        for dep in nodes[key].get("dependsOn", []):
            result.add(dep)
            result.update(ancestors(dep, trail + (key,)))
        return result
    try:
        parents = {i: ancestors(i) for i in ids}
        valid_graph = True
    except (ValueError, TypeError):
        parents, valid_graph = {}, False
    owners = {f: t["id"] for t in tasks for f in t.get("files", [])}
    docs_deps = parents.get(owners.get("README.md"), set())
    return [
        ("Distinct tasks", len(tasks) >= 2 and len(ids) == len(set(ids))),
        ("Complete file coverage", set(files) == {"sample.py", "tests/test_page.py", "README.md"}),
        ("No overlapping file ownership", len(files) == len(set(files))),
        ("Acyclic known dependencies", valid_graph),
        ("Documentation follows implementation and tests", all(owners.get(f) in docs_deps for f in ("sample.py", "tests/test_page.py"))),
        ("Concrete acceptance criteria", bool(tasks) and all(isinstance(t.get("acceptance"), str) and len(t["acceptance"].strip()) >= 15 for t in tasks))]


def grade_review(answer):
    findings = answer.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
        raise ValueError("findings must be a list of objects")
    expected = {("page", "truncation"), ("page", "invalid-bounds"), ("mean", "empty-input")}
    actual = {(f.get("function"), f.get("case")) for f in findings}
    hits = expected & actual
    checks = [(f"Detect {function}/{case}", (function, case) in actual) for function, case in sorted(expected)]
    checks += [("No false positives", not (actual - expected)),
               ("Explain findings", bool(findings) and all(len(str(f.get("explanation", "")).strip()) >= 15 for f in findings))]
    return checks, {"precision": len(hits) / len(actual) if actual else 0, "recall": len(hits) / len(expected)}


WORKER_CHECK = '''import importlib.util, json, sys
spec=importlib.util.spec_from_file_location("candidate",sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
checks=[]
def check(name, fn):
    try: checks.append([name, bool(fn())])
    except Exception: checks.append([name, False])
def rejects(offset, limit):
    try: m.page([1,2,3],offset,limit)
    except ValueError: return True
    return False
check("Full page",lambda:m.page([1,2,3,4],1,2)==[2,3])
check("Zero limit",lambda:m.page([1,2,3],0,0)==[])
check("Empty page",lambda:m.page([],0,3)==[])
check("Past end",lambda:m.page([1],3,2)==[])
check("Negative offset",lambda:rejects(-1,2))
check("Negative limit",lambda:rejects(0,-1))
check("Empty mean",lambda:m.mean([]) is None)
check("Nonempty mean",lambda:m.mean([2,4,9])==5)
check("Parity preserved",lambda:m.is_even(2) is True and m.is_even(3) is False)
print(json.dumps(checks))
'''


def grade(role, workspace, text):
    metrics = {}
    if role == "worker":
        result = subprocess.run([sys.executable, "-I", "-c", WORKER_CHECK, str(Path(workspace) / "sample.py")],
                                capture_output=True, text=True, timeout=20, cwd="/tmp")
        if result.returncode:
            raise ValueError("Independent worker checks could not complete: " + result.stderr[-1000:])
        checks = json.loads(result.stdout)
        regression_check = '''import unittest, sys, json
sys.path.insert(0, sys.argv[1])
suite=unittest.defaultTestLoader.discover(sys.argv[1])
count=suite.countTestCases()
result=unittest.TextTestRunner(verbosity=0).run(suite)
print(json.dumps({"count":count,"passed":result.wasSuccessful()}))
'''
        result = subprocess.run([sys.executable, "-I", "-c", regression_check, str(workspace)], capture_output=True, text=True, timeout=20, cwd=workspace)
        try:
            regression = json.loads(result.stdout)
        except ValueError:
            regression = {}
        checks.append(("Added regression tests execute successfully", result.returncode == 0 and regression.get("count", 0) > 0 and regression.get("passed") is True))
    elif role == "reviewer":
        checks, metrics = grade_review(parse_answer(text))
    else:
        checks = grade_plan(parse_answer(text))
    if role != "worker":
        result = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, capture_output=True, text=True, timeout=10, check=True)
        checks.append(("Read-only fixture preserved", not result.stdout.strip() and (Path(workspace) / "sample.py").read_text() == FIXTURE))
    return {"checks": [{"name": name, "status": "pass" if ok else "fail"} for name, ok in checks],
            "score": sum(bool(ok) for _, ok in checks) / len(checks), "metrics": metrics,
            "status": "pass" if all(ok for _, ok in checks) else "fail"}


class Benchmarks:
    def __init__(self, factory):
        self.factory, self.store = factory, factory.audit
        self.lock = threading.Lock()
        self.active = False

    def launch(self, role, harness, correlation=None):
        if not isinstance(role, str) or role not in PROMPTS or harness not in ("codex", "claude-code", "copilot", "opencode"):
            raise ValueError("Select a supported role and harness")
        with self.lock:
            if self.active:
                raise ValueError("A role probe is already running")
            self.active = True
        identifier = "probe-" + uuid.uuid4().hex[:16]
        subject = "benchmark:" + identifier
        try:
            self.store.subject(subject, role=role, harness=harness, title=f"{role.title()} role probe", executionKind="benchmark-worker")
            self.store.append(subject, "benchmark.started", {**catalog(), "role": role, "harness": harness, "id": identifier}, actor="local-user", correlation=correlation)
            context = contextvars.copy_context()
            threading.Thread(target=context.run, args=(self.run, identifier, subject, role, harness, correlation), daemon=True).start()
        except Exception:
            with self.lock:
                self.active = False
            raise
        return {"id": identifier, "subjectId": subject, "status": "running"}

    def run(self, identifier, subject, role, harness, correlation=None):
        started, sid = time.monotonic(), None
        try:
            fixture = self.factory.state / "benchmarks" / identifier
            fixture.mkdir(parents=True, mode=0o700)
            (fixture / "sample.py").write_text(FIXTURE)
            (fixture / "README.md").write_text("# Role probe fixture\n")
            for args in (["git", "init", "-qb", "main"], ["git", "add", "."], ["git", "-c", "user.name=Factory Evals", "-c", "user.email=evals@localhost", "commit", "-qm", "Seed role probe"]):
                subprocess.run(args, cwd=fixture, capture_output=True, check=True, timeout=20)
            # AO resolves its base from remote HEAD. Keep this entire remote local.
            remote = fixture.with_name(identifier + "-remote.git")
            for args in (["git", "clone", "--bare", str(fixture), str(remote)],
                         ["git", "remote", "add", "origin", str(remote)],
                         ["git", "fetch", "origin"],
                         ["git", "remote", "set-head", "origin", "main"]):
                subprocess.run(args, cwd=fixture, capture_output=True, check=True, timeout=20)
            project = self.factory.api("/api/v1/projects", {"path": str(fixture), "config": {
                "worker": {"agent": harness, "agentConfig": {"permissions": "auto"}},
                "autoReview": False, "agentRules": "This is a local benchmark fixture. Do not publish, create PRs, use the network, delegate, or edit outside your assigned worktree."}})["project"]["id"]
            response = self.factory.api("/api/v1/sessions", {"projectId": project, "kind": "worker", "mode": "chat", "harness": harness,
                "approvalMode": "auto", "clientRequestId": identifier, "prompt": PROMPTS[role], "displayName": f"Eval {role} · {SUITE}"})
            sid = response["session"]["id"]
            self.store.subject(subject, parentId=sid, projectId=project)
            self.store.subject(sid, role="worker", harness=harness, projectId=project, title=f"Eval {role}", probeRole=role, probeId=subject)
            self.store.append(subject, "benchmark.dispatched", {"sessionId": sid, "prompt": PROMPTS[role], "suite": SUITE}, correlation=correlation)
            # The session id is returned by the trusted native API; use native worktree inventory.
            while time.monotonic() - started < 600:
                conversation = self.factory.api(f"/api/v1/sessions/{sid}/conversation")
                turns = conversation.get("turns") or []
                if turns and all(t.get("state") == "completed" for t in turns):
                    messages = [m for m in conversation.get("messages", []) if m.get("role") == "assistant" and not m.get("streaming")]
                    answer = max(messages, key=lambda m: m.get("sequence", 0))["text"] if messages else ""
                    workspace = self.factory.state / "worktrees" / project / sid
                    try:
                        result = grade(role, workspace, answer)
                    except (ValueError, TypeError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
                        result = {"status": "fail", "score": 0, "checks": [{"name": "Output can be independently graded", "status": "fail", "error": str(exc)}]}
                    self.store.append(subject, "benchmark.completed", {**result, **catalog(), "role": role, "harness": harness,
                        "sessionId": sid, "durationSeconds": round(time.monotonic() - started, 2), "usage": conversation.get("usage"),
                        "model": conversation.get("settings", {}).get("model"), "answer": answer,
                        "graderHash": GRADER_HASH}, correlation=correlation)
                    return
                if any(t.get("state") in ("failed", "interrupted", "cancelled") for t in turns):
                    raise ValueError("Agent turn did not complete successfully")
                time.sleep(2)
            self.factory.api(f"/api/v1/sessions/{sid}/conversation/interrupt", {})
            raise TimeoutError("Role probe exceeded its 10 minute limit; interruption requested")
        except Exception as exc:
            self.store.append(subject, "benchmark.completed", {**catalog(), "role": role, "harness": harness,
                "status": "error", "score": None, "sessionId": sid, "error": str(exc),
                "durationSeconds": round(time.monotonic() - started, 2)}, correlation=correlation)
        finally:
            with self.lock:
                self.active = False
