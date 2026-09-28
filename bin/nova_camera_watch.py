#!/usr/bin/env python3
"""Event-driven NOVA camera availability watcher.

Tracks one stable camera identity. It never identifies people, restarts services,
changes hardware, or treats a missing device node as proof of a physical cause.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import sys
import time
from typing import Callable, Optional

DEFAULT_STATE = Path.home() / ".local/state/nova/camera_state.json"
DEBOUNCE_SECONDS = 5.0
FLAP_WINDOW_SECONDS = 10 * 60.0
FLAP_TRANSITION_LIMIT = 3


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def default_state(device_key: str) -> dict:
    return {
        "device_key": device_key,
        "state": "UNKNOWN",
        "generation": 0,
        "last_verified_at": None,
        "last_notified_generation": 0,
        "evidence": [],
        "pending_notification": None,
        "transition_times": [],
        "unstable_until": None,
    }


def load_state(path: Path, device_key: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "device_key", "state", "generation", "last_verified_at",
            "last_notified_generation", "evidence",
        }
        if not required.issubset(data):
            raise ValueError("missing fields")
        if data["device_key"] != device_key:
            return default_state(device_key)
        if data["state"] not in {"UNKNOWN", "PRESENT", "LOST"}:
            raise ValueError("bad state")
        return data
    except Exception:
        return default_state(device_key)


def atomic_save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(path.name + ".tmp")
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def notification_for(old: str, new: str, generation: int, *, unstable: bool = False) -> dict:
    if unstable:
        text = "Camera unstable: more than 3 availability transitions in 10 minutes. No action taken."
    elif old == "PRESENT" and new == "LOST":
        text = "Camera not detected (USB device gone). Likely unplugged or cable loose. No action taken."
    elif old == "LOST" and new == "PRESENT":
        text = "Camera detected again. Vision availability recovered. No action taken."
    else:
        text = f"Camera state changed: {old} -> {new}. No action taken."
    return {
        "generation": generation,
        "previous_state": old,
        "new_state": new,
        "text": text,
    }
class CameraStateMachine:
    def __init__(
        self,
        state_path: Path,
        device_key: str,
        exists: Callable[[], bool],
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], str] = now_iso,
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        self.state_path = state_path
        self.device_key = device_key
        self.exists = exists
        self.clock = clock
        self.wall_clock = wall_clock
        self.debounce = debounce
        self.data = load_state(state_path, device_key)
        self.absent_since: Optional[float] = None
        self.boot_observed = False
        self.startup_candidate: Optional[tuple[str, float]] = None

    def _evidence(self, present: bool, source: str) -> list[dict]:
        return [{
            "source": source,
            "device_key": self.device_key,
            "present": present,
            "at": self.wall_clock(),
        }]

    def _persist_observation(self, present: bool, source: str) -> None:
        self.data["last_verified_at"] = self.wall_clock()
        self.data["evidence"] = self._evidence(present, source)
        atomic_save(self.state_path, self.data)

    def _flap_action(self, now: float) -> str:
        raw = self.data.get("transition_times") or []
        times = []
        for value in raw:
            try:
                t = float(value)
            except (TypeError, ValueError):
                continue
            if 0.0 <= t <= now and now - t <= FLAP_WINDOW_SECONDS:
                times.append(t)
        times.append(now)
        self.data["transition_times"] = times

        unstable_until = self.data.get("unstable_until")
        try:
            unstable_until = float(unstable_until) if unstable_until is not None else None
        except (TypeError, ValueError):
            unstable_until = None

        if unstable_until is not None and 0.0 <= now <= unstable_until:
            self.data["unstable_until"] = now + FLAP_WINDOW_SECONDS
            return "suppress"

        if len(times) > FLAP_TRANSITION_LIMIT:
            self.data["unstable_until"] = now + FLAP_WINDOW_SECONDS
            return "summary"

        self.data["unstable_until"] = None
        return "normal"

    def _transition(self, new_state: str, source: str) -> Optional[dict]:
        old = self.data["state"]
        if old == new_state:
            self._persist_observation(new_state == "PRESENT", source)
            return None
        self.data["state"] = new_state
        self.data["generation"] = int(self.data.get("generation", 0)) + 1
        self.data["last_verified_at"] = self.wall_clock()
        self.data["evidence"] = self._evidence(new_state == "PRESENT", source)

        flap_action = self._flap_action(self.clock())
        if flap_action == "suppress":
            atomic_save(self.state_path, self.data)
            return None

        intent = notification_for(
            old,
            new_state,
            self.data["generation"],
            unstable=(flap_action == "summary"),
        )
        self.data["pending_notification"] = intent
        atomic_save(self.state_path, self.data)
        return intent

    def observe(self, present: bool, source: str = "event") -> Optional[dict]:
        now = self.clock()
        current = self.data["state"]

        if not self.boot_observed:
            self.boot_observed = True
            observed = "PRESENT" if present else "LOST"
            if current == "UNKNOWN":
                self.data["state"] = observed
                self.data["last_verified_at"] = self.wall_clock()
                self.data["evidence"] = self._evidence(present, "startup")
                self.data["pending_notification"] = None
                atomic_save(self.state_path, self.data)
                return None
            if current != observed:
                self.startup_candidate = (observed, now)
                self._persist_observation(present, "startup:debounce")
                return None

        if self.startup_candidate is not None:
            target, started = self.startup_candidate
            observed = "PRESENT" if present else "LOST"
            if observed != target:
                self.startup_candidate = None
                self._persist_observation(present, "startup:debounce_cancelled")
                return None
            if now - started < self.debounce:
                self._persist_observation(present, "startup:debounce")
                return None
            self.startup_candidate = None
            return self._transition(target, "startup:confirmed_after_debounce")

        current = self.data["state"]
        if present:
            self.absent_since = None
            if current == "LOST":
                return self._transition("PRESENT", source)
            self._persist_observation(True, source)
            return None

        if current == "LOST":
            self._persist_observation(False, source)
            return None

        if self.absent_since is None:
            self.absent_since = now
            self._persist_observation(False, source + ":debounce")
            return None

        if now - self.absent_since < self.debounce:
            self._persist_observation(False, source + ":debounce")
            return None

        if self.exists():
            self.absent_since = None
            self._persist_observation(True, source + ":recovered_during_debounce")
            return None

        self.absent_since = None
        return self._transition("LOST", source + ":confirmed_absent")

    def acknowledge(self, generation: int) -> bool:
        pending = self.data.get("pending_notification")
        if not pending or int(pending.get("generation", -1)) != generation:
            return False
        self.data["last_notified_generation"] = generation
        self.data["pending_notification"] = None
        atomic_save(self.state_path, self.data)
        return True
def stable_device_key(device: Path) -> str:
    text = str(device)
    if "/dev/v4l/by-id/" in text or "/dev/v4l/by-path/" in text:
        return text
    raise ValueError("camera identity must use /dev/v4l/by-id or /dev/v4l/by-path")


def resolve_device(configured: Optional[str], state_path: Path) -> Path:
    if configured:
        device = Path(configured)
        stable_device_key(device)
        return device

    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        saved_key = saved.get("device_key")
        if isinstance(saved_key, str) and saved_key:
            device = Path(saved_key)
            stable_device_key(device)
            return device
    except Exception:
        pass

    candidates = sorted(Path("/dev/v4l/by-id").glob("*-video-index0"))
    if not candidates:
        candidates = sorted(Path("/dev/v4l/by-path").glob("*-video-index0"))
    if len(candidates) != 1:
        raise ValueError("camera discovery requires exactly one stable by-id/by-path video-index0 device")
    stable_device_key(candidates[0])
    return candidates[0]


def run_monitor(device: Path, state_path: Path, debounce: float) -> int:
    try:
        import pyudev
    except ImportError:
        print("CAMERA_WATCH_ERROR pyudev unavailable", file=sys.stderr)
        return 2

    key = stable_device_key(device)
    machine = CameraStateMachine(state_path, key, device.exists, debounce=debounce)

    initial = device.exists()
    machine.observe(initial, "startup")

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="video4linux")
    monitor.start()

    print(f"CAMERA_WATCH_READY device_key={key} state={machine.data['state']}", flush=True)

    while True:
        readable, _, _ = select.select([monitor.fileno()], [], [], 1.0)
        if readable:
            dev = monitor.poll(timeout=0)
            action = getattr(dev, "action", None) if dev is not None else None
            intent = machine.observe(device.exists(), f"udev:{action or 'change'}")
            if intent:
                print("CAMERA_NOTIFY_INTENT " + json.dumps(intent, ensure_ascii=False), flush=True)

        if machine.absent_since is not None:
            intent = machine.observe(device.exists(), "debounce_timer")
            if intent:
                print("CAMERA_NOTIFY_INTENT " + json.dumps(intent, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=os.environ.get("NOVA_CAMERA_STABLE_DEVICE"))
    parser.add_argument("--state", default=os.environ.get("NOVA_CAMERA_WATCH_STATE", str(DEFAULT_STATE)))
    parser.add_argument("--debounce", type=float, default=DEBOUNCE_SECONDS)
    parser.add_argument("--ack-generation", type=int)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    state_path = Path(args.state)
    try:
        device = resolve_device(args.device, state_path)
        key = stable_device_key(device)
    except ValueError as exc:
        print(f"CAMERA_WATCH_ERROR {exc}", file=sys.stderr)
        return 2

    if args.ack_generation is not None:
        machine = CameraStateMachine(state_path, key, device.exists, debounce=args.debounce)
        if machine.acknowledge(args.ack_generation):
            print(f"CAMERA_NOTIFICATION_ACK generation={args.ack_generation}")
            return 0
        print("CAMERA_NOTIFICATION_ACK_REJECTED", file=sys.stderr)
        return 1

    if args.once:
        machine = CameraStateMachine(state_path, key, device.exists, debounce=args.debounce)
        machine.observe(device.exists(), "once")
        print(json.dumps(machine.data, ensure_ascii=False, sort_keys=True))
        return 0

    return run_monitor(device, state_path, args.debounce)


if __name__ == "__main__":
    raise SystemExit(main())
