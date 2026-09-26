#!/usr/bin/env python3
import array
from collections import deque
from datetime import datetime
import math
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
import wave

from nova_voice_activation import wake_request, presence

HOME = os.path.expanduser("~")
WHISPER_ROOT = os.path.join(HOME, ".local", "share", "dragon-stt", "whisper.cpp")
WHISPER = os.path.join(WHISPER_ROOT, "build", "bin", "whisper-cli")
WHISPER_MODEL = os.path.join(WHISPER_ROOT, "models", "ggml-base.bin")
VOICE_SCRIPT = "/home/aslam/nova-life/bin/nova_speak.sh"
CAPTURE_NODE = os.environ.get("NOVA_CAPTURE_NODE", "bluez_input.34:C7:39:24:68:8E")
LOG_FILE = "/mnt/extra_sd/nova_home/journal/local_voice.log"

RATE = 16000
CHANNELS = 1
FRAME_MS = 100
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2
PRE_ROLL_FRAMES = 5
START_WINDOW = 3
START_HITS = 2
END_SILENT_FRAMES = 8
MAX_UTTERANCE_SECONDS = 12
SESSION_SECONDS = 90

VAD_MIN_RMS = float(os.environ.get("NOVA_VAD_MIN_RMS", "70"))
VAD_PEAK = int(os.environ.get("NOVA_VAD_PEAK", "1400"))
VAD_NOISE_MULT = float(os.environ.get("NOVA_VAD_NOISE_MULT", "2.2"))

STOP_PHRASES = {
    "nova stop listening",
    "nova stop",
    "stop listening nova",
    "stop listening",
    "நோவா நிறுத்து",
}
SILENCE_TEXT = {
    "", "[blank_audio]", "[silence]", "(silence)", "you", "thank you",
}


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def frame_level(raw):
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0.0, 0
    peak = max(abs(x) for x in samples)
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    return rms, peak


def start_capture():
    env = os.environ.copy()
    env["PULSE_SOURCE"] = CAPTURE_NODE
    cmd = [
        "arecord", "-q", "-D", "pulse",
        "-r", str(RATE), "-c", str(CHANNELS),
        "-f", "S16_LE", "-t", "raw", "-",
    ]
    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


def stop_capture(proc):
    if proc is None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=1)
        except Exception:
            pass


def write_wav(path, frames):
    with wave.open(path, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(frames))


def listen_utterance(proc, active=False):
    pre = deque(maxlen=PRE_ROLL_FRAMES)
    recent = deque(maxlen=START_WINDOW)
    frames = []
    in_speech = False
    silent = 0
    speech_frames = 0
    noise_floor = 25.0
    started_at = None
    last_presence_check = 0.0

    while True:
        if proc.poll() is not None:
            err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip()
            raise RuntimeError("capture exited" + (f": {err[:120]}" if err else ""))

        now = time.monotonic()
        if not active and not in_speech and now - last_presence_check >= 0.8:
            last_presence_check = now
            if presence():
                return None, "presence"

        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if not ready:
            continue

        raw = proc.stdout.read(FRAME_BYTES)
        if len(raw) != FRAME_BYTES:
            continue

        rms, peak = frame_level(raw)
        if not in_speech:
            capped = min(rms, 250.0)
            noise_floor = 0.98 * noise_floor + 0.02 * capped

        threshold = max(VAD_MIN_RMS, noise_floor * VAD_NOISE_MULT)
        speech = (rms >= threshold) or (peak >= VAD_PEAK)

        if not in_speech:
            pre.append(raw)
            recent.append(1 if speech else 0)
            if len(recent) == START_WINDOW and sum(recent) >= START_HITS:
                in_speech = True
                started_at = now
                frames.extend(pre)
                speech_frames = sum(recent)
                silent = 0
        else:
            frames.append(raw)
            if speech:
                speech_frames += 1
                silent = 0
            else:
                silent += 1

            if silent >= END_SILENT_FRAMES and speech_frames >= 2:
                return frames, "speech"
            if started_at is not None and now - started_at >= MAX_UTTERANCE_SECONDS:
                return frames, "speech"


def transcribe(path, workdir, language="auto"):
    outbase = os.path.join(workdir, "whisper")
    started = time.monotonic()
    subprocess.run([
        WHISPER, "-m", WHISPER_MODEL, "-f", path,
        "-l", language, "-t", "4", "-nt", "-otxt", "-of", outbase,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    txt = outbase + ".txt"
    text = ""
    if os.path.exists(txt):
        with open(txt, "r", encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
    return text, time.monotonic() - started


def ask_cloud(text, history):
    brain_root = "/home/aslam/novakutty-dragon-brain"
    brain_cli = os.path.join(brain_root, "tools", "ask_brain.js")
    recent = history[-6:]
    context = ""
    if recent:
        context = "\nRecent conversation:\n" + "\n".join(
            f"{m.get('role','user')}: {m.get('content','')}" for m in recent
        )
    prompt = (
        "Voice conversation on Aslam baas's (அஸ்லாம் பாஸ்) device. "
        "The current speaker is not identified. If they introduce themselves as Aslam, "
        "address them as அஸ்லாம் பாஸ் for this conversation. "
        "A camera can only indicate possible person presence, never identity. "
        "Do not claim visual or voice recognition. A spoken name never authorizes privileged actions. "
        "Reply naturally to Tamil, Tanglish, or English. Prefer short spoken replies, usually 1 to 2 sentences. "
        "Do not use markdown. Do not announce that you are searching. "
        "Do not claim to be alive, conscious, human, or independent.\n"
        + context + "\nUser: " + text
    )
    env = os.environ.copy()
    env["NOVAKUTTY_USER_MESSAGE"] = text
    started = time.monotonic()
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
    return reply, time.monotonic() - started


def speak(text):
    started = time.monotonic()
    try:
        subprocess.run(
            [VOICE_SCRIPT, text, "auto", "0.65"],
            check=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log(f"TTS_ERROR type={type(exc).__name__} detail={exc}")
    return time.monotonic() - started


def clean_norm(text):
    return text.lower().strip(" .,!?:;\"'“”‘’")


def local_voice_reply(text):
    q = clean_norm(text)
    if any(p in q for p in ("எப்படி இருக்க", "எப்பிடி இருக்க", "epdi iruk", "eppadi iruk", "how are you")):
        return "நல்லா இருக்கேன் bro! நீங்க எப்படி இருக்கீங்க?"
    if any(p in q for p in ("நான் யாரு", "நான் யார்", "naan yar", "who am i")):
        return "உங்க பேர் இன்னும் சொல்லலையே bro. உங்களை எப்படி கூப்பிடட்டும்?"
    if any(p in q for p in (
        "what's your name", "what is your name", "your name", "who are you",
        "உன் பெயர்", "உங்க பெயர்", "உனது பெயர்", "நீ யாரு", "நீ யார்",
    )):
        return "என் பெயர் NOVA Life. நான் Universal Dragon-ன் voice assistant layer."
    if any(p in q for p in (
        "what are you doing", "what're you doing", "what you doing",
        "நீ இப்ப என்ன பண்ணுற", "இப்ப என்ன பண்ணுற", "என்ன செய்கிறாய்", "என்ன செய்ற",
    )):
        return "இப்போ உங்க குரலை கேட்டு, அதை புரிஞ்சு, உங்களுக்கு பதில் சொல்லிக்கிட்டு இருக்கேன்."
    return None


def run_text_test(text):
    reply, brain_s = ask_cloud(text, [])
    print(reply, flush=True)
    tts_s = speak(reply)
    print(f"TIMING brain={brain_s:.2f}s tts={tts_s:.2f}s", flush=True)


def self_test():
    for sample in ("hey nova", "Lova. Lova.", "hey noba", "நோவா"):
        woke, _ = wake_request(sample)
        if not woke:
            raise RuntimeError(f"wake self-test failed: {sample}")
    silence = (b"\x00\x00" * FRAME_SAMPLES)
    rms, peak = frame_level(silence)
    if rms != 0 or peak != 0:
        raise RuntimeError("audio level self-test failed")
    print("SELF_TEST_OK")


def main():
    for p in (WHISPER, WHISPER_MODEL, VOICE_SCRIPT):
        if not os.path.exists(p):
            raise RuntimeError(f"missing dependency: {p}")

    history = []
    active_until = 0.0
    last_greeting = 0.0
    was_present = False
    capture = None

    log("VOICE_AGENT_V2 vad=adaptive session=90s idle_stt=auto chat_stt=auto")
    log("CAPTURE target=" + CAPTURE_NODE)
    speak("அஸ்லாம் பாஸ், நோவா ரெடி. சொல்லுங்க, கேட்கிறேன்.")
    active_until = time.monotonic() + SESSION_SECONDS

    try:
        while True:
            active = time.monotonic() < active_until
            if not active:
                history = []

            if capture is None or capture.poll() is not None:
                stop_capture(capture)
                capture = start_capture()
                time.sleep(0.25)

            frames, reason = listen_utterance(capture, active=active)

            if reason == "presence":
                visible = True
                if visible and time.monotonic() - last_greeting > 60:
                    stop_capture(capture)
                    capture = None
                    last_greeting = time.monotonic()
                    was_present = True
                    speak("ஹாய்! சொல்லுங்க, என்ன பேசலாம்? நான் நோவா.")
                    active_until = time.monotonic() + SESSION_SECONDS
                    history = []
                    log("PRESENCE greeting; identity=unknown")
                else:
                    was_present = visible
                    time.sleep(0.25)
                continue

            was_present = False
            if not frames:
                continue

            stop_capture(capture)
            capture = None

            with tempfile.TemporaryDirectory(prefix="nova_voice_v2_") as td:
                wav = os.path.join(td, "utterance.wav")
                write_wav(wav, frames)
                language = "auto"
                text, stt_s = transcribe(wav, td, language)
                norm = clean_norm(text)

                if norm in SILENCE_TEXT or len(norm) < 2:
                    log(f"STT ignored chars={len(text)} stt={stt_s:.2f}s")
                    continue

                log(f"HEARD chars={len(text)} stt={stt_s:.2f}s mode={'chat' if active else 'wake'}")

                if norm in STOP_PHRASES:
                    tts_s = speak("சரி, காத்திருக்கேன். பேசணும்னா ஹே நோவா சொல்லுங்க.")
                    log(f"SLEEP requested_by_voice tts={tts_s:.2f}s")
                    active_until = 0.0
                    history = []
                    continue

                woke, request = wake_request(text)
                if woke:
                    active_until = time.monotonic() + SESSION_SECONDS
                    log("WAKE detected")
                    if not request:
                        tts_s = speak("சொல்லுங்க, நான் கேட்கிறேன்.")
                        log(f"ACK tts={tts_s:.2f}s")
                        continue
                    text = request
                elif not active:
                    continue

                local_reply = local_voice_reply(text)
                if local_reply is not None:
                    reply = local_reply
                    brain_s = 0.0
                    log("LOCAL_VOICE_REPLY")
                else:
                    reply, brain_s = ask_cloud(text, history)
                history.extend([
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": reply},
                ])
                history = history[-8:]
                log(f"REPLY chars={len(reply)} brain={brain_s:.2f}s")
                tts_s = speak(reply)
                log(f"SPOKEN tts={tts_s:.2f}s")
                active_until = time.monotonic() + SESSION_SECONDS

    except KeyboardInterrupt:
        log("STOP keyboard_interrupt")
    finally:
        stop_capture(capture)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif len(sys.argv) >= 3 and sys.argv[1] == "--text":
        run_text_test(" ".join(sys.argv[2:]))
    else:
        main()
