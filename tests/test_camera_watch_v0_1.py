#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "bin/nova_camera_watch.py"
spec = importlib.util.spec_from_file_location("nova_camera_watch", MODULE_PATH)
cw = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(cw)

DEVICE = "/dev/v4l/by-id/camera-fixture-video-index0"


class Clock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class CameraWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "camera_state.json"
        self.clock = Clock()
        self.present = False

    def tearDown(self):
        self.tmp.cleanup()

    def machine(self):
        return cw.CameraStateMachine(
            self.state, DEVICE, lambda: self.present,
            clock=self.clock, wall_clock=lambda: f"T{self.clock.value:.1f}",
            debounce=5.0,
        )

    def test_add(self):
        m = self.machine()
        self.present = False
        self.assertIsNone(m.observe(False, "startup"))
        self.assertEqual(m.data["state"], "LOST")
        self.present = True
        intent = m.observe(True, "udev:add")
        self.assertEqual(intent["new_state"], "PRESENT")
        self.assertEqual(m.data["generation"], 1)

    def test_remove_confirmed_lost(self):
        m = self.machine()
        self.present = True
        self.assertIsNone(m.observe(True, "startup"))
        self.present = False
        self.clock.advance(1)
        self.assertIsNone(m.observe(False, "udev:remove"))
        self.clock.advance(5)
        intent = m.observe(False, "debounce_timer")
        self.assertEqual(intent["new_state"], "LOST")
        self.assertEqual(m.data["generation"], 1)

    def test_flap_remove_add_inside_debounce_no_lost(self):
        m = self.machine()
        self.present = True
        m.observe(True, "startup")
        self.present = False
        self.clock.advance(1)
        self.assertIsNone(m.observe(False, "udev:remove"))
        self.present = True
        self.clock.advance(2)
        self.assertIsNone(m.observe(True, "udev:add"))
        self.assertEqual(m.data["state"], "PRESENT")
        self.assertEqual(m.data["generation"], 0)
        self.assertIsNone(m.data.get("pending_notification"))

    def test_restart_while_lost_no_duplicate(self):
        data = cw.default_state(DEVICE)
        data.update(state="LOST", generation=3, last_notified_generation=3)
        cw.atomic_save(self.state, data)
        self.present = False
        m = self.machine()
        self.assertIsNone(m.observe(False, "startup"))
        self.clock.advance(6)
        self.assertIsNone(m.observe(False, "timer"))
        self.assertEqual(m.data["generation"], 3)
        self.assertIsNone(m.data.get("pending_notification"))

    def test_lost_to_present_one_recovery_after_startup_debounce(self):
        data = cw.default_state(DEVICE)
        data.update(state="LOST", generation=4, last_notified_generation=4)
        cw.atomic_save(self.state, data)
        self.present = True
        m = self.machine()
        self.assertIsNone(m.observe(True, "startup"))
        self.clock.advance(4)
        self.assertIsNone(m.observe(True, "timer"))
        self.clock.advance(1)
        intent = m.observe(True, "timer")
        self.assertEqual(intent["new_state"], "PRESENT")
        self.assertEqual(intent["generation"], 5)
        self.assertIsNone(m.observe(True, "same-state"))
        self.assertEqual(m.data["generation"], 5)

    def test_same_state_transition_is_deduplicated(self):
        m = self.machine()
        self.present = False
        m.observe(False, "startup")
        self.assertIsNone(m._transition("LOST", "duplicate"))
        self.assertEqual(m.data["generation"], 0)


    def test_flap_guard_emits_one_summary_then_quiet(self):
        m = self.machine()
        self.present = True
        m.observe(True, "startup")

        self.present = False
        self.clock.advance(1)
        self.assertIsNone(m.observe(False, "udev:remove"))
        self.clock.advance(5)
        self.assertEqual(m.observe(False, "debounce_timer")["new_state"], "LOST")

        self.present = True
        self.clock.advance(1)
        self.assertEqual(m.observe(True, "udev:add")["new_state"], "PRESENT")

        self.present = False
        self.clock.advance(1)
        self.assertIsNone(m.observe(False, "udev:remove"))
        self.clock.advance(5)
        self.assertEqual(m.observe(False, "debounce_timer")["new_state"], "LOST")

        self.present = True
        self.clock.advance(1)
        summary = m.observe(True, "udev:add")
        self.assertEqual(
            summary["text"],
            "Camera unstable: more than 3 availability transitions in 10 minutes. No action taken.",
        )

        self.present = False
        self.clock.advance(1)
        self.assertIsNone(m.observe(False, "udev:remove"))
        self.clock.advance(5)
        self.assertIsNone(m.observe(False, "debounce_timer"))
        self.assertEqual(m.data["state"], "LOST")

    def test_resolve_device_uses_persisted_stable_key_when_camera_absent(self):
        data = cw.default_state(DEVICE)
        data.update(state="LOST", generation=2, last_notified_generation=2)
        cw.atomic_save(self.state, data)
        self.assertEqual(cw.resolve_device(None, self.state), Path(DEVICE))

    def test_atomic_state_mode_0600_and_required_fields(self):
        m = self.machine()
        self.present = True
        m.observe(True, "startup")
        self.assertEqual(os.stat(self.state).st_mode & 0o777, 0o600)
        data = json.loads(self.state.read_text())
        for key in (
            "device_key", "state", "generation", "last_verified_at",
            "last_notified_generation", "evidence",
        ):
            self.assertIn(key, data)

    def test_reject_unstable_video_number_identity(self):
        with self.assertRaises(ValueError):
            cw.stable_device_key(Path("/dev/video0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
