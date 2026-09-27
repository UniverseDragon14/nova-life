#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/aslam/nova-life").resolve()
BIN = ROOT / "bin"
NOVA_HOME = Path(os.environ.get("NOVA_HOME", "/home/aslam/nova_home"))
STATE = NOVA_HOME / "autocode"
LOG = STATE / "logs" / "autocode.jsonl"
BACKUPS = STATE / "backups"
MODEL = os.environ.get("NOVA_AUTOCODE_MODEL", "llama3.2:latest")
ENABLED = os.environ.get("NOVA_AUTOCODE_ENABLED", "1") == "1"

STATE.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(parents=True, exist_ok=True)
BACKUPS.mkdir(parents=True, exist_ok=True)

def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def log(event, **extra):
    row = {"ts": stamp(), "event": event, **extra}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False), flush=True)

def run(cmd, timeout=60):
    p = subprocess.run(
        cmd, cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False,
    )
    return p.returncode, p.stdout[-4000:], p.stderr[-4000:]

def source_files():
    files = []
    for f in sorted(BIN.iterdir()):
        if not f.is_file() or ".bak-" in f.name:
            continue
        if f.suffix in {".py", ".sh"}:
            files.append(f)
    return files

def syntax_check(path):
    if path.suffix == ".py":
        return run(["python3", "-m", "py_compile", str(path)], 30)
    if path.suffix == ".sh":
        return run(["bash", "-n", str(path)], 30)
    return 0, "", ""

def project_tests():
    tests = [
        ["python3", "bin/nova_voice_agent_v2.py", "--self-test"],
        ["bash", "bin/dragon_verify.sh"],
        ["bash", "-lc", "cd /home/aslam/qbit-nova-language/c-implementation/specification/v0.1 && sha256sum -c SPEC_MANIFEST.sha256 >/dev/null"],
        ["/home/aslam/qbit-nova-native/qbit-nova-native-v0.5-dev/build/qnova", "gpu", "compute-proof", "--backend", "vulkan"],
        ["/home/aslam/qbit-nova-native/qbit-nova-native-v0.5-dev/build/qnova", "run", "/home/aslam/qbit-nova-native/qbit-nova-native-v0.5-dev/examples/vector_add_u32.qn", "--backend", "vulkan"],
        ["/home/aslam/qbit-nova-c/qnova", "/home/aslam/qbit-nova-c/examples/bell_state2.qn"],
        ["v4l2-ctl", "-d", "/dev/video0", "--get-fmt-video"],
    ]

    failures = []
    for cmd in tests:
        code, out, err = run(cmd, 90)
        if code != 0:
            failures.append({
                "cmd": cmd,
                "code": code,
                "out": out,
                "err": err,
            })
    return failures

def find_issue():
    for path in source_files():
        code, out, err = syntax_check(path)
        if code != 0:
            return {
                "kind": "syntax",
                "path": path,
                "detail": (out + "\n" + err).strip()[-5000:],
            }
    failures = project_tests()
    if failures:
        failure = failures[0]
        detail = json.dumps(failure, ensure_ascii=False)
        cmd_text = " ".join(failure.get("cmd", []))
        if "nova_voice_agent_v2.py" in cmd_text:
            target = BIN / "nova_voice_agent_v2.py"
            return {"kind": "test", "path": target, "detail": detail[-5000:]}
        return {"kind": "proposal", "path": None, "detail": detail[-5000:]}
    return None

def ask_local_model(path, detail):
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > 50000:
        raise RuntimeError("target file too large for bounded auto repair")
    prompt = f"""You are a local code repair engine.
Return ONLY one JSON object with keys old_string, new_string, reason.
Make the smallest possible repair for the reported failure.
old_string MUST be an exact unique substring copied from the file.
Do not add network calls, sudo, deletion, credential access, hardware motion,
service control, subprocess shell=True, eval, exec, or new external dependencies.
Do not weaken existing safety rules.

FILE: {path}
FAILURE:
{detail}

CONTENT:
{text}
"""

    code, out, err = run(["ollama", "run", MODEL, prompt], 180)
    if code != 0:
        raise RuntimeError("local model failed: " + err[-1000:])
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("local model returned no JSON")
    obj = json.loads(m.group(0))
    old = obj.get("old_string", "")
    new = obj.get("new_string", "")
    reason = obj.get("reason", "")
    if not old or old == new:
        raise RuntimeError("invalid/no-op patch")
    return old, new, reason

def safe_target(path):
    rp = path.resolve()
    try:
        rp.relative_to(ROOT)
    except ValueError:
        return False
    return rp.parent == BIN and rp.suffix in {".py", ".sh"}

def backup(path):
    tag = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest_dir = BACKUPS / tag
    dest_dir.mkdir(parents=True, exist_ok=False)
    dest = dest_dir / path.name
    shutil.copy2(path, dest)
    return dest

def validate_all():
    errors = []
    for path in source_files():
        code, out, err = syntax_check(path)
        if code != 0:
            errors.append(f"{path.name}: {(out + err)[-1200:]}")
    for failure in project_tests():
        errors.append(json.dumps(failure, ensure_ascii=False)[-1500:])
    return errors

def main():
    if not ENABLED:
        log("disabled")
        return 0

    issue = find_issue()
    if not issue:
        log("healthy", model=MODEL)
        return 0

    path = issue.get("path")
    if path is None:
        log("proposal_needed", reason=issue["detail"][-1200:])
        return 2
    if not safe_target(path):
        log("proposal_needed", reason="unsafe target", path=str(path))
        return 2

    log("issue_found", kind=issue["kind"], path=str(path),
        detail=issue["detail"][-1200:])

    try:
        old, new, reason = ask_local_model(path, issue["detail"])
    except Exception as exc:
        log("proposal_needed", reason=str(exc), path=str(path))
        return 3

    current = path.read_text(encoding="utf-8")
    if current.count(old) != 1:
        log("proposal_needed", reason="old_string not unique", path=str(path))
        return 4

    b = backup(path)
    mode = path.stat().st_mode
    path.write_text(current.replace(old, new, 1), encoding="utf-8")
    os.chmod(path, mode)

    errors = validate_all()
    if errors:
        shutil.copy2(b, path)
        log("rollback", path=str(path), backup=str(b),
            reason="validation failed", errors=errors[:4])
        return 5

    log("patch_applied", path=str(path), backup=str(b),
        reason=reason[:500], model=MODEL)
    run([
        "python3", "bin/nova_self.py", "remember",
        f"Auto Code repaired {path.name}: {reason[:160]}", "6"
    ], 20)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
