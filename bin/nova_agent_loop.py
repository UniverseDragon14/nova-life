#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/aslam/nova-life")
HOME = Path("/mnt/extra_sd/nova_home")
STATE_DIR = HOME / "agent"
STATE_FILE = STATE_DIR / "agent_state.json"
LOG_FILE = STATE_DIR / "agent.jsonl"
PENDING = ROOT / "proposals" / "pending"
INTERVAL = int(os.environ.get("NOVA_AGENT_INTERVAL", "60"))

STATE_DIR.mkdir(parents=True, exist_ok=True)
PENDING.mkdir(parents=True, exist_ok=True)
RUNNING = True

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def run(cmd, timeout=45):
    p = subprocess.run(cmd, cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout, check=False)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def log(event, **extra):
    row = {"ts": now(), "event": event, **extra}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False), flush=True)

def load_state():
    if not STATE_FILE.exists():
        return {"last_heartbeat": 0, "last_observe": 0,
                "last_healthy_memory": 0, "action_stats": {},
                "issue_seen": {}, "decision_spoken": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_heartbeat": 0, "last_observe": 0,
                "last_healthy_memory": 0, "action_stats": {},
                "issue_seen": {}, "decision_spoken": {}}

def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(STATE_FILE)

def proc_running(pattern):
    code, out, _ = run(["pgrep", "-f", pattern], 10)
    return code == 0 and bool(out.strip())

def read_camera():
    path = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")) / "nova_presence.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("camera_ok")), bool(data.get("present"))
    except Exception:
        return False, False

def vitals():
    code, out, err = run(["bash", "bin/nova_vitals.sh"], 15)
    if code != 0:
        return {"ok": False, "raw": err[-300:]}
    disk = temp = None
    for token in out.split():
        if token.startswith("disk="):
            try: disk = int(token.split("=", 1)[1].rstrip("%"))
            except ValueError: pass
        if token.startswith("temp="):
            try: temp = float(token.split("=", 1)[1].rstrip("Cc"))
            except ValueError: pass
    return {"ok": True, "disk": disk, "temp": temp, "raw": out[-300:]}

def observe_world():
    v = vitals()
    camera_ok, present = read_camera()
    core_code, _, _ = run(["bash", "bin/dragon_verify.sh"], 20)
    return {
        "vitals": v,
        "core_ok": core_code == 0,
        "voice_agent": proc_running("nova_voice_agent_v2.py"),
        "camera_process": proc_running("nova_camera_presence.py"),
        "camera_ok": camera_ok,
        "present": present,
    }

def understand(obs):
    issues = []
    v = obs["vitals"]
    if not obs["core_ok"]:
        issues.append(("core_integrity", "Core verification failed"))
    if not obs["voice_agent"]:
        issues.append(("voice_agent_down", "NOVA voice agent is not running"))
    if not obs["camera_process"]:
        issues.append(("camera_process_down", "NOVA camera presence process is not running"))
    elif not obs["camera_ok"]:
        issues.append(("camera_unavailable", "Camera process is alive but no usable camera frame is available"))
    if v.get("disk") is not None and v["disk"] >= 85:
        issues.append(("disk_high", f"Root disk usage is {v['disk']}%"))
    if v.get("temp") is not None and v["temp"] >= 70:
        issues.append(("temp_high", f"Pi temperature is {v['temp']} C"))
    return issues

def safe_slug(value):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in value)

def ensure_proposal(issue_id, detail):
    pid = "agent-" + safe_slug(issue_id)
    path = PENDING / f"{pid}.json"
    if path.exists():
        return "already_pending"
    data = {
        "id": pid, "created": now(), "observation": detail,
        "suggestion": "Inspect and repair this condition; request owner approval before service, hardware, network, credential, or system-wide changes.",
        "risk": "Agent did not perform risky recovery automatically.",
        "status": "pending"
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return "created"

def remember_once(state, issue_id, detail):
    seen = state.setdefault("issue_seen", {})
    last = float(seen.get(issue_id, 0))
    if time.time() - last < 3600:
        return
    run(["python3", "bin/nova_self.py", "remember",
         f"Agent observed {issue_id}: {detail}", "5"], 20)
    seen[issue_id] = time.time()

def record_action(state, name, ok):
    stats = state.setdefault("action_stats", {}).setdefault(
        name, {"success": 0, "failure": 0})
    stats["success" if ok else "failure"] += 1

def speak_decision(state, issue_id, detail):
    spoken = state.setdefault("decision_spoken", {})
    last = float(spoken.get(issue_id, 0))
    if time.time() - last < 3600:
        return "cooldown"
    messages = {
        "core_integrity": "அஸ்லாம் பாஸ், நோவா கோர் verification fail ஆகியிருக்கிறது. மாற்றம் செய்யாமல் நிறுத்தியிருக்கேன். உங்கள் approval தேவை.",
        "voice_agent_down": "அஸ்லாம் பாஸ், நோவா voice agent down ஆகியிருக்கிறது. repair செய்ய உங்கள் approval தேவை.",
        "camera_process_down": "அஸ்லாம் பாஸ், camera process down ஆகியிருக்கிறது. repair செய்ய உங்கள் approval தேவை.",
        "camera_unavailable": "அஸ்லாம் பாஸ், camera process ஓடுகிறது, ஆனால் camera frame கிடைக்கவில்லை. இதை சரி செய்ய உங்கள் approval தேவை.",
        "temp_high": "அஸ்லாம் பாஸ், Raspberry Pi temperature அதிகமாக இருக்கிறது. அடுத்த action எடுக்க உங்கள் approval தேவை.",
        "disk_high": "அஸ்லாம் பாஸ், root disk usage அதிகமாக இருக்கிறது. cleanup செய்யும் முன் உங்கள் approval தேவை.",
    }
    text = messages.get(issue_id, f"அஸ்லாம் பாஸ், ஒரு NOVA decision தேவை. {detail}")
    code, out, err = run(["bash", "bin/nova_speak.sh", text, "auto", "0.65"], 120)
    if code == 0:
        spoken[issue_id] = time.time()
        return "spoken"
    return "speak_failed:" + (err or out)[-120:]

def act(state, obs, issues):
    actions = []
    t = time.time()

    if t - float(state.get("last_heartbeat", 0)) >= 300:
        code, out, err = run(["bash", "bin/nova_heartbeat.sh"], 30)
        ok = code == 0
        record_action(state, "heartbeat", ok)
        actions.append({"action": "heartbeat", "ok": ok,
                        "detail": (out or err)[-300:]})
        state["last_heartbeat"] = t

    disk = obs["vitals"].get("disk")
    if t - float(state.get("last_observe", 0)) >= 900 or (disk is not None and disk >= 85):
        code, out, err = run(["bash", "bin/nova_observe.sh"], 30)
        ok = code == 0
        record_action(state, "observe", ok)
        actions.append({"action": "observe", "ok": ok,
                        "detail": (out or err)[-300:]})
        state["last_observe"] = t

    for issue_id, detail in issues:
        remember_once(state, issue_id, detail)
        if issue_id in {
            "core_integrity", "voice_agent_down", "camera_process_down",
            "camera_unavailable", "temp_high", "disk_high"
        }:
            result = ensure_proposal(issue_id, detail)
            voice_result = speak_decision(state, issue_id, detail)
            actions.append({"action": "proposal", "issue": issue_id,
                            "result": result, "voice": voice_result})

    return actions

def learn_cycle(state, obs, issues, actions):
    summary = {
        "issues": [i[0] for i in issues],
        "actions": [a.get("action") for a in actions],
        "core_ok": obs["core_ok"],
        "camera_ok": obs["camera_ok"],
        "voice_agent": obs["voice_agent"],
    }
    run(["python3", "bin/nova_self.py", "learn",
         "agent.last_cycle", json.dumps(summary, ensure_ascii=False)], 20)

    if not issues and time.time() - float(state.get("last_healthy_memory", 0)) >= 3600:
        run(["python3", "bin/nova_self.py", "remember",
             "NOVA agent cycle healthy: core, voice and monitored local state are normal.",
             "3"], 20)
        state["last_healthy_memory"] = time.time()

def one_cycle(state):
    obs = observe_world()
    issues = understand(obs)
    actions = act(state, obs, issues)
    learn_cycle(state, obs, issues, actions)
    log("cycle", observation=obs,
        issues=[{"id": x, "detail": y} for x, y in issues],
        actions=actions)
    save_state(state)
    return obs, issues, actions

def stop_handler(signum, frame):
    global RUNNING
    RUNNING = False

def main():
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    state = load_state()
    log("agent_start", interval=INTERVAL,
        policy="bounded-local-agent; risky actions require proposal/approval")

    while RUNNING:
        started = time.monotonic()
        try:
            one_cycle(state)
        except Exception as exc:
            log("cycle_error", error=type(exc).__name__,
                detail=str(exc)[:500])
        if "--once" in sys.argv:
            break
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL - elapsed))

    save_state(state)
    log("agent_stop")

if __name__ == "__main__":
    main()
