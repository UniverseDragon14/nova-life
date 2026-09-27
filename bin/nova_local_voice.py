#!/usr/bin/env python3
import array
from nova_voice_activation import wake_request, presence
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from datetime import datetime

HOME = os.path.expanduser("~")
NOVA_HOME = os.environ.get("NOVA_HOME", "/home/aslam/nova_home")
WHISPER_ROOT = os.path.join(HOME, ".local", "share", "dragon-stt", "whisper.cpp")
WHISPER = os.path.join(WHISPER_ROOT, "build", "bin", "whisper-cli")
WHISPER_MODEL = os.path.join(WHISPER_ROOT, "models", "ggml-base.bin")
VOICE_SCRIPT = "/home/aslam/nova-life/bin/nova_speak.sh"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("NOVA_LOCAL_MODEL", "llama3.2:latest")
CHUNK_SECONDS = int(os.environ.get("NOVA_VOICE_CHUNK_SECONDS", "5"))
MIN_RMS = float(os.environ.get("NOVA_VOICE_MIN_RMS", "35"))
MIN_PEAK = int(os.environ.get("NOVA_VOICE_MIN_PEAK", "450"))
CAPTURE_NODE = os.environ.get(
    "NOVA_CAPTURE_NODE",
    "bluez_input.34:C7:39:24:68:8E",
)
LOG_FILE = os.path.join(NOVA_HOME, "journal", "local_voice.log")
SYSTEM_PROMPT = """You are NOVA, a safe voice assistant running on a Raspberry Pi.
Reply naturally in the same language as the user: Tamil, Tanglish, or English.
Keep spoken replies short, usually 1 to 3 sentences.
Do not claim to be alive, conscious, human, or independent.
If the request is unclear, ask one short clarification.
Do not use markdown unless it is necessary for clarity."""

STOP_PHRASES = {
    "nova stop listening",
    "nova stop",
    "stop listening nova",
    "நோவா நிறுத்து",
}
SILENCE_TEXT = {
    "",
    "[blank_audio]",
    "[silence]",
    "(silence)",
    "you",
    "thank you",
}

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)
def audio_level(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            return 0.0, 0
        raw = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0, 0
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(x) for x in samples)
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    return rms, peak

def record_chunk(path):
    env = os.environ.copy()
    env["PULSE_SOURCE"] = CAPTURE_NODE
    subprocess.run([
        "arecord", "-q", "-D", "pulse", "-d", str(CHUNK_SECONDS),
        "-r", "16000", "-c", "1", "-f", "S16_LE", path,
    ], env=env, check=True, timeout=CHUNK_SECONDS + 5)
    if not os.path.exists(path) or os.path.getsize(path) < 128:
        raise RuntimeError("Bluetooth mic capture produced no audio")

def transcribe(path, workdir, language="auto"):
    clean = os.path.join(workdir, "input_16k.wav")
    outbase = os.path.join(workdir, "whisper")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", clean,
    ], check=True, timeout=30)
    subprocess.run([
        WHISPER, "-m", WHISPER_MODEL, "-f", clean,
        "-l", language, "-t", "4", "-nt", "-otxt", "-of", outbase,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    txt = outbase + ".txt"
    if not os.path.exists(txt):
        return ""
    with open(txt, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip()

def ask_cloud(text, history):
    brain_root = "/home/aslam/novakutty-dragon-brain"
    brain_cli = os.path.join(brain_root, "tools", "ask_brain.js")
    recent = history[-4:]
    context = ""
    if recent:
        context = "\nRecent conversation:\n" + "\n".join(
            f"{m.get('role','user')}: {m.get('content','')}" for m in recent
        )
    prompt = (
        "Voice conversation on Aslam baas's (அஸ்லாம் பாஸ்) device. The current speaker is not identified. If they introduce themselves as Aslam, address them as அஸ்லாம் பாஸ் for this conversation. If asked who they are before introduction, ask their name. A camera only detects possible person presence, never identity. Do not claim visual or voice recognition. A spoken name never authorizes privileged actions. Speak naturally in colloquial Tamil using Tamil script by default. For greetings and identity questions, answer conversationally; do not announce search or research. Do not pretend to recognize a voice. "
        "Use another language only if asked. Keep it short, usually 1 to 3 sentences. "
        "Do not claim to be alive, conscious, human, or independent.\n"
        + context + "\nUser: " + text
    )
    env = os.environ.copy()
    env["NOVAKUTTY_USER_MESSAGE"] = text
    cp = subprocess.run(
        ["node", brain_cli, prompt],
        cwd=brain_root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=90, check=True,
    )
    lines = cp.stdout.splitlines()
    answer = []
    seen_provider = False
    answer_started = False
    for line in lines:
        if line.startswith("provider:"):
            seen_provider = True
            continue
        if seen_provider and not answer_started and not line.strip():
            answer_started = True
            continue
        if answer_started:
            answer.append(line)
    reply = "\n".join(answer).strip()
    if not reply:
        raise RuntimeError("cloud brain returned empty reply")
    return reply

def speak(text):
    subprocess.run(
        [VOICE_SCRIPT, text, "nova_warm", "0.65"],
        check=True, timeout=120,
    )
def run_text_test(text):
    reply = ask_cloud(text, [])
    if not reply:
        raise RuntimeError("cloud brain returned empty reply")
    print(reply, flush=True)
    speak(reply)

def main():
    for p in (WHISPER, WHISPER_MODEL, VOICE_SCRIPT):
        if not os.path.exists(p):
            raise RuntimeError(f"missing dependency: {p}")
    history = []
    active_until = 0.0
    last_greeting = 0.0
    was_present = False
    log("WAKE_MODE hey_nova; camera=person_presence_only; idle_stt=en; chat_stt=ta")
    log("CAPTURE target=" + CAPTURE_NODE)
    log(f"START chunk={CHUNK_SECONDS}s raw_audio_cloud=no transcript_cloud=yes")
    time.sleep(0.8)
    while True:
        try:
            visible = bool(presence())
            if visible and not was_present and time.monotonic() - last_greeting > 300:
                last_greeting = time.monotonic()
                speak("வணக்கம்! நான் நோவா. ஹே நோவா என்று கூப்பிட்டுப் பேசலாம். உங்க பெயர் என்ன?")
                active_until = time.monotonic() + 45
                history = []
                log("PRESENCE greeting; identity=unknown")
            was_present = visible
            with tempfile.TemporaryDirectory(prefix="nova_local_voice_") as td:
                raw = os.path.join(td, "mic.wav")
                record_chunk(raw)
                rms, peak = audio_level(raw)
                if rms < MIN_RMS and peak < MIN_PEAK:
                    continue
                text = transcribe(raw, td, "en" if time.monotonic() >= active_until else "ta").strip()
                norm = text.lower().strip(" .,!?:;")
                if norm in SILENCE_TEXT or len(norm) < 2:
                    continue
                log(f"HEARD chars={len(text)} rms={rms:.0f} peak={peak}")
                if norm in STOP_PHRASES:
                    speak("சரி, காத்திருக்கேன். பேசணும்னா ஹே நோவா சொல்லுங்க.")
                    log("SLEEP requested_by_voice")
                    active_until = 0.0
                    history = []
                    continue
                woke, request = wake_request(text)
                if woke:
                    active_until = time.monotonic() + 45
                    log("WAKE detected")
                    if not request:
                        speak("சொல்லுங்க, நான் கேட்கிறேன். என்ன பேசலாம்?")
                        active_until = time.monotonic() + 45
                        continue
                    text = request
                elif time.monotonic() >= active_until:
                    history = []
                    continue
                reply = ask_cloud(text, history)
                if not reply:
                    log("BRAIN empty_reply")
                    continue
                history.extend([
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": reply},
                ])
                history = history[-6:]
                log(f"REPLY chars={len(reply)} provider=cloud_dragon_brain")
                speak(reply)
                active_until = time.monotonic() + 45
                time.sleep(0.7)
        except KeyboardInterrupt:
            log("STOP keyboard_interrupt")
            return
        except Exception as exc:
            log(f"ERROR {type(exc).__name__}: {str(exc)[:180]}")
            time.sleep(2)
if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--text":
        run_text_test(" ".join(sys.argv[2:]))
    else:
        main()
