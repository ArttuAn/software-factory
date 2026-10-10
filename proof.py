"""Capture real commands and compare before/after evidence for human review."""
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from observability import now, redact

OUTPUT_LIMIT = 65536
ARTIFACT_LIMIT = 25 * 1024 * 1024
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
         ".mp4": "video/mp4", ".webm": "video/webm"}


def git(workspace, *args):
    return subprocess.run(["git", "-C", str(workspace), *args], capture_output=True,
                          text=True, check=True, timeout=20).stdout.strip()


def snapshot(workspace):
    return {"headSha": git(workspace, "rev-parse", "HEAD"),
            "clean": not git(workspace, "status", "--porcelain", "--untracked-files=normal")}


def capture(workspace, phase, criterion, command, expected_exit=0, timeout=120):
    workspace = Path(workspace).resolve(strict=True)
    if phase not in ("before", "after") or not isinstance(criterion, str) or not criterion.strip() or len(criterion) > 500:
        raise ValueError("Choose before/after and an acceptance criterion of 1-500 characters")
    if not command or any(not isinstance(arg, str) for arg in command):
        raise ValueError("Supply a command after --")
    if not 1 <= timeout <= 600 or not 0 <= expected_exit <= 255 or (phase == "after" and expected_exit != 0):
        raise ValueError("Timeout must be 1-600 seconds; after proof must expect exit 0")
    before = snapshot(workspace)
    if not before["clean"]:
        raise ValueError("Proof requires a clean committed worktree, including untracked files")
    started = time.monotonic()
    timed_out = False
    # Disk-backed output bounds memory even when a check prints a large log.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, cwd=workspace, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        size = output.tell()
        output.seek(0)
        text = redact(output.read(OUTPUT_LIMIT).decode("utf-8", errors="replace"))
    after = snapshot(workspace)
    stable = before == after
    return {"schema": 1, "phase": phase, "criterion": criterion.strip(),
            "command": redact(command), "headSha": before["headSha"],
            "exitCode": process.returncode, "expectedExitCode": expected_exit,
            "timedOut": timed_out, "snapshotStable": stable,
            "passed": not timed_out and stable and process.returncode == expected_exit,
            "output": text, "outputSha256": hashlib.sha256(text.encode()).hexdigest(),
            "outputTruncated": size > OUTPUT_LIMIT, "outputBytes": size,
            "durationSeconds": round(time.monotonic() - started, 3), "capturedAt": now()}


def attach(state, paths):
    artifacts = []
    directory = Path(state) / "proof-artifacts"
    for path in paths:
        path = Path(path).resolve(strict=True)
        suffix = path.suffix.lower()
        if suffix not in MEDIA or not path.is_file() or not 0 < path.stat().st_size <= ARTIFACT_LIMIT:
            raise ValueError("Proof attachments must be PNG, JPG, WebP, MP4 or WebM files of 1 byte to 25 MiB")
        with path.open("rb") as source:
            raw = source.read(ARTIFACT_LIMIT + 1)
        if len(raw) > ARTIFACT_LIMIT:
            raise ValueError("Proof attachment exceeded 25 MiB while reading")
        sha = hashlib.sha256(raw).hexdigest()
        name = sha + suffix
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = directory / name
        # Content addressing keeps each before/after attachment even if its source is overwritten.
        with destination.open("wb") as target:
            os.chmod(destination, 0o600)
            target.write(raw)
        artifacts.append({"id": name, "sha256": sha, "bytes": len(raw), "mediaType": MEDIA[suffix],
                          "provenance": "Operator-supplied attachment; content captured, meaning requires review"})
    return artifacts


def assess(events, head, state):
    latest = {}
    for event in events:
        data = event["data"]
        latest.setdefault(data["criterion"], {})[data["phase"]] = event
    reasons, pairs = [], []
    if not head:
        reasons.append("Supply a PR head SHA to assess current-head proof")
    if not latest:
        reasons.append("No captured before/after proof")
    for criterion, phases in latest.items():
        before, after = phases.get("before"), phases.get("after")
        errors = []
        if not before or not after:
            errors.append("Both before and after captures are required")
        else:
            b, a = before["data"], after["data"]
            if not b["passed"] or not a["passed"]:
                errors.append("A proof command failed, timed out or changed the worktree")
            if head and a["headSha"] != head:
                errors.append("After proof does not match the current PR head")
            if b["headSha"] == a["headSha"]:
                errors.append("Before and after proof must describe different commits")
            if b["command"] != a["command"]:
                errors.append("Before and after must run the same comparison command")
            if a.get("beforeHash") != before["hash"] or not a.get("baselineAncestor"):
                errors.append("After proof is not bound to this earlier ancestor capture")
            for event in (before, after):
                data = event["data"]
                if hashlib.sha256(data["output"].encode()).hexdigest() != data["outputSha256"]:
                    errors.append("Captured output digest mismatch")
                for artifact in data.get("artifacts", []):
                    path = Path(state) / "proof-artifacts" / artifact["id"]
                    if path.name != artifact["id"] or not path.is_file() or path.stat().st_size != artifact["bytes"]:
                        errors.append("Proof attachment is missing or has changed")
                    elif hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                        errors.append("Proof attachment digest mismatch")
        reasons.extend(f"{criterion}: {error}" for error in errors)
        pairs.append({"criterion": criterion, "ready": not errors,
                      "before": before["data"] if before else None,
                      "after": after["data"] if after else None})
    return {"ready": not reasons, "headSha": head, "reasons": reasons, "pairs": pairs,
            "meaning": "Captured execution and attachment integrity, not proof that requirements are sufficient. Independent review must judge coverage and meaning."}
