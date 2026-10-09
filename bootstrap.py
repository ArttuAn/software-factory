#!/usr/bin/env python3
"""Reproduce the bundled Linux x64 runtime from the pinned official release."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent
manifest = json.loads((root / "UPSTREAM.json").read_text())
if platform.system() != "Linux" or platform.machine() != "x86_64":
    raise SystemExit("This bootstrap targets Linux x64. Use the upstream desktop release for other platforms.")
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    subprocess.run(["gh", "release", "download", manifest["tag"], "--repo", "OrchestratorInc/agent-orchestrator", "--pattern", manifest["asset"], "--dir", directory], check=True)
    package = work / manifest["asset"]
    if hashlib.sha256(package.read_bytes()).hexdigest() != manifest["asset_sha256"]:
        raise SystemExit("Release checksum mismatch")
    subprocess.run(["dpkg-deb", "-x", str(package), str(work / "extracted")], check=True)
    binary = work / "extracted/usr/lib/agent-orchestrator/resources/daemon/ao"
    if hashlib.sha256(binary.read_bytes()).hexdigest() != manifest["daemon_sha256"]:
        raise SystemExit("Daemon checksum mismatch")
    (root / "runtime").mkdir(exist_ok=True)
    shutil.copy2(binary, root / "runtime/ao")
print("Installed verified Agent Orchestrator " + manifest["tag"])
