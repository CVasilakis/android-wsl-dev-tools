"""The scripts against the real SDK and emulator: slow (boots), so only with run.py --emulator.

Uses the developer's own setup (SDK, AVD) as the scripts find it; AWDT_AVD picks the AVD. If that
AVD is already running it's reused and left running; otherwise it's booted without a window, with
--wait-for-home so the tests start on a device that has settled, with the emulator flags in
AWDT_TEST_EMULATOR_FLAGS if any, and stopped afterwards (without saving a snapshot, so the next
normal start is unaffected). The tests that need the AVD to themselves, to stop it or to show its
window on a private X server, skip if it was already running.

What reaches an app is seen through TouchProbe.apk (probe/), installed for the tests and removed
after them.
"""
import getpass
import os
import re
import shlex
import signal
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from support import x11

TESTS = Path(__file__).resolve().parents[1]
TOOLS = TESTS.parent
BIN = TOOLS / "bin"
LIB = TOOLS / "lib"
PROBE = Path(__file__).resolve().parent / "TouchProbe.apk"
PROBE_ACTIVITY = "awdt.probe/.ProbeActivity"

ENABLED = os.environ.get("AWDT_EMULATOR_TESTS") == "1"

# How long a test waits for something on the device, in seconds. The waits end as soon as it's
# there, so these limits only decide how long a failure takes, and must hold for an emulator
# starved of CPU.
EVENT_TIMEOUT = 60   # from a gesture's end until the app has logged it
FOCUS_TIMEOUT = 60   # for an app's activity to come to the front
TOUCH_LIMIT = 120    # for touch.sh or ui.sh to return: the limit of their adb calls, and more

# Python's limits for the scripts, from the scripts' own: when Python stops a script on the way,
# its emulator can be left running (start-emulator.sh starts it with nohup), so a script must
# always reach its own limits first, and clean up and say why. Each adb call they make gets
# ADB_CALL s (adb_bounded in device.sh: ADB_TIMEOUT s, then SIGKILL ADB_KILL_AFTER s later), and each
# of their limits lasts up to 1 s longer (time_is_up in device.sh). ADB_CALLS is more than either
# script makes on the way with up to three emulators running. The scripts' values are copied here;
# hermetic/test_conventions.py checks that the copies match.
ADB_TIMEOUT = 15
ADB_KILL_AFTER = 5
ADB_CALL = ADB_TIMEOUT + ADB_KILL_AFTER
ADB_CALLS = 10
TERM_WAIT = 30   # start-emulator.sh's, for an emulator it stops to exit after SIGTERM
KILL_WAIT = 30   # stop-emulator.sh's, for a killed emulator to exit, and again for adb to unlist it
STOP_SAVE_WAIT = 12  # stop-emulator.sh's SAVE_WAIT, from API 33 on, for Android to save app states
BOOT_TIMEOUT = int(os.environ.get("AWDT_BOOT_TIMEOUT") or 900)   # passed on to start-emulator.sh
HOME_TIMEOUT = int(os.environ.get("AWDT_HOME_TIMEOUT") or 600)   # and to its --wait-for-home
STOP_TIMEOUT = int(os.environ.get("AWDT_STOP_TIMEOUT") or 60)    # passed on to stop-emulator.sh
# home.sh's wait_for_home: its limit, then its pause between two looks and a last look of up to
# five adb calls (the API level, what HOME resolves to, two dumps, a Back).
HOME_LIMIT = HOME_TIMEOUT + 1 + 1 + 5 * ADB_CALL if HOME_TIMEOUT else None
# start-emulator.sh: the boot limit; with --wait-for-home, that wait; then stopping an emulator that
# didn't boot or settle (SIGTERM, TERM_WAIT s, then SIGKILL). No limit when a limit is 0 (the
# script's own "no limit").
START_LIMIT = (BOOT_TIMEOUT + 1 + HOME_LIMIT + TERM_WAIT + 1 + ADB_CALLS * ADB_CALL
               if BOOT_TIMEOUT and HOME_LIMIT else None)
# stop-emulator.sh: the save, the emulator's exit, then a kill and adb unlisting it.
STOP_LIMIT = STOP_SAVE_WAIT + 2 * STOP_TIMEOUT + 2 * KILL_WAIT + ADB_CALLS * ADB_CALL


def lib(snippet):
    """Runs a bash snippet with the library sourced, in the developer's real environment."""
    sources = "\n".join(f"source {LIB / name}" for name in ("sdk.sh", "avd.sh", "device.sh"))
    return subprocess.run(["bash", "-c", f"{sources}\n{snippet}"],
                          capture_output=True, text=True, timeout=60).stdout.strip()


def default_avd():
    return os.environ.get("AWDT_AVD") or lib(
        'avds="$(list_avds)"; grep -qx "$DEFAULT_AVD" <<<"$avds" && echo "$DEFAULT_AVD" '
        '|| grep -m 1 -E "^(phone|tablet)_" <<<"$avds"')


def serial_of(avd):
    """The serial of that AVD's running emulator, or None."""
    return lib(f'for s in $(running_emulators); do [ "$(emulator_avd "$s")" = {avd} ] '
               '&& echo "$s"; done') or None


def exited(pid):
    """Whether a process has exited: it's gone, or a zombie its parent hasn't reaped yet, which
    holds nothing (under WSL the emulator's parent is init's relay, which reaps it a moment
    later)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return True


def start_script(*args, env=None):
    """Runs start-emulator.sh, which gives up on a boot before Python gives up on it."""
    return subprocess.run([str(BIN / "start-emulator.sh"), *args], capture_output=True, text=True,
                          timeout=START_LIMIT,
                          env={**os.environ, "AWDT_BOOT_TIMEOUT": str(BOOT_TIMEOUT),
                               "AWDT_HOME_TIMEOUT": str(HOME_TIMEOUT), **(env or {})})


def start(avd, *flags, env=None):
    """Boots an AVD for a test: no window unless a test's env names a display, no snapshot saved."""
    window = [] if env and "DISPLAY" in env else ["-no-window"]
    return start_script(avd, *window, "-no-snapshot-save",
                        *shlex.split(os.environ.get("AWDT_TEST_EMULATOR_FLAGS", "")), *flags,
                        env=env)


def stop(target, stop_timeout=STOP_TIMEOUT):
    """Runs stop-emulator.sh --no-save: a test run's changes don't matter."""
    return subprocess.run([str(BIN / "stop-emulator.sh"), "--no-save", target],
                          capture_output=True, text=True, timeout=STOP_LIMIT,
                          env={**os.environ, "AWDT_STOP_TIMEOUT": str(stop_timeout)})


def scratch_files():
    """The disk overlays -read-only emulators keep in their scratch folder."""
    folder = Path(tempfile.gettempdir()) / f"android-{getpass.getuser()}"
    return set(folder.glob("emulator-*")) if folder.is_dir() else set()


def remove_new_scratch_files(before):
    for path in scratch_files() - before:
        path.unlink(missing_ok=True)


def emulator_pids(*args):
    """The PIDs of the running emulators with all these arguments on their command lines."""
    pids = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            command = (path / "cmdline").read_bytes().decode(errors="replace").split("\0")
        except OSError:
            continue
        if "qemu-system" in Path(command[0]).name and all(arg in command for arg in args):
            pids.append(int(path.name))
    return pids


class Device:
    """A running emulator, and what the probe saw on it."""

    def __init__(self, serial):
        self.serial = serial
        self.env = {**os.environ, "ANDROID_SERIAL": serial}

    def adb(self, *args, timeout=TOUCH_LIMIT):
        return subprocess.run([lib('echo "$ADB"'), "-s", self.serial, *args], capture_output=True,
                              text=True, timeout=timeout, stdin=subprocess.DEVNULL)

    def shell(self, *args):
        return self.adb("shell", *args).stdout.replace("\r", "")

    def touch(self, *args):
        return self.tool("touch.sh", *args)

    def ui(self, *args):
        return self.tool("ui.sh", *args)

    def tool(self, name, *args):
        return subprocess.run([str(BIN / name), *map(str, args)], capture_output=True, text=True,
                              timeout=TOUCH_LIMIT, env=self.env, stdin=subprocess.DEVNULL)

    def install_probe(self):
        self.adb("uninstall", "awdt.probe")
        installed = self.adb("install", str(PROBE))
        if "Success" not in installed.stdout:
            raise AssertionError(f"couldn't install the probe:\n{installed.stdout}{installed.stderr}")

    def remove_probe(self):
        self.adb("uninstall", "awdt.probe")
        self.shell("rm", "-f", "/data/local/tmp/awdt-*")

    def open_probe(self):
        """A fresh probe in front, its window focused, and an empty log."""
        self.shell("am", "force-stop", "awdt.probe")
        deadline = time.monotonic() + FOCUS_TIMEOUT
        focused = ""
        while time.monotonic() < deadline:
            self.shell("am", "start", "-n", PROBE_ACTIVITY)
            time.sleep(1)
            focused = self.ui("front").stdout
            if re.search(r"mCurrentFocus=.*awdt\.probe/", focused):
                break
        else:
            raise AssertionError(f"the probe didn't come to the front:\n{focused}")
        self.adb("logcat", "-c")

    def log(self):
        output = self.adb("logcat", "-d", "-s", "AwdtProbe:I").stdout
        return [line.split("AwdtProbe: ", 1)[1].strip() for line in output.splitlines()
                if "AwdtProbe: " in line]

    def wait_for_log(self, pattern, why=""):
        """Waits until the probe has logged a line matching `pattern`; returns its match."""
        deadline = time.monotonic() + EVENT_TIMEOUT
        lines = []
        while time.monotonic() < deadline:
            lines = self.log()
            for line in lines:
                found = re.search(pattern, line)
                if found:
                    return found
            time.sleep(0.2)
        raise AssertionError(f"the probe logged no {pattern!r} {why}; it logged:\n"
                             + "\n".join(lines[-30:]))

    def touches(self, action):
        """How many touches of that action the probe logged, by its pointer counts."""
        return [int(found.group(1)) for line in self.log()
                if (found := re.match(rf"TOUCH ACTION_{action} pointers=(\d+)", line))]

    def area_center(self):
        """The center of the probe's touch area."""
        found = self.ui("find", "id:probe_area")
        if found.returncode != 0:
            raise AssertionError(f"no probe area:\n{found.stdout}{found.stderr}")
        return tuple(int(n) for n in found.stdout.split())

    def api(self):
        return int(self.shell("getprop", "ro.build.version.sdk").strip())


@unittest.skipUnless(ENABLED, "real-emulator tests run only with: tests/run.py --emulator")
class OnTheRealEmulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.avd = default_avd()
        if not cls.avd:
            raise unittest.SkipTest("no phone or tablet AVD: create one with create-avd.sh")
        cls.started = None
        serial = serial_of(cls.avd)
        cls.was_running = bool(serial)
        if not serial:
            # Registered before the boot: tearDownClass isn't called when setUpClass fails, and a
            # failed start leaves the emulator to this cleanup.
            cls.addClassCleanup(stop, cls.avd)
            cls.started = start(cls.avd, "--wait-for-home")
            if cls.started.returncode != 0:
                raise AssertionError(f"couldn't boot {cls.avd}:\n{cls.started.stderr}")
            serial = cls.started.stdout.strip()
        cls.device = Device(serial)
        cls.device.install_probe()
        cls.addClassCleanup(cls.device.remove_probe)

    def setUp(self):
        self.device.open_probe()

    # --- Booting --------------------------------------------------------------------------------

    def test_start_returns_once_android_has_booted(self):
        if self.was_running:
            self.skipTest(f"{self.avd} was already running")
        self.assertRegex(self.started.stdout, r"^emulator-\d+\n$")
        self.assertEqual(self.device.shell("getprop", "sys.boot_completed").strip(), "1")

    def test_start_waits_for_home_until_the_home_app_has_the_focus(self):
        if self.was_running:
            self.skipTest(f"{self.avd} was already running")
        self.assertRegex(self.started.stderr, r"The home app \(\S+\) is in front\.")

    def test_no_app_was_reported_as_not_responding_while_it_booted(self):
        # An ANR dialog stays over the home screen until someone taps it. System UI's own, at each
        # cold boot on API 36 and 37, is why the renderer is what it is (sdk.sh).
        if self.was_running:
            self.skipTest(f"{self.avd} was already running")
        self.assertEqual(self.device.shell("logcat", "-d", "-b", "events", "-s", "am_anr")
                         .replace("--------- beginning of events\n", "").strip(), "")

    def test_start_again_reports_the_running_emulator(self):
        result = start_script(self.avd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.device.serial)
        self.assertIn("already running", result.stderr)

    # --- Gestures -------------------------------------------------------------------------------

    def assert_at(self, found, x, y):
        self.assertLessEqual(abs(int(found.group(1)) - x), 2, found.group(0))
        self.assertLessEqual(abs(int(found.group(2)) - y), 2, found.group(0))

    def played(self, *args):
        result = self.device.touch(*args)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tap_is_a_tap_where_it_was_asked_for(self):
        x, y = self.device.area_center()
        self.played("tap", x, y)
        self.assert_at(self.device.wait_for_log(r"GESTURE TAP x=(\d+) y=(\d+)"), x, y)
        self.assertEqual(self.device.touches("DOWN"), [1])
        self.assertEqual(self.device.touches("UP"), [1])

    def test_double_tap_is_a_double_tap(self):
        x, y = self.device.area_center()
        self.played("double-tap", x, y)
        self.assert_at(self.device.wait_for_log(r"GESTURE DOUBLE_TAP x=(\d+) y=(\d+)"), x, y)

    def test_long_press_is_a_long_press(self):
        x, y = self.device.area_center()
        self.played("long-press", x, y)
        self.assert_at(self.device.wait_for_log(r"GESTURE LONG_PRESS x=(\d+) y=(\d+)"), x, y)
        self.device.wait_for_log(r"TOUCH ACTION_UP")

    def test_a_quick_swipe_is_a_fling(self):
        x, y = self.device.area_center()
        self.played("swipe", x, y + 300, x, y - 300, 80)
        found = self.device.wait_for_log(r"GESTURE FLING vx=(-?\d+) vy=(-?\d+)")
        self.assertLess(int(found.group(2)), 0, "swiped up")

    def test_a_slow_swipe_moves_from_its_start_to_its_end(self):
        x, y = self.device.area_center()
        self.played("swipe", x - 200, y, x + 200, y + 100, 500)
        self.assert_at(self.device.wait_for_log(r"TOUCH ACTION_DOWN pointers=1 x=(\d+) y=(\d+)"),
                       x - 200, y)
        self.assert_at(self.device.wait_for_log(r"TOUCH ACTION_UP pointers=1 x=(\d+) y=(\d+)"),
                       x + 200, y + 100)
        self.assertGreater(len(self.device.touches("MOVE")), 5)

    def test_drag_holds_then_moves(self):
        x, y = self.device.area_center()
        self.played("drag", x - 200, y, x + 200, y + 200)
        self.device.wait_for_log(r"GESTURE LONG_PRESS")
        self.assert_at(self.device.wait_for_log(r"TOUCH ACTION_UP pointers=1 x=(\d+) y=(\d+)"),
                       x + 200, y + 200)
        log = self.device.log()
        pressed = next(i for i, line in enumerate(log) if "LONG_PRESS" in line)
        self.assertTrue(any("ACTION_MOVE" in line for line in log[pressed:]),
                        "moved only after the long press")

    def test_pinch_spreads_and_closes_two_fingers(self):
        x, y = self.device.area_center()
        for start_span, end_span in ((300, 800), (800, 300)):
            with self.subTest(frm=start_span, to=end_span):
                self.device.adb("logcat", "-c")
                self.played("pinch", x, y, start_span, end_span)
                found = self.device.wait_for_log(r"SPAN from=(\d+) to=(\d+)")
                self.assertLessEqual(abs(int(found.group(1)) - start_span), 2, found.group(0))
                self.assertLessEqual(abs(int(found.group(2)) - end_span), 2, found.group(0))
                self.device.wait_for_log(r"GESTURE SCALE")
                self.assertEqual(max(self.device.touches("MOVE")), 2)

    def test_rotate_turns_two_fingers(self):
        x, y = self.device.area_center()
        self.played("rotate", x, y, 500, 90)
        found = self.device.wait_for_log(r"TURN degrees=(-?\d+)")
        self.assertLessEqual(abs(int(found.group(1)) - 90), 2, found.group(0))

    def test_percentages_are_of_the_screen(self):
        width, height = map(int, lib(f"screen_size {self.device.serial}").split())
        self.played("tap", "50%", "75%")
        self.assert_at(self.device.wait_for_log(r"GESTURE TAP x=(\d+) y=(\d+)"),
                       width // 2, height * 3 // 4)

    def test_percentages_follow_a_turned_screen(self):
        device = self.device
        settings = {name: device.shell("settings", "get", "system", name).strip()
                    for name in ("accelerometer_rotation", "user_rotation")}

        def restore():
            for name, value in settings.items():
                if value == "null":
                    device.shell("settings", "delete", "system", name)
                else:
                    device.shell("settings", "put", "system", name, value)
        self.addCleanup(restore)
        portrait = lib(f"screen_size {device.serial}")
        device.shell("settings", "put", "system", "accelerometer_rotation", "0")
        device.shell("settings", "put", "system", "user_rotation", "1")
        deadline = time.monotonic() + FOCUS_TIMEOUT
        while lib(f"screen_size {device.serial}") == portrait and time.monotonic() < deadline:
            time.sleep(0.5)
        width, height = map(int, lib(f"screen_size {device.serial}").split())
        self.assertGreater(width, height, "the screen didn't turn")
        self.device.ui("wait", "Probe button", 30)
        self.device.adb("logcat", "-c")
        self.played("tap", "50%", "90%")
        self.assert_at(self.device.wait_for_log(r"GESTURE TAP x=(\d+) y=(\d+)"),
                       width // 2, height * 9 // 10)

    # --- Seeing the screen ----------------------------------------------------------------------

    def test_list_names_what_is_on_the_screen(self):
        result = self.device.ui("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Older themes write a button in capitals.
        self.assertRegex(result.stdout, r"(?i)Button .*Probe button.* id=probe_button .*clickable")

    def test_tap_by_text_presses_the_button(self):
        result = self.device.ui("tap", "probe button")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.device.wait_for_log(r"^CLICK$")

    def test_tap_by_id_presses_the_button(self):
        result = self.device.ui("tap", "id:probe_button")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.device.wait_for_log(r"^CLICK$")

    def test_find_fails_for_what_is_not_there(self):
        self.assertEqual(self.device.ui("find", "text:no such element").returncode, 1)

    def test_long_press_by_text(self):
        # Android long-clicks a button without a listener for it as nothing, so this looks at the
        # probe's area, whose touches it logs.
        result = self.device.ui("long-press", "id:probe_area")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.device.wait_for_log(r"GESTURE LONG_PRESS")

    def test_type_writes_text_with_spaces_and_quotes_into_the_field(self):
        self.assertEqual(self.device.ui("tap", "id:probe_field").returncode, 0)
        time.sleep(1)
        text = "it's a test & more"
        result = self.device.ui("type", text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.device.wait_for_log(re.escape(f"TEXT [{text}]"))

    def test_wait_and_wait_gone_follow_the_screen(self):
        self.assertEqual(self.device.ui("wait", "Probe button", 30).returncode, 0)
        self.device.shell("input", "keyevent", "HOME")
        self.assertEqual(self.device.ui("wait-gone", "Probe button", 60).returncode, 0)

    def test_wait_fails_at_its_limit(self):
        result = self.device.ui("wait", "text:no such element", 1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("within 1 s", result.stderr)

    def test_shot_saves_a_png_of_the_screen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            result = self.device.ui("shot", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = path.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual(f"{width} {height}", lib(f"screen_size {self.device.serial}"))

    def test_front_names_the_app_in_front(self):
        self.assertIn("awdt.probe/", self.device.ui("front").stdout)


@unittest.skipUnless(ENABLED, "real-emulator tests run only with: tests/run.py --emulator")
class MouseOnTheEmulatorsWindow(unittest.TestCase):
    """The mouse in the emulator's window as a finger: the real window, on a private X server, with
    real pointer events (XTest, which WSLg's own display ignores). So this checks everything from
    the X server on, not WSLg's own way to it, which only a real mouse can."""

    @classmethod
    def setUpClass(cls):
        cls.avd = default_avd()
        reason = x11.unavailable_reason()
        if reason or os.environ.get("SCRIPT_TESTS_DISPLAY"):
            raise unittest.SkipTest(reason or "never on a real display")
        if not cls.avd or serial_of(cls.avd):
            raise unittest.SkipTest(f"{cls.avd} is running, or there's no AVD")

    def test_a_click_a_hold_and_a_drag_are_touches(self):
        with x11.XServer() as display:
            self.addCleanup(stop, self.avd)
            started = start(self.avd, "--wait-for-home", env={"DISPLAY": display})
            self.assertEqual(started.returncode, 0, started.stderr)
            device = Device(started.stdout.strip())
            device.install_probe()
            device.open_probe()
            width, height = map(int, lib(f"screen_size {device.serial}").split())
            with x11.Pointer(display, f"Android Emulator - {self.avd}:") as pointer:
                pointer.click(0.5, 0.75)
                found = device.wait_for_log(r"GESTURE TAP x=(\d+) y=(\d+)", "for a click")
                self.assertLessEqual(abs(int(found.group(1)) - width / 2), width * 0.02)
                self.assertLessEqual(abs(int(found.group(2)) - height * 0.75), height * 0.02)

                pointer.hold(0.5, 0.75, 1.5)
                device.wait_for_log(r"GESTURE LONG_PRESS", "for a held button")

                device.adb("logcat", "-c")
                pointer.drag(0.3, 0.8, 0.7, 0.6)
                device.wait_for_log(r"GESTURE FLING", "for a drag")
            device.remove_probe()


@unittest.skipUnless(ENABLED, "real-emulator tests run only with: tests/run.py --emulator")
class StopOnTheRealEmulator(unittest.TestCase):
    def setUp(self):
        self.avd = default_avd()
        if not self.avd:
            self.skipTest("no phone or tablet AVD: create one with create-avd.sh")
        if serial_of(self.avd):
            self.skipTest(f"{self.avd} is running, and a test doesn't stop the developer's "
                          "emulator")
        self.addCleanup(stop, self.avd)

    def start_and_get_pid(self):
        """Boots the AVD; returns its serial and its emulator's PID, from the AVD's lock file."""
        started = start(self.avd)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.lock = os.path.join(lib(f"avd_dir {self.avd}"), "hardware-qemu.ini.lock")
        with open(self.lock, "rb") as f:
            return started.stdout.strip(), int(f.read().strip(b"\0").decode())

    def test_stop_kills_an_emulator_that_does_not_answer(self):
        serial, pid = self.start_and_get_pid()
        os.kill(pid, signal.SIGSTOP)   # frozen: its console answers nothing, SIGTERM waits
        result = stop(self.avd, stop_timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("killed (SIGKILL)", result.stderr)
        self.assertTrue(exited(pid), "returned before the emulator had exited")
        again = start(self.avd)   # the lock file it left behind doesn't stop a new start
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_stop_kills_a_read_only_emulator_that_does_not_answer(self):
        # -read-only writes no lock file, and a frozen console can't name the process: the
        # emulator's discovery file names it, found by the AVD's name. Killed, it leaves its disk
        # overlays behind.
        self.addCleanup(remove_new_scratch_files, scratch_files())
        started = start(self.avd, "-read-only")
        self.assertEqual(started.returncode, 0, started.stderr)
        [pid] = emulator_pids("-avd", self.avd, "-read-only")
        self.addCleanup(lambda: exited(pid) or os.kill(pid, signal.SIGKILL))   # if left frozen
        os.kill(pid, signal.SIGSTOP)
        result = stop(self.avd, stop_timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("killed (SIGKILL)", result.stderr)
        self.assertTrue(exited(pid), "returned before the emulator had exited")

    def test_stop_waits_for_a_read_only_emulator(self):
        # -read-only writes no lock file: the emulator's console names its process instead.
        started = start(self.avd, "-read-only")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertFalse(os.path.exists(os.path.join(lib(f"avd_dir {self.avd}"),
                                                     "hardware-qemu.ini.lock")))
        [pid] = emulator_pids("-avd", self.avd, "-read-only")
        result = stop(self.avd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exited(pid), "returned before the emulator had exited")

    def test_stop_an_emulator_that_is_exiting_already(self):
        # As when the test run that started it is killed: after SIGTERM its console answers
        # nothing, and adb lists it for a moment after its exit. Depending on when the script gets
        # there it sees it running, exiting or gone; never still running.
        started = start(self.avd, "-read-only")
        self.assertEqual(started.returncode, 0, started.stderr)
        serial = started.stdout.strip()
        [pid] = emulator_pids("-avd", self.avd, "-read-only")
        os.kill(pid, signal.SIGTERM)
        result = stop(serial)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("still running", result.stderr)
        self.assertNotIn(serial, lib("running_emulators").split())

    def test_stop_returns_once_the_avd_can_start_again(self):
        avd = self.avd
        serial, pid = self.start_and_get_pid()
        lock = self.lock

        result = stop(avd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Stopped '{avd}' ({serial}).", result.stderr)
        self.assertTrue(exited(pid), "returned before the emulator had exited")
        self.assertFalse(os.path.exists(lock))
        self.assertNotIn(serial, lib("running_emulators").split())

        again = start(avd)   # right away: the AVD's files are free
        self.assertEqual(again.returncode, 0, again.stderr)
        result = stop(avd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(serial_of(avd))
