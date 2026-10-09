#!/usr/bin/env python3
"""Local factory supervisor over the pinned Agent Orchestrator HTTP API."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent


class FactoryError(Exception):
    pass


def run_json(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise FactoryError(result.stderr.strip() or f"Command failed: {args[0]}")
    return json.loads(result.stdout)


def ao_request(base, path, body=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise FactoryError(f"AO HTTP {exc.code}: {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise FactoryError(f"AO daemon unavailable: {exc.reason}") from exc


def parse_pr(url):
    match = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)/?", url)
    if not match:
        raise FactoryError("Use a github.com pull request URL.")
    owner, repo, number = match.groups()
    return owner + "/" + repo, int(number)


def evaluate(pr, checks, threads, reviews, required):
    """Fail closed; all inputs must describe one currently observed PR head."""
    reasons = []
    head = pr.get("headRefOid", "")
    if not head:
        reasons.append("PR head SHA is unavailable")
    if pr.get("state") != "OPEN":
        reasons.append("PR is not open")
    if pr.get("mergeable") != "MERGEABLE":
        reasons.append("Mergeability is conflicting or unknown")
    if pr.get("reviewDecision") == "CHANGES_REQUESTED" or pr.get("outstandingChangeRequests"):
        reasons.append("GitHub reviewers requested changes")
    if not required:
        reasons.append("Configure at least one required CI check name")
    # All current-head contexts must finish successfully, including optional ones.
    successful = set()
    for check in checks:
        name = check.get("name", check.get("context", "unnamed"))
        if check.get("__typename") == "CheckRun":
            good = check.get("status") == "COMPLETED" and check.get("conclusion") == "SUCCESS"
        else:
            good = check.get("state") == "SUCCESS"
        if good:
            successful.add(name)
        else:
            reasons.append(f"CI check has not succeeded: {name}")
    for name in required:
        if name not in successful:
            reasons.append(f"Required CI check missing or unsuccessful: {name}")
    if any(not thread.get("isResolved", False) for thread in threads):
        reasons.append("Unresolved review threads remain")
    # A later failed/running/rejected pass from the same reviewer supersedes approval.
    latest = {}
    for review in sorted(reviews, key=lambda r: (r.get("createdAt", ""), r.get("id", ""))):
        if review.get("targetSha") == head and review.get("prUrl", "").rstrip("/") == pr.get("url", "").rstrip("/"):
            latest[review.get("reviewId") or review.get("harness", "unknown")] = review
    approved = [r for r in latest.values() if r.get("status") in ("complete", "completed", "delivered") and r.get("verdict") == "approved"]
    if not approved:
        reasons.append("No independent AO review approved the current head")
    if any(r.get("verdict") != "approved" or r.get("status") not in ("complete", "completed", "delivered") for r in latest.values()):
        reasons.append("A current-head AO review is unresolved or requested changes")
    return {"ready": not reasons, "reasons": reasons, "headSha": head,
            "prUrl": pr.get("url"), "draft": pr.get("isDraft", True),
            "requiredChecks": required, "successfulChecks": sorted(successful),
            "approvedReviewRuns": [r.get("id") for r in approved],
            "observedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "meaning": "Ready for human handoff; this does not authorize merging." if not reasons else "Evidence incomplete; resolve blockers before handoff."}


def github_evidence(url):
    repo, number = parse_pr(url)
    pr = run_json(["gh", "pr", "view", str(number), "--repo", repo, "--json",
                   "url,headRefOid,state,isDraft,mergeable,reviewDecision,statusCheckRollup"])
    owner, name = repo.split("/")
    query = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
      repository(owner:$owner,name:$name){pullRequest(number:$number){headRefOid
        reviewThreads(first:100,after:$cursor){nodes{isResolved}
          pageInfo{hasNextPage endCursor}}}}}"""
    threads, cursor = [], None
    while True:
        args = ["gh", "api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner,
                "-f", "name=" + name, "-F", "number=" + str(number)]
        if cursor:
            args += ["-f", "cursor=" + cursor]
        data = run_json(args)
        if data.get("errors"):
            raise FactoryError("GitHub could not establish review thread state")
        observed = data["data"]["repository"]["pullRequest"]
        if observed["headRefOid"] != pr["headRefOid"]:
            raise FactoryError("PR head changed while reading evidence; retry")
        page = observed["reviewThreads"]
        threads.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    # gh pr view's rollup is bounded. Page all contexts so a late failing check
    # cannot disappear beyond the first 100 results.
    query = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
      repository(owner:$owner,name:$name){pullRequest(number:$number){headRefOid
        commits(last:1){nodes{commit{statusCheckRollup{contexts(first:100,after:$cursor){
          nodes{__typename ... on CheckRun{name status conclusion}
            ... on StatusContext{context state}} pageInfo{hasNextPage endCursor}}}}}}}}}"""
    checks, cursor = [], None
    while True:
        args = ["gh", "api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner,
                "-f", "name=" + name, "-F", "number=" + str(number)]
        if cursor:
            args += ["-f", "cursor=" + cursor]
        data = run_json(args)
        if data.get("errors"):
            raise FactoryError("GitHub could not establish CI check state")
        observed = data["data"]["repository"]["pullRequest"]
        if observed["headRefOid"] != pr["headRefOid"]:
            raise FactoryError("PR head changed while reading checks; retry")
        rollup = observed["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        if not rollup:
            break
        page = rollup["contexts"]
        checks.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    # reviewDecision can be null without branch protection. Read submitted
    # review decisions too; a later comment is not an approval of earlier fixes.
    query = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
      repository(owner:$owner,name:$name){pullRequest(number:$number){headRefOid
        reviews(first:100,after:$cursor){nodes{author{login} state submittedAt}
          pageInfo{hasNextPage endCursor}}}}}"""
    decisions, records, cursor = {}, [], None
    while True:
        args = ["gh", "api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner,
                "-f", "name=" + name, "-F", "number=" + str(number)]
        if cursor:
            args += ["-f", "cursor=" + cursor]
        data = run_json(args)
        if data.get("errors"):
            raise FactoryError("GitHub could not establish review decision state")
        observed = data["data"]["repository"]["pullRequest"]
        if observed["headRefOid"] != pr["headRefOid"]:
            raise FactoryError("PR head changed while reading reviews; retry")
        page = observed["reviews"]
        records.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    for index, review in enumerate(sorted(records, key=lambda r: r.get("submittedAt") or "")):
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED"):
            author = (review.get("author") or {}).get("login") or f"deleted-reviewer-{index}"
            decisions[author] = review["state"]
    pr["outstandingChangeRequests"] = [a for a, decision in decisions.items() if decision == "CHANGES_REQUESTED"]
    return pr, checks, threads


class Factory:
    def __init__(self, base, state):
        self.base, self.state = base, Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def api(self, path, body=None, method=None):
        return ao_request(self.base, path, body, method)

    def policies(self):
        path = self.state / "factory-policies.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def save_policy(self, project, policy):
        with self.lock:
            policies = self.policies()
            policies[project] = policy
            temp = self.state / "factory-policies.tmp"
            temp.write_text(json.dumps(policies, indent=2) + "\n")
            temp.replace(self.state / "factory-policies.json")

    def add(self, body):
        path = str(Path(body["path"]).expanduser().resolve(strict=True))
        checks = list(dict.fromkeys(x.strip() for x in body.get("requiredChecks", []) if x.strip()))
        if not checks:
            raise FactoryError("Specify at least one real CI check name for the readiness gate.")
        harness = body.get("harness", "codex")
        if harness not in ("codex", "copilot", "claude-code", "opencode"):
            raise FactoryError("Unsupported factory harness")
        rules = (ROOT / "WORKFLOW.md").read_text()
        rules += "\nRequired GitHub CI checks for handoff: " + ", ".join(checks)
        rules += "\nUse draft PRs. The factory gate remains blocked until current-head evidence passes."
        config = {"worker": {"agent": harness, "agentConfig": {"permissions": "auto"}},
                  "orchestrator": {"agent": harness, "agentConfig": {"permissions": "auto"}},
                  "reviewers": [{"harness": harness, "agentConfig": {"permissions": "auto"}}],
                  "agentRules": rules, "orchestratorRules": rules + "\nDelegate independent tasks to AO workers; avoid overlapping file ownership. Limit active workers to 3. This concurrency limit is an instruction, not a daemon quota.",
                  "autoReview": True, "workersRequestReview": True}
        # Native create is atomic with config; never overwrite an existing project's settings.
        result = self.api("/api/v1/projects", {"path": path, "config": config})
        pid = result["project"]["id"]
        self.save_policy(pid, {"requiredChecks": checks, "harness": harness,
                               "workflowSha256": hashlib.sha256(rules.encode()).hexdigest()})
        return result

    def spawn(self, body):
        pid, prompt = body["projectId"], body["prompt"].strip()
        if pid not in self.policies():
            raise FactoryError("Add this repository through factory onboarding first.")
        if not prompt or len(prompt) > 14000:
            raise FactoryError("Enter a task of 1–14000 characters.")
        request_id = body.get("requestId", "")
        if not re.fullmatch(r"[\w-]{8,100}", request_id):
            raise FactoryError("A stable requestId is required for retry-safe dispatch.")
        if body.get("kind") == "orchestrator":
            result = self.api("/api/v1/orchestrators", {"projectId": pid, "mode": "chat", "approvalMode": "auto"})
            sid = result["orchestrator"]["id"]
            sent = self.api(f"/api/v1/sessions/{sid}/conversation/messages", {"text": prompt, "clientMessageId": request_id})
            return {"session": {"id": sid}, "delivery": sent}
        return self.api("/api/v1/sessions", {"projectId": pid, "kind": "worker", "mode": "chat",
                        "harness": self.policies()[pid]["harness"], "approvalMode": "auto",
                        "clientRequestId": request_id, "prompt": prompt,
                        "displayName": body.get("title", "Factory task")[:100]})

    def gate(self, sid, url):
        sid = safe_id(sid)
        session = self.api(f"/api/v1/sessions/{sid}")["session"]
        policy = self.policies().get(session.get("projectId"), {})
        reviews = self.api(f"/api/v1/sessions/{sid}/reviews").get("runs", [])
        pr, checks, threads = github_evidence(url)
        result = evaluate(pr, checks, threads, reviews, policy.get("requiredChecks", []))
        # Verify head again after AO/GitHub evidence collection; reports are point-in-time.
        repo, number = parse_pr(url)
        current = run_json(["gh", "pr", "view", str(number), "--repo", repo, "--json", "headRefOid"])
        if current.get("headRefOid") != result["headSha"]:
            raise FactoryError("PR head changed during gate evaluation; retry")
        result["sessionId"] = sid
        reports = self.state / "gate-reports"
        reports.mkdir(exist_ok=True, mode=0o700)
        report = reports / f"{sid}-{time.time_ns()}.json"
        result["reportPath"] = str(report)
        report.write_text(json.dumps(result, indent=2) + "\n")
        return result


def safe_id(value):
    if not re.fullmatch(r"[\w.-]{1,150}", value):
        raise FactoryError("Invalid session identifier")
    return value


def handler(factory, port):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, content_type="application/json"):
            raw = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            try:
                if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                    return self.reply({"error": "Invalid host"}, 403)
                path = urllib.parse.urlsplit(self.path).path
                if path == "/":
                    return self.reply((ROOT / "web/index.html").read_bytes(), content_type="text/html; charset=utf-8")
                if path in ("/app.js", "/style.css"):
                    return self.reply((ROOT / "web" / path[1:]).read_bytes(), content_type="text/javascript" if path.endswith("js") else "text/css")
                if path in ("/assets/logo.svg", "/assets/logo-mark.svg", "/assets/icons.svg", "/assets/hero.svg"):
                    return self.reply((ROOT / "web" / path[1:]).read_bytes(), content_type="image/svg+xml")
                if path == "/api/state":
                    return self.reply({"engine": factory.api("/healthz"),
                        "projects": factory.api("/api/v1/projects")["projects"],
                        "sessions": factory.api("/api/v1/sessions")["sessions"],
                        "policies": factory.policies(), "token": token})
                match = re.fullmatch(r"/api/sessions/([\w.-]+)/(conversation|reviews)", path)
                if match:
                    return self.reply(factory.api(f"/api/v1/sessions/{match[1]}/{match[2]}"))
                return self.reply({"error": "Not found"}, 404)
            except (FactoryError, KeyError, ValueError, OSError) as exc:
                self.reply({"error": str(exc)}, 502)

        def do_POST(self):
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}") or origin not in (None, f"http://{host}") or self.headers.get("X-Factory-Token") != token:
                return self.reply({"error": "Request must originate from this local factory"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 32768:
                    return self.reply({"error": "Invalid request size"}, 413)
                body = json.loads(self.rfile.read(length))
                if self.path == "/api/projects":
                    return self.reply(factory.add(body), 201)
                if self.path == "/api/spawn":
                    return self.reply(factory.spawn(body), 201)
                match = re.fullmatch(r"/api/sessions/([\w.-]+)/(send|review|gate|interrupt|approval)", self.path)
                if not match:
                    return self.reply({"error": "Not found"}, 404)
                sid, action = match.groups()
                if action == "gate":
                    return self.reply(factory.gate(sid, body["prUrl"]))
                if action == "review":
                    parse_pr(body["prUrl"])
                    return self.reply(factory.api(f"/api/v1/sessions/{sid}/reviews/trigger", {"prUrl": body["prUrl"], "interfaceMode": "chat", "enableAutoInject": True}))
                if action == "send":
                    return self.reply(factory.api(f"/api/v1/sessions/{sid}/conversation/steer-or-send", {"text": body["text"], "clientMessageId": body["requestId"]}))
                if action == "approval":
                    request_id = urllib.parse.quote(body["requestId"], safe="")
                    return self.reply(factory.api(f"/api/v1/sessions/{sid}/conversation/approvals/{request_id}/resolve", {"decisionId": body["decisionId"]}))
                return self.reply(factory.api(f"/api/v1/sessions/{sid}/conversation/interrupt", {}))
            except (FactoryError, KeyError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                self.reply({"error": str(exc)}, 400)
    return Handler


def environment(state, ao_port):
    env = os.environ.copy()
    env.update(AO_PORT=str(ao_port), AO_DATA_DIR=str(state), AO_RUN_FILE=str(state / "running.json"),
               AO_AGENT="codex", AO_TELEMETRY_EVENTS="off", AO_TELEMETRY_METRICS="off", AO_TELEMETRY_REMOTE="off")
    env["PATH"] = str(ROOT / "runtime") + os.pathsep + env["PATH"]
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "software-factory")
    parser.add_argument("--ao-port", type=int, default=48082)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=48080)
    serve.add_argument("--connect", action="store_true", help="Use an already-running daemon")
    sub.add_parser("doctor")
    ao = sub.add_parser("ao")
    ao.add_argument("args", nargs=argparse.REMAINDER)
    gate = sub.add_parser("gate")
    gate.add_argument("session")
    gate.add_argument("pr_url")
    args = parser.parse_args()
    state = args.state.expanduser().resolve()
    base = f"http://127.0.0.1:{args.ao_port}"
    if args.command == "doctor":
        result = {"python": sys.version.split()[0], "git": shutil.which("git"), "gh": shutil.which("gh"), "codex": shutil.which("codex"), "state": str(state)}
        try:
            result["daemon"] = ao_request(base, "/healthz")
            result["agents"] = ao_request(base, "/api/v1/agents")["installed"]
        except FactoryError as exc:
            result["daemon"] = str(exc)
        print(json.dumps(result, indent=2))
        return
    if args.command == "ao":
        os.execve(ROOT / "runtime/ao", ["ao"] + args.args, environment(state, args.ao_port))
    factory = Factory(base, state)
    if args.command == "gate":
        result = factory.gate(args.session, args.pr_url)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["ready"] else 1)
    child = None
    try:
        if not args.connect:
            manifest = json.loads((ROOT / "UPSTREAM.json").read_text())
            if hashlib.sha256((ROOT / "runtime/ao").read_bytes()).hexdigest() != manifest["daemon_sha256"]:
                raise FactoryError("Daemon binary differs from the pinned release")
            # Refuse an occupied port instead of attaching to someone else's state.
            import socket
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", args.ao_port))
            log = (state / "daemon.log").open("a")
            child = subprocess.Popen([str(ROOT / "runtime/ao"), "daemon"], env=environment(state, args.ao_port), stdout=log, stderr=log)
        for attempt in range(100):
            if child and child.poll() is not None:
                raise FactoryError(f"Daemon exited; inspect {state / 'daemon.log'}")
            try:
                factory.api("/readyz")
                break
            except FactoryError:
                time.sleep(.1)
        else:
            raise FactoryError("Daemon did not become ready")
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(factory, args.port))
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        print(f"Software Factory: http://127.0.0.1:{args.port} • AO v0.13.5 • state {state}", flush=True)
        server.serve_forever()
    finally:
        if child:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                print("Daemon still shutting down; left running to preserve work.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (FactoryError, OSError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
