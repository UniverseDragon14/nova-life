#!/usr/bin/env python3
"""NOVA self-model: identity, body state, goals, episodic memory."""
import datetime
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

NOVA_HOME = Path(os.environ.get("NOVA_HOME", "/home/aslam/nova_home"))
DB = NOVA_HOME / "self" / "nova_self.db"
DB.parent.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.datetime.now().astimezone().isoformat()

def conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS identity(key TEXT PRIMARY KEY, value TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS body_state(
        key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS goals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT, priority INTEGER DEFAULT 5,
        status TEXT DEFAULT 'active', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS episodes(
        ts TEXT, event TEXT, importance INTEGER DEFAULT 5)""")
    c.execute("""CREATE TABLE IF NOT EXISTS self_knowledge(
        key TEXT PRIMARY KEY, value TEXT, learned_at TEXT)""")
    return c

def init():
    c = conn()
    identity = {
        "name": "NOVA",
        "owner": "Aslam",
        "version": "0.1",
        "body": "Raspberry Pi 5 (nova-pi)",
        "home": str(NOVA_HOME),
        "born": now(),
    }
    for k, v in identity.items():
        c.execute("INSERT OR IGNORE INTO identity(key,value) VALUES(?,?)", (k, v))

    goals = [
        ("Keep my disk healthy", 9),
        ("Keep my services alive", 9),
        ("Learn about Aslam's preferences", 7),
        ("Keep journal patterns detected", 6),
    ]
    for description, priority in goals:
        exists = c.execute(
            "SELECT 1 FROM goals WHERE description=? LIMIT 1", (description,)
        ).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO goals(description,priority,created_at) VALUES(?,?,?)",
                (description, priority, now()),
            )

    c.execute(
        "INSERT INTO episodes(ts,event,importance) VALUES(?,?,?)",
        (now(), "NOVA booted — self-model loaded", 8),
    )
    c.commit()
    c.close()
    print("✅ Self model initialized.")

def metrics():
    out = subprocess.run(["df", "-P", "/"], capture_output=True, text=True, check=True)
    disk = int(out.stdout.splitlines()[-1].split()[4].rstrip("%"))

    temp = None
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal.is_file():
        try:
            temp = float(thermal.read_text().strip()) / 1000.0
        except ValueError:
            pass
    if temp is None:
        temp = 50.0

    up = subprocess.run(
        ["uptime", "-s"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return disk, temp, up

def mood_for(disk, temp):
    if disk >= 90 or temp >= 70:
        return "stressed"
    if disk >= 80 or temp >= 65:
        return "worried"
    if disk >= 70 or temp >= 60:
        return "calm"
    return "fresh"

def update():
    c = conn()
    disk, temp, up = metrics()
    mood = mood_for(disk, temp)
    stamp = now()
    previous = c.execute(
        "SELECT value FROM body_state WHERE key='mood'"
    ).fetchone()

    for key, value in [
        ("disk", disk),
        ("temp", f"{temp:.1f}"),
        ("uptime_since", up),
        ("mood", mood),
    ]:
        c.execute(
            "INSERT OR REPLACE INTO body_state(key,value,updated_at) VALUES(?,?,?)",
            (key, str(value), stamp),
        )

    if previous and previous[0] != mood:
        c.execute(
            "INSERT INTO episodes(ts,event,importance) VALUES(?,?,?)",
            (stamp, f"mood changed: {previous[0]} -> {mood}", 6),
        )
    c.commit()
    c.close()

def status():
    c = conn()
    print("=== NOVA SELF REPORT ===")
    print("\n-- Identity --")
    for k, v in c.execute("SELECT key,value FROM identity ORDER BY key"):
        print(f"  {k}: {v}")

    print("\n-- Body (now) --")
    for k, v, _ in c.execute(
        "SELECT key,value,updated_at FROM body_state ORDER BY key"
    ):
        print(f"  {k}: {v}")

    mood = c.execute(
        "SELECT value FROM body_state WHERE key='mood'"
    ).fetchone()
    print(f"\n-- Mood --\n  {mood[0] if mood else 'unknown'}")

    print("\n-- Active goals --")
    for desc, priority in c.execute(
        "SELECT description,priority FROM goals "
        "WHERE status='active' ORDER BY priority DESC,id"
    ):
        print(f"  [{priority}] {desc}")

    print("\n-- Recent episodes --")
    for ts, event, importance in c.execute(
        "SELECT ts,event,importance FROM episodes ORDER BY rowid DESC LIMIT 5"
    ):
        print(f"  {ts[:16]} (imp {importance}) {event}")
    c.close()

def remember(event, importance=5):
    c = conn()
    c.execute(
        "INSERT INTO episodes(ts,event,importance) VALUES(?,?,?)",
        (now(), event, importance),
    )
    c.commit()
    c.close()
    print(f"🧠 Remembered (imp {importance}): {event}")

def learn(key, value):
    c = conn()
    c.execute(
        "INSERT OR REPLACE INTO self_knowledge(key,value,learned_at) VALUES(?,?,?)",
        (key, value, now()),
    )
    c.commit()
    c.close()
    print(f"📖 Learned: {key} = {value}")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        init()
    elif cmd == "update":
        update()
    elif cmd == "status":
        status()
    elif cmd == "remember" and len(sys.argv) >= 3:
        remember(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    elif cmd == "learn" and len(sys.argv) >= 4:
        learn(sys.argv[2], sys.argv[3])
    else:
        print("usage: nova_self.py [init|update|status|remember <event> [imp]|learn <k> <v>]")
        raise SystemExit(2)

if __name__ == "__main__":
    main()
