import json
import os
import re
import time

STRICT_WAKE = re.compile(
    r"^(?:(?:hey|hi|hello|ஹேய்|ஹே|ஹாய்|ஏய்|ஹலோ)[\s,.!?…:;-]*)?"
    r"(?:nova|novaa|novaah|novah|nava|noba|lova|noah|no[ -]?va|நோவா|நோவ|நோவாஹ்)"
    r"(?=$|[\s,.!?…:;-])[, .!?…:;-]*",
    re.I,
)

GREETING = re.compile(r"^(?:hey|hi|hello|ஹேய்|ஹே|ஹாய்|ஏய்|ஹலோ)$", re.I)
GREETING_WAKE_ALIASES = {
    "nova", "novaa", "novaah", "novah", "nover",
    "nava", "noba", "lova", "lover", "lowa", "noah", "no",
    "நோவா", "நோவ", "நோவாஹ்",
}

def _tokens(text):
    return re.findall(r"[A-Za-z]+|[\u0B80-\u0BFF]+", text)

def _strip_repeated_wake(rest):
    while rest:
        m = STRICT_WAKE.match(rest)
        if not m:
            break
        rest = rest[m.end():].strip()
    return rest

def wake_request(text):
    original = text.strip()
    raw = original.lstrip('"“‘')

    m = STRICT_WAKE.match(raw)
    if m:
        return True, _strip_repeated_wake(raw[m.end():].strip())

    toks = _tokens(raw)

    # On this Pi5/Bluetooth mic, the real spoken wake phrase "Hey Nova"
    # has been observed as "Oh, no, ma." by whisper.cpp. Accept that
    # exact three-token acoustic error, including repeated wake calls.
    lowered = [t.lower() for t in toks]
    if lowered[:3] == ["oh", "no", "ma"]:
        consumed = 3
        while lowered[consumed:consumed + 3] == ["oh", "no", "ma"]:
            consumed += 3
        return True, " ".join(toks[consumed:]).strip()

    # Whisper sometimes turns "Hey Nova" into "Hey Lova/Lover/Noah/No".
    # Only permit these looser aliases after an explicit greeting to avoid
    # random background words waking the assistant.
    if len(toks) >= 2 and GREETING.match(toks[0]):
        alias = toks[1].lower()
        consumed = 2
        if alias == "no" and len(toks) >= 3 and toks[2].lower() == "va":
            alias = "nova"
            consumed = 3
        if alias in GREETING_WAKE_ALIASES:
            return True, " ".join(toks[consumed:]).strip()

    return False, original

_last_visual_event = None

def presence():
    """Consume each stable appearance/wave once; never starve audio capture."""
    global _last_visual_event
    try:
        with open(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000") + "/nova_presence.json") as f:
            p = json.load(f)
        fresh = 0 <= time.time() - p.get("at", 0) < 10
        if not fresh or not p.get("camera_ok") or not p.get("present"):
            return False
        event = (p.get("session"), p.get("entry_seq", 0), p.get("wave_seq", 0))
        if event == _last_visual_event:
            return False
        _last_visual_event = event
        return True
    except (OSError, ValueError, TypeError):
        return False

def presence_level():
    try:
        p = json.load(open(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000") + "/nova_presence.json"))
        return p.get("camera_ok") and p.get("present") and time.time() - p.get("at", 0) < 10
    except (OSError, ValueError, TypeError):
        return False
