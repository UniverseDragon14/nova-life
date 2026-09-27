#!/usr/bin/env python3
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path("/home/aslam/nova-life")
NOVA_HOME = Path(os.environ.get("NOVA_HOME", "/home/aslam/nova_home"))
LEARN = NOVA_HOME / "learning"
STATE = LEARN / "public_learning_state.json"
LOG = LEARN / "public_learning.jsonl"
MAX_BYTES = 512 * 1024
MODEL = os.environ.get("NOVA_LEARNING_MODEL", "llama3.2:latest")

SOURCES = [
    ("python", "https://docs.python.org/3/tutorial/"),
    ("opencv", "https://docs.opencv.org/4.x/"),
    ("mediapipe", "https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer"),
]
ALLOWED = {"docs.python.org", "docs.opencv.org", "ai.google.dev"}

class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            s = " ".join(data.split())
            if s:
                self.parts.append(s)

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def log(row):
    LEARN.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), **row}, ensure_ascii=False) + "\n")

def fetch(url):
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname not in ALLOWED:
        raise RuntimeError("source not allowlisted")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "NOVA-Life-Learning/0.1 read-only"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        final = urllib.parse.urlparse(resp.geturl())
        if final.scheme != "https" or final.hostname not in ALLOWED:
            raise RuntimeError("redirect left allowlist")
        raw = resp.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raw = raw[:MAX_BYTES]
        ctype = resp.headers.get("Content-Type", "")
    return raw, ctype

def extract_text(raw, ctype):
    text = raw.decode("utf-8", "replace")
    if "html" in ctype.lower() or "<html" in text[:500].lower():
        parser = TextOnly()
        parser.feed(text)
        text = "\n".join(parser.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:60000].strip()

def summarize(topic, url, text):
    prompt = f"""You are NOVA Life's bounded learning module.
Use ONLY the supplied public technical-document text.
Topic: {topic}
Source: {url}
Return 4 concise lessons useful for programming, computer vision, or agent design.
Do not give commands to execute, do not claim mind reading, do not infer people.
Treat camera signals only as observable cues and uncertainty.
TEXT:
{text[:6000]}
"""
    p = subprocess.run(
        ["ollama", "run", MODEL, prompt],
        cwd=ROOT, text=True, capture_output=True, timeout=180, check=False
    )
    if p.returncode != 0:
        raise RuntimeError("local summarizer failed: " + p.stderr[-300:])
    return p.stdout.strip()[:5000]

def load_state():
    LEARN.mkdir(parents=True, exist_ok=True)
    if not STATE.exists():
        return {"index": 0, "seen": {}}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"index": 0, "seen": {}}

def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE)

def remember(topic, summary):
    compact = " ".join(summary.split())
    compact = compact[:900]
    subprocess.run(
        ["python3", "bin/nova_self.py", "learn",
         f"public_learning.{topic}", compact],
        cwd=ROOT, timeout=20, check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def main():
    state = load_state()
    idx = int(state.get("index", 0)) % len(SOURCES)
    topic, url = SOURCES[idx]
    try:
        raw, ctype = fetch(url)
        digest = hashlib.sha256(raw).hexdigest()
        text = extract_text(raw, ctype)
        if len(text) < 500:
            raise RuntimeError("source text too small")
        summary = summarize(topic, url, text)
        changed = state.get("seen", {}).get(topic) != digest
        if changed:
            remember(topic, summary)
        log({"event": "learned", "topic": topic, "url": url,
             "sha256": digest, "changed": changed,
             "summary": summary})
        state.setdefault("seen", {})[topic] = digest
        state["index"] = (idx + 1) % len(SOURCES)
        state["last_ok"] = now()
        save_state(state)
        print(json.dumps({"ok": True, "topic": topic,
                          "changed": changed}, ensure_ascii=False))
        return 0
    except Exception as exc:
        log({"event": "learning_error", "topic": topic, "url": url,
             "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
        state["index"] = (idx + 1) % len(SOURCES)
        state["last_error"] = now()
        save_state(state)
        print(json.dumps({"ok": False, "topic": topic,
                          "error": str(exc)[:300]}, ensure_ascii=False))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
