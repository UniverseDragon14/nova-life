#!/usr/bin/env python3
"""Local visual cues, not identity, emotion, gaze intent or mind reading."""
import collections
import json
import os
from pathlib import Path
import sys
import time
import uuid
import cv2
import numpy as np

ASSETS = Path(__file__).resolve().parent.parent / "vision"
sys.path.insert(0, str(ASSETS))
from mp_palmdet import MPPalmDet
from mp_handpose import MPHandPose
STATE = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")) / "nova_presence.json"
DEVICE = os.environ.get("NOVA_CAMERA_DEVICE", "/dev/video0")

def publish(data):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.chmod(0o600)
    tmp.replace(STATE)

def wave_detected(points):
    if len(points) < 6 or points[-1][0] - points[0][0] < 1:
        return False
    xs = [p[1] for p in points]
    if max(xs) - min(xs) < 0.15:
        return False
    directions = []
    anchor = xs[0]
    for x in xs[1:]:
        if abs(x - anchor) >= 0.045:
            directions.append(1 if x > anchor else -1)
            anchor = x
    return sum(a != b for a, b in zip(directions, directions[1:])) >= 2

def main(once=False):
    cv2.setNumThreads(1)
    face = cv2.CascadeClassifier(str(ASSETS / "face.xml"))
    eyes = cv2.CascadeClassifier(str(ASSETS / "eyes.xml"))
    if face.empty() or eyes.empty():
        raise RuntimeError("missing face/eye detector assets")
    palm = MPPalmDet(str(ASSETS / "palm.onnx"), scoreThreshold=0.8)
    hand = MPHandPose(str(ASSETS / "hand.onnx"), confThreshold=0.85)
    session = uuid.uuid4().hex
    entry_seq = wave_seq = hits = 0
    present = False
    last_seen = last_wave = 0.0
    wrists = collections.deque()
    cap = None
    try:
        while True:
            tick = time.monotonic()
            if cap is None:
                cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read()
            data = dict(at=time.time(), camera_ok=bool(ok), present=False,
                        identity=None, session=session, entry_seq=entry_seq,
                        wave_seq=wave_seq, detections=0, hands=[], eyes=[],
                        limitation="eye locations only; no identity, gaze intent or thoughts")
            if not ok:
                publish(data)
                cap.release()
                cap = None
                present = False
                hits = 0
                wrists.clear()
                if once:
                    raise RuntimeError("camera frame unavailable")
                time.sleep(3)
                continue
            frame = cv2.resize(frame, (640, 480))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face.detectMultiScale(gray, 1.15, 5, minSize=(45, 45))
            for x, y, w, h in faces:
                found = eyes.detectMultiScale(gray[y:y+h//2, x:x+w], 1.1, 4)
                for ex, ey, ew, eh in found[:2]:
                    data["eyes"].append([round((x+ex+ew/2)/640, 3),
                                         round((y+ey+eh/2)/480, 3)])
            palms = palm.infer(frame)
            for candidate in sorted(palms, key=lambda p: float(p[-1]), reverse=True)[:1]:
                pose = hand.infer(frame, candidate)
                if pose is None:
                    continue
                lm = pose[4:67].reshape(21, 3)
                coords = [[round(float(p[0])/640, 3), round(float(p[1])/480, 3)] for p in lm]
                # Deliberately no gesture-to-approval mapping.
                data["hands"].append(dict(landmarks=coords, score=round(float(pose[-1]), 3)))
                wrists.append((tick, coords[0][0]))
            if not data["hands"]:
                wrists.clear()
            while wrists and tick - wrists[0][0] > 3:
                wrists.popleft()
            if wave_detected(wrists) and tick - last_wave > 15:
                wave_seq += 1
                last_wave = tick
                wrists.clear()
            seen = bool(len(faces) or data["hands"])
            hits = hits + 1 if seen else 0
            if seen:
                last_seen = tick
            if not present and hits >= 3:
                present = True
                entry_seq += 1
            if tick - last_seen > 5:
                present = False
            data.update(present=present, detections=len(faces),
                        entry_seq=entry_seq, wave_seq=wave_seq)
            publish(data)
            if once:
                print(json.dumps(dict(camera_ok=True, frame_shape=list(frame.shape),
                                      faces=len(faces), hands=len(data["hands"]),
                                      eyes=len(data["eyes"]), models_ok=True)))
                return
            time.sleep(max(0, 0.25 - (time.monotonic() - tick)))
    finally:
        if cap is not None:
            cap.release()
        publish(dict(at=time.time(), camera_ok=False, present=False, identity=None))

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert not wave_detected([(i/4, 0.5) for i in range(8)])
        assert wave_detected([(i/4, x) for i, x in enumerate([.2,.3,.5,.6,.4,.2,.4,.6])])
        print("VISION_SELF_TEST_OK")
    else:
        main("--once" in sys.argv)
