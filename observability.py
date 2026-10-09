"""Local, redacted, hash-chained evidence journal. No upstream database access."""
import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


RUBRIC_HASH = digest(Path(__file__).read_text())


def redact(value):
    """Best-effort secret filtering, not a guarantee that transcripts are public-safe."""
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"(?i)(password|secret|api.?key|authorization|access.?token|refresh.?token|credential)", k)
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", value)
        value = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})\b", "[REDACTED]", value)
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", value)
        return re.sub(r"(?i)((?:[\w-]*(?:api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token))[\w-]*\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    return value


class AuditStore:
    def __init__(self, state):
        directory = Path(state) / "observability"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        self.path = directory / "audit.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, hash TEXT NOT NULL, envelope TEXT NOT NULL,
                    subject TEXT NOT NULL, kind TEXT NOT NULL, dedup TEXT UNIQUE);
                CREATE INDEX IF NOT EXISTS subject_events ON events(subject,seq);
                CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'audit events are append-only'); END;
                CREATE TABLE IF NOT EXISTS subjects (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, subject, kind, data, *, source="factory", actor="system", correlation=None, dedup=None, observation=None):
        data = redact(data)
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if dedup and db.execute("SELECT 1 FROM events WHERE dedup=?", (dedup,)).fetchone():
                return None
            fingerprint = digest(data)
            if observation:
                prior = db.execute("SELECT fingerprint FROM observations WHERE id=?", (observation,)).fetchone()
                if prior and prior[0] == fingerprint:
                    return None
            previous = db.execute("SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (previous["seq"] + 1, previous["hash"]) if previous else (1, "0" * 64)
            envelope = {"schema": 1, "seq": seq, "previousHash": prev, "observedAt": now(),
                        "subjectId": subject, "kind": kind, "source": source, "actor": actor,
                        "correlationId": correlation, "data": data}
            root, visited = subject, set()
            while root not in visited:
                visited.add(root)
                row = db.execute("SELECT body FROM subjects WHERE id=?", (root,)).fetchone()
                parent = json.loads(row[0]).get("parentId") if row else None
                if not parent:
                    break
                root = parent
            envelope["traceId"] = root
            hashed = digest(envelope)
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (seq, hashed, canonical(envelope), subject, kind, dedup))
            if observation:
                db.execute("INSERT OR REPLACE INTO observations VALUES (?,?)", (observation, fingerprint))
            return {**envelope, "hash": hashed}

    def observe(self, subject, kind, data, source="native", **kwargs):
        key = digest([subject, kind, data.get("conversationId"), data.get("id", "singleton")])
        return self.append(subject, kind, data, observation=key, source=source, **kwargs)

    def subject(self, identifier, **fields):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT body FROM subjects WHERE id=?", (identifier,)).fetchone()
            body = json.loads(row[0]) if row else {"id": identifier, "firstObservedAt": now()}
            before = {k: v for k, v in body.items() if k != "lastObservedAt"}
            body.update(redact(fields))
            if before != {k: v for k, v in body.items() if k != "lastObservedAt"} or row is None:
                self.append(identifier, "subject.metadata", {k: v for k, v in body.items() if k != "lastObservedAt"})
            body["lastObservedAt"] = now()
            db.execute("INSERT OR REPLACE INTO subjects VALUES (?,?)", (identifier, canonical(body)))
            return body

    def subjects(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT body FROM subjects ORDER BY id")]

    def events(self, subject=None, after=0, limit=200, kinds=None):
        query, args = "SELECT envelope,hash FROM events WHERE seq>?", [after]
        if subject:
            query += " AND subject=?"
            args.append(subject)
        if kinds:
            query += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
            args.extend(kinds)
        query += " ORDER BY seq LIMIT ?"
        args.append(limit)
        with self.connect() as db:
            return [{**json.loads(r[0]), "hash": r[1]} for r in db.execute(query, args)]

    def all_events(self, subject=None, kinds=None):
        after = 0
        while True:
            page = self.events(subject, after, 500, kinds)
            yield from page
            if not page:
                return
            after = page[-1]["seq"]

    def trace_events(self, subject, after=0, limit=100):
        subjects = {s["id"]: s for s in self.subjects()}
        root, visited = subject, set()
        while root not in visited and subjects.get(root, {}).get("parentId"):
            visited.add(root)
            root = subjects[root]["parentId"]
        members = {root}
        while True:
            linked = {s["id"] for s in subjects.values() if s.get("parentId") in members}
            if linked <= members:
                break
            members.update(linked)
        marks = ",".join("?" for _ in members)
        # Include the factory-side intent that created a session, using its correlation id.
        query = f"""SELECT envelope,hash FROM events WHERE seq>? AND (subject IN ({marks}) OR
            json_extract(envelope,'$.correlationId') IN (SELECT json_extract(envelope,'$.correlationId')
            FROM events WHERE subject IN ({marks}) AND json_extract(envelope,'$.correlationId') IS NOT NULL)) ORDER BY seq LIMIT ?"""
        with self.connect() as db:
            return [{**json.loads(r[0]), "hash": r[1]} for r in db.execute(query, [after, *members, *members, limit])]

    def verify(self, checkpoint=None):
        prev, count = "0" * 64, 0
        # One read transaction provides a consistent checkpoint during concurrent writes.
        with self.connect() as db:
            for row in db.execute("SELECT seq,envelope,hash,subject,kind FROM events ORDER BY seq"):
                try:
                    event = json.loads(row["envelope"])
                    if row["seq"] != count + 1 or event["seq"] != row["seq"] or event["subjectId"] != row["subject"] or event["kind"] != row["kind"] or event["previousHash"] != prev or digest(event) != row["hash"]:
                        return {"valid": False, "brokenAt": row["seq"], "events": count}
                except (ValueError, KeyError, TypeError):
                    return {"valid": False, "brokenAt": row["seq"], "events": count}
                count += 1
                prev = row["hash"]
                if checkpoint and count == checkpoint.get("events") and prev != checkpoint.get("headHash"):
                    return {"valid": False, "brokenAt": count, "events": count, "error": "External checkpoint does not match"}
        if checkpoint and (not isinstance(checkpoint.get("events"), int) or checkpoint["events"] > count or checkpoint["events"] < 0 or (checkpoint["events"] == 0 and checkpoint.get("headHash") != "0" * 64)):
            return {"valid": False, "events": count, "error": "External checkpoint is invalid or journal was truncated"}
        return {"valid": True, "events": count, "headHash": prev,
                "scope": "Local hash chain; retain an external checkpoint to detect wholesale replacement or tail deletion."}


class Collector:
    def __init__(self, store, api):
        self.store, self.api = store, api
        self.stop = threading.Event()
        self.status = {"state": "starting", "intervalSeconds": 10, "lastSuccessAt": None}

    def conversation(self, subject, path):
        cursor, seen, pages = None, set(), 0
        while True:
            page = self.api(path + (f"?beforeSequence={cursor}&limit=200" if cursor else "?limit=200"))
            for collection, kind in (("messages", "message"), ("activities", "activity"), ("turns", "turn")):
                for item in page.get(collection, []) or []:
                    self.store.observe(subject, kind, {"conversationId": page.get("conversationId"), **item})
            if cursor is None:
                metrics = {key: page.get(key) for key in ("usage", "settings", "controller", "capabilities", "branchMaterialization", "activeBranchId")}
                self.store.observe(subject, "runtime", metrics)
                self.store.subject(subject, usage=page.get("usage"), settings=page.get("settings"),
                                   conversationId=page.get("conversationId"))
            pages += 1
            if not page.get("hasMoreBefore"):
                self.store.subject(subject, conversationCoverage="available history captured", coverageError=None, historyPages=pages)
                return
            cursor = page.get("oldestSequence")
            if not isinstance(cursor, int) or cursor < 1 or cursor in seen or pages >= 1000:
                raise ValueError("Native history pagination did not complete")
            seen.add(cursor)

    def capture_conversation(self, subject, path):
        try:
            self.conversation(subject, path)
        except Exception as exc:
            self.store.subject(subject, conversationCoverage="unavailable or partial", coverageError=str(exc))
            self.store.observe(subject, "coverage.error", {"path": path, "error": str(exc)})

    def collect(self):
        sessions = self.api("/api/v1/sessions").get("sessions", [])
        for session in sessions:
            sid = session["id"]
            if not re.fullmatch(r"[\w.-]{1,150}", sid):
                continue
            parent = session.get("parentSessionId")
            fields = {"parentId": parent, "parentEvidence": "native"} if parent else {}
            self.store.subject(sid, role=session.get("kind", "worker"), projectId=session.get("projectId"),
                               **fields, harness=session.get("harness"), model=session.get("model"),
                               title=session.get("displayName", sid), branch=session.get("branch"),
                               status=session.get("status"), nativeCreatedAt=session.get("createdAt"))
            self.store.observe(sid, "session", session)
            for pr in session.get("prs", []) or []:
                self.store.subject("ci:" + sid, role="ci", projectId=session.get("projectId"), parentId=sid, title="GitHub CI")
                self.store.observe("ci:" + sid, "pr.summary", pr)
            self.capture_conversation(sid, f"/api/v1/sessions/{sid}/conversation")
            try:
                reviews = self.api(f"/api/v1/sessions/{sid}/reviews").get("runs", []) or []
                reviewer_ids = set()
                for run in reviews:
                    rid = run.get("reviewId") or run["id"]
                    subject = "reviewer:" + rid
                    self.store.subject(subject, role="reviewer", projectId=session.get("projectId"), parentId=sid,
                                       harness=run.get("harness"), title="Reviewer · " + rid)
                    self.store.observe(subject, "review.run", run)
                    if run.get("reviewId") and re.fullmatch(r"[\w.-]{1,150}", rid):
                        reviewer_ids.add(rid)
                    else:
                        self.store.subject(subject, conversationCoverage="native reviewer ID unavailable")
                for rid in reviewer_ids:
                    self.capture_conversation("reviewer:" + rid, f"/api/v1/reviews/{rid}/conversation")
            except Exception as exc:
                self.store.observe(sid, "coverage.error", {"path": "reviews", "error": str(exc)})
        # Backfill pre-journal reports, preserving their original assessment timestamps.
        for report in (self.store.path.parent.parent / "gate-reports").glob("*.json"):
            try:
                result = json.loads(report.read_text())
                sid = result["sessionId"]
                if not re.fullmatch(r"[\w.-]{1,150}", sid) or not isinstance(result.get("ready"), bool):
                    raise ValueError("Invalid saved gate report")
                self.store.subject("gate:" + sid, role="gate", parentId=sid, title="Readiness gate")
                self.store.append(sid, "gate.assessed", result, source="saved-gate-report", dedup="gate-report:" + str(report))
                self.store.append("gate:" + sid, "gate.assessed", result, source="saved-gate-report", dedup="gate-component:" + str(report))
            except (ValueError, KeyError, OSError, TypeError) as exc:
                self.store.observe("factory", "coverage.error", {"id": report.name, "error": str(exc)})
        for subject in self.store.subjects():
            result = operational_eval(self.store, subject)
            result.pop("assessedAt", None)  # The journal's observedAt is the assessment time.
            self.store.observe(subject["id"], "eval.completed", {**result, "trigger": "collector"}, source="factory")
        self.status.update(state="online", lastSuccessAt=now(), error=None)

    def loop(self):
        while not self.stop.is_set():
            try:
                self.collect()
            except Exception as exc:
                self.status.update(state="degraded", error=str(exc))
                try:
                    self.store.observe("factory", "collector.error", {"error": str(exc)})
                except (OSError, sqlite3.Error):
                    pass  # The in-memory degraded status remains visible if disk writes fail.
            self.stop.wait(10)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="factory-audit", daemon=True)
        self.thread.start()


def operational_eval(store, subject):
    """Versioned evidence checks. Unknown is not success; this is not a quality benchmark."""
    events = list(store.all_events(subject["id"]))
    if subject.get("executionKind") == "benchmark-worker":
        completed = [e["data"] for e in events if e["kind"] == "benchmark.completed"]
        result = completed[-1] if completed else {}
        return {"suite": "role-probe-record-v1", "rubricHash": RUBRIC_HASH, "subjectId": subject["id"],
                "role": subject["role"], "assessedAt": now(), "status": result.get("status", "unknown"),
                "checks": result.get("checks", [{"name": "Role probe completed with a grade", "status": "unknown", "evidence": result.get("error", "Probe still running")}]),
                "metrics": {"turns": None, "activities": None, "usage": result.get("usage"), "costUsd": None,
                            "durationSeconds": result.get("durationSeconds"), "score": result.get("score")},
                "meaning": "Synthetic role ability probe, executed by the linked native worker. This does not measure production orchestration or PR-review execution."}
    latest = {}
    for event in events:
        data = event["data"]
        key = (event["kind"], data.get("conversationId"), data.get("id", "singleton"))
        latest[key] = event
    turns = [e["data"] for e in latest.values() if e["kind"] == "turn"]
    activities = [e["data"] for e in latest.values() if e["kind"] == "activity"]
    reviews = [e["data"] for e in latest.values() if e["kind"] == "review.run"]
    gates = [e["data"] for e in events if e["kind"] == "gate.assessed"]
    checks = []
    def check(name, verdict, evidence):
        checks.append({"name": name, "status": "unknown" if verdict is None else "pass" if verdict else "fail", "evidence": evidence})
    if subject["role"] in ("worker", "orchestrator", "reviewer"):
        check("Conversation captured", subject.get("conversationCoverage") == "available history captured" if subject.get("conversationCoverage") else None, subject.get("conversationCoverage"))
        check("Turns finish without errors", all(t.get("state") == "completed" for t in turns) if turns else None, {"turns": len(turns), "states": [t.get("state") for t in turns]})
        commands = [a for a in activities if a.get("activityKind") == "command"]
        exits = [a.get("detail", {}).get("exitCode") for a in commands]
        check("Observed commands succeed", all(x == 0 for x in exits) if exits and all(x is not None for x in exits) else None, {"commands": len(commands), "exitCodes": exits})
    if subject["role"] == "orchestrator":
        children = [s["id"] for s in store.subjects() if s.get("parentId") == subject["id"] and s.get("role") == "worker"]
        check("Delegation has attributed workers", True if children else None, children or "No attributed worker evidence; some goals need no delegation")
    elif subject["role"] == "worker":
        if subject.get("probeId"):
            result = list(store.all_events(subject["probeId"], kinds=["benchmark.completed"]))
            check("Role probe passed independent grading", result[-1]["data"].get("status") == "pass" if result and result[-1]["data"].get("score") is not None else None, result[-1]["data"] if result else None)
        else:
            check("Latest saved gate assessment passed (point-in-time)", gates[-1]["ready"] if gates else None, gates[-1] if gates else "No gate assessment")
    elif subject["role"] == "reviewer":
        check("Review is bound to a PR and commit", all(r.get("targetSha") and r.get("prUrl") for r in reviews) if reviews else None, [{"id": r.get("id"), "head": r.get("targetSha"), "prUrl": r.get("prUrl")} for r in reviews])
        completed = [r for r in reviews if r.get("status") in ("complete", "completed", "delivered")]
        check("Completed verdicts have findings or approval", all(r.get("verdict") in ("approved", "changes_requested") and (r.get("verdict") != "changes_requested" or bool(r.get("body", "").strip())) for r in completed) if completed else None, [{"id": r.get("id"), "verdict": r.get("verdict"), "status": r.get("status")} for r in reviews])
    elif subject["role"] == "gate":
        check("Latest saved handoff assessment passed (point-in-time)", gates[-1]["ready"] if gates else None, gates[-1] if gates else None)
    elif subject["role"] == "ci":
        observations = [e["data"] for e in events if e["kind"] == "ci.observed"]
        checks_observed = observations[-1].get("checks", []) if observations else []
        check("Observed CI checks succeeded", all(c.get("conclusion") == "SUCCESS" if c.get("__typename") == "CheckRun" else c.get("state") == "SUCCESS" for c in checks_observed) if checks_observed else None, checks_observed)
    failed, unknown = sum(c["status"] == "fail" for c in checks), sum(c["status"] == "unknown" for c in checks)
    durations = []
    for turn in turns:
        try:
            durations.append((dt.datetime.fromisoformat(turn["completedAt"].replace("Z", "+00:00")) - dt.datetime.fromisoformat(turn["startedAt"].replace("Z", "+00:00"))).total_seconds())
        except (KeyError, ValueError, TypeError):
            pass
    return {"suite": "operational-evidence-v1", "rubricHash": RUBRIC_HASH, "subjectId": subject["id"], "role": subject["role"],
            "assessedAt": now(), "status": "fail" if failed else "unknown" if unknown else "pass", "checks": checks,
            "metrics": {"turns": len(turns), "activities": len(activities), "reviewRuns": len(reviews),
                        "gateAssessments": len(gates), "usage": subject.get("usage"), "costUsd": None,
                        "completedTurnSeconds": sum(durations) if durations else None},
            "meaning": "Evidence diagnostics, not a measure of engineering correctness. Unknown values are unscored."}
