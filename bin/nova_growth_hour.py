#!/usr/bin/env python3
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/aslam/nova-life")
NOVA_HOME = Path(os.environ.get("NOVA_HOME", "/home/aslam/nova_home"))
EXP_ROOT = NOVA_HOME / "experiments"
DURATION = 60 * 60
INTERVAL = 60

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def run(cmd, timeout=20):
    try:
        p = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "code": p.returncode,
            "out": p.stdout.strip()[-2000:],
            "err": p.stderr.strip()[-1000:],
        }
    except Exception as e:
        return {"code": 99, "out": "", "err": type(e).__name__ + ": " + str(e)[:300]}

def parse_vitals(text):
    disk = None
    temp = None
    m = re.search(r"disk=(\d+)%", text or "")
    if m:
        disk = int(m.group(1))
    m = re.search(r"temp=([0-9.]+)", text or "")
    if m:
        try:
            temp = float(m.group(1))
        except ValueError:
            pass
    return disk, temp

def count_json(path):
    try:
        return len(list(Path(path).glob("*.json")))
    except Exception:
        return 0

def git_dirty_count():
    r = run(["git", "status", "--porcelain"], timeout=10)
    if r["code"] != 0:
        return None
    return len([x for x in r["out"].splitlines() if x.strip()])

def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def main():
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    exp = EXP_ROOT / ("self-growth-" + stamp)
    exp.mkdir(parents=True, exist_ok=False)
    os.chmod(exp, 0o700)

    obs_file = exp / "observations.jsonl"
    cand_file = exp / "candidate_improvements.md"
    summary_file = exp / "summary.md"
    policy_file = exp / "POLICY.txt"

    policy = """NOVA Life one-hour self-growth sandbox
Allowed without owner approval:
- read-only local observation
- NOVA self/body-state updates
- NOVA memory/self-knowledge notes
- proposal generation
- files written only inside this experiment directory
Disallowed:
- deployment
- external network actions
- service or system configuration changes
- production code patching
- auth/credential changes
- hardware/robot motion
- deletion or cleanup
"""
    policy_file.write_text(policy, encoding="utf-8")

    run(["python3", "bin/nova_self.py", "remember",
         "Started one-hour sandbox self-growth experiment; risky actions remain approval-gated.", "4"])
    run(["python3", "bin/nova_self.py", "learn",
         "growth.experiment_policy",
         "sandbox-only: observe, learn, remember, propose; no deploy/network/system/motion"])

    start = time.monotonic()
    cycles = 0
    disk_samples = []
    temp_samples = []
    proposals_seen = set()
    suggestions = []

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= DURATION:
            break

        cycles += 1
        hb = run(["bash", "bin/nova_heartbeat.sh"], timeout=25)
        vitals = run(["bash", "bin/nova_vitals.sh"], timeout=15)
        core = run(["bash", "bin/dragon_verify.sh"], timeout=15)
        dirty = git_dirty_count()

        if cycles == 1 or cycles % 5 == 0:
            observe = run(["bash", "bin/nova_observe.sh"], timeout=20)
        else:
            observe = {"code": 0, "out": "not_due", "err": ""}

        disk, temp = parse_vitals(vitals["out"])
        if disk is not None:
            disk_samples.append(disk)
        if temp is not None:
            temp_samples.append(temp)

        pending_dir = ROOT / "proposals" / "pending"
        current_props = {p.name for p in pending_dir.glob("*.json")}
        proposals_seen |= current_props

        ideas = []
        if disk is not None and disk > 85:
            ideas.append("storage pressure recurring: prepare read-only largest-files analysis")
        if temp is not None and temp >= 75:
            ideas.append("thermal pressure: propose workload throttling review")
        if core["code"] != 0:
            ideas.append("core verification failed: propose integrity review")
        if dirty not in (None, 0):
            ideas.append(f"workspace has {dirty} uncommitted paths: preserve before any future patch")
        if len(current_props) > 0:
            ideas.append(f"{len(current_props)} pending proposal(s): avoid duplicate proposals")

        for idea in ideas:
            if idea not in suggestions:
                suggestions.append(idea)
                with open(cand_file, "a", encoding="utf-8") as f:
                    f.write(f"- {now_iso()} — {idea}\n")

        summary = (
            f"cycle={cycles}; disk={disk}; temp={temp}; "
            f"core={'ok' if core['code']==0 else 'alert'}; "
            f"pending={len(current_props)}; git_dirty={dirty}"
        )
        run(["python3", "bin/nova_self.py", "learn", "growth.last_observation", summary])

        append_jsonl(obs_file, {
            "ts": now_iso(),
            "cycle": cycles,
            "elapsed_s": round(elapsed, 1),
            "disk_percent": disk,
            "temp_c": temp,
            "core_ok": core["code"] == 0,
            "pending_proposals": sorted(current_props),
            "git_dirty_count": dirty,
            "heartbeat_code": hb["code"],
            "observe": observe["out"][:500],
            "ideas": ideas,
        })

        remaining = DURATION - (time.monotonic() - start)
        if remaining <= 0:
            break
        time.sleep(min(INTERVAL, remaining))

    avg_disk = round(sum(disk_samples)/len(disk_samples), 2) if disk_samples else None
    avg_temp = round(sum(temp_samples)/len(temp_samples), 2) if temp_samples else None
    max_temp = max(temp_samples) if temp_samples else None
    final = [
        "# NOVA Life — One-Hour Self-Growth Sandbox Summary",
        "",
        f"- Started: {stamp}",
        f"- Completed: {now_iso()}",
        f"- Cycles: {cycles}",
        f"- Average disk use: {avg_disk}%",
        f"- Average temperature: {avg_temp} C",
        f"- Maximum temperature: {max_temp} C",
        f"- Proposals observed: {len(proposals_seen)}",
        f"- Unique improvement ideas: {len(suggestions)}",
        "",
        "## Safety boundary",
        "No deployment, external network action, system/service modification, credential change, deletion, or robot motion was permitted by this experiment.",
        "",
        "## Candidate improvements",
    ]
    final.extend(["- " + x for x in suggestions] or ["- No new candidate improvements generated."])
    summary_file.write_text("\n".join(final) + "\n", encoding="utf-8")

    run(["python3", "bin/nova_self.py", "learn",
         "growth.last_experiment",
         f"completed {cycles} cycles; ideas={len(suggestions)}; path={exp}"])
    run(["python3", "bin/nova_self.py", "remember",
         f"Completed one-hour sandbox self-growth experiment with {cycles} cycles and {len(suggestions)} candidate improvements.", "5"])

    print(str(exp))

if __name__ == "__main__":
    main()
