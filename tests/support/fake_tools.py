"""Fake versions of the external programs the scripts call: adb, emulator, avdmanager, and the
host commands python3, getent, id and sg; javac and d8 for lib/build-gesture.sh.

Each fake is a small wrapper file (written by sandbox.py) that calls main(<tool name>). The fakes
behave like the real tools as far as the scripts can tell (same output formats, exit codes and
side effects) and share their state through files in $FAKE_STATE, so a test can arrange a
situation (AVDs, running emulators, connected devices, failures) and afterwards check every call
that was made. They never touch the real SDK, emulator or devices.

State directory ($FAKE_STATE):
  calls.jsonl             one JSON line per call: {"tool", "argv", "android_serial", "time"}
                          (time: time.time() when it was made)
  behavior.json           knobs set by the test, see DEFAULT_BEHAVIOR
  running/<serial>.json   a running fake emulator: {"avd", "pid", "polls", "offline", "hidden",
                          "stop_at", "stuck", "discoverable", "console_hung", "settings" (secure)}
  device/<serial>.json    what's on a device, emulator or physical: {"files": {path: text}
                          (adb push, uiautomator dump), "gestures": [[argument, ...], ...] (what
                          the Gesture program was given), "typed": [text, ...] (input text)}
  devices.json            serials of connected physical devices
  counters.json           per-knob counters (e.g. how many key events failed so far)
"""
import ctypes
import json
import os
import re
import shlex
import signal
import sys
import time
import zlib
from pathlib import Path

HOME = "com.android.launcher3/.uioverrides.QuickstepLauncher"
HOME_WINDOW = "com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher"
FALLBACK_HOME = "com.android.settings/.FallbackHome"

DEFAULT_BEHAVIOR = {
    "boot_polls": 0,              # getprop sys.boot_completed answers "" this many times, then "1"
    "adb_offline": None,          # a booting emulator shows as "offline" in adb devices and its
                                  # adb shell calls fail: for this many boot polls (a slow cold
                                  # boot), "until_reconnect" (a stale Quick Boot snapshot, fixed by
                                  # adb reconnect offline) or "forever"
    "emulator_crash": None,       # emulator prints this and exits 1 instead of booting
    "emulator_signal": None,      # emulator dies of this signal (e.g. "SEGV") instead of booting,
                                  # with nothing about it in its log
    "emulator_hidden": False,     # emulator keeps running but never shows up in adb devices
    "emulator_exit_delay": 0,     # seconds an emulator keeps running after `adb emu kill` (saving
                                  # its Quick Boot snapshot) while adb devices no longer lists it:
                                  # the case where waiting for adb alone would return too early
    "emulator_stuck": False,      # a started emulator answers `adb emu kill` with OK but keeps
                                  # running, and ignores SIGTERM: only SIGKILL stops it
    "emulator_already_exiting": False,  # `adb emu kill` finds a started emulator shutting down
                                  # already (sent SIGTERM by someone else, e.g. with a test run that
                                  # was killed): its console no longer answers that call, which
                                  # fails, and the emulator exits then
    "adb_lists_exited": 0,        # adb devices keeps listing an emulator whose process has exited
                                  # (a zombie, or gone) as offline for this many more calls, as adb
                                  # notices only a moment later; meanwhile its console refuses
                                  # connections
    "emulator_lock_file": True,   # a started emulator writes hardware-qemu.ini.lock; False: it
                                  # writes none, like a real one started with -read-only
    "emulator_discoverable": True,  # a started emulator's console answers `adb emu avd
                                  # discoverypath` with the path of its discovery file,
                                  # pid_<pid>.ini; False: like a console without that command,
                                  # it answers with its help and "KO:  bad sub-command"
    "emulator_discovery_file": True,  # a started emulator writes its discovery file,
                                  # $XDG_RUNTIME_DIR/avd/running/pid_<pid>.ini, and deletes it when
                                  # it exits, unless it's killed with SIGKILL; False: none, or one
                                  # where the scripts don't look
    "emulator_console_hangs": False,  # a started emulator's console never answers any `adb emu`
                                  # call, like a hung emulator's (e.g. one stopped with SIGSTOP);
                                  # adb still lists it
    "emulator_noise": True,       # emulator -list-avds prints a log line before the names
    "device_settings": {},        # secure settings a newly booted emulator starts with, e.g.
                                  # {"long_press_timeout": "400"}; unset ones read as "null"
    "pending_package_write": None,  # from API 33 on (api_level), mobile-stop-emulator.sh waits for
                                  # Android's own write of the app states: seconds after the
                                  # first `adb shell logcat -b events` call until a
                                  # commit_sys_config_file event for package-user-0 shows; None:
                                  # nothing pending, only an older such event shows
    "earlier_package_write": True,  # the events log holds a write of the app states from long
                                  # ago (False: none, as on an image that logs none)
    "sync_error": None,           # `adb shell sync` prints this and exits 1
    "push_error": None,           # `adb push` prints this and exits 1
    "gesture_output": None,       # the Gesture program prints this instead of "Events injected: <n>"
                                  # (it failed): adb's exit status is 1, or 0 before API 24, where
                                  # adb shell doesn't pass exit statuses on
    "screen_size": "1080x2400",   # the screen as `dumpsys window displays` calls it cur=; None:
                                  # the dump has no such line
    "screen_turned": False,       # the screen is turned: cur= is that size the other way round,
                                  # while init= stays the natural size, as `wm size` does
    "ui_hierarchy": ['<hierarchy rotation="0"/>'],
                                  # what `uiautomator dump` writes, one per successful dump, the
                                  # last one repeated
    "ui_idle_failures": 0,        # the first N dumps answer "could not get idle state", as on a
                                  # screen that keeps animating, and write nothing
    "screenshot": "\x89PNG\r\n\x1a\nfake",
                                  # the bytes `adb exec-out screencap -p` writes (latin-1); None:
                                  # it fails
    "api_level": 25,              # every device's `getprop ro.build.version.sdk`; below 24 there's
                                  # no `cmd` (adb shell prints "cmd: not found" and exits 0)
    "home_resolves": [HOME],      # what `cmd package resolve-activity --brief` answers for a HOME
                                  # intent, one per call, the last one repeated: e.g. FallbackHome
                                  # (FALLBACK_HOME) first, as until the user is unlocked
    "user_unlocked": None,        # whether `dumpsys user` shows user 0 unlocked (RUNNING_UNLOCKED);
                                  # None: unless a HOME intent resolves to FallbackHome (the latest
                                  # answer of resolve-activity)
    "home_activities": None,      # what `cmd package query-activities --components` lists for a
                                  # HOME intent, one list per call, the last one repeated; None:
                                  # FallbackHome, and the activity HOME resolves to while the user
                                  # is unlocked (before, Android lists only direct boot aware ones)
    "front": [[HOME, HOME_WINDOW]],  # [focused activity (mFocusedApp), focused window's title
                                  # (mCurrentFocus)] that `dumpsys window` shows, one per call, the
                                  # last one repeated; None: null. A "BACK" item: the ones after it
                                  # come only once `input keyevent BACK` was sent (one per BACK).
                                  # `dumpsys activity activities` shows that activity at the top,
                                  # resumed and idle, in the home app's task if it's of the home
                                  # app's package (that of the activity HOME resolves to; before
                                  # API 24, of the last home_resolves, in a task a HOME intent
                                  # started), else in a task of its own above it. An item can be
                                  # {"window": ..., "activities": ...} instead: the two dumps as
                                  # they are, e.g. captured from a device
    "adb_hangs": {},              # {"getprop": N, "avd_name": N, "emu_kill": N, "gesture": N}: the
                                  # first N `adb shell getprop sys.boot_completed`, `adb emu avd
                                  # name`, `adb emu kill` or gesture calls never return, like adb
                                  # on a half-booted emulator starved of CPU, or on a hung one
    "adb_late": [],               # ["emu_kill"]: `adb emu kill` is made (and logged) only in the
                                  # last 0.1 s before the clock's next whole second, where a time
                                  # limit counted in whole seconds ($SECONDS) would end early
    "avd_home": None,             # avdmanager/emulator use this AVD folder, ignoring the env vars
    "avdmanager_xdg": False,      # avdmanager acts like cmdline-tools 12.0 (GitHub's runners): with
                                  # $XDG_CONFIG_HOME set, it creates AVDs in
                                  # $XDG_CONFIG_HOME/.android/avd, where the emulator doesn't look,
                                  # unless $ANDROID_AVD_HOME names an existing folder
    "avdmanager_error": None,     # avdmanager create prints this and exits 1
    "user": "tester",             # the user the scripts run as (`id -un`)
    "kvm_group_members": [],      # users listed by `getent group kvm`
    "kvm_primary_group": False,   # kvm is the user's primary group: `id -nG` lists it, getent
                                  # doesn't list the user as a member
    "kvm_group_gid": None,        # gid of the kvm group; None = the gid of $AWDT_KVM_DEVICE,
                                  # i.e. the device belongs to the kvm group
    "javac_error": None,          # javac prints this and exits 1
    "python3_exit": 0,     # exit code of the fake python3 standing in for mobile-wslg-toolbar.py
}

STATE = Path(os.environ["FAKE_STATE"])
RUNNING = STATE / "running"
FIRST_PORT = 5554


def behavior():
    path = STATE / "behavior.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    return {**DEFAULT_BEHAVIOR, **data}


def counters():
    path = STATE / "counters.json"
    return json.loads(path.read_text()) if path.exists() else {}


def take(counter, limit):
    """Counts calls for a knob: True for the first `limit` calls, then False."""
    counted = counters()
    counted[counter] = counted.get(counter, 0) + 1
    (STATE / "counters.json").write_text(json.dumps(counted))
    return counted[counter] <= limit


def step(knob):
    """For knobs that list what a device shows over time: this call's item, the last one once
    they're used up."""
    path = STATE / "counters.json"
    counts = json.loads(path.read_text()) if path.exists() else {}
    counts[knob] = counts.get(knob, 0) + 1
    path.write_text(json.dumps(counts))
    items = behavior()[knob]
    return items[min(counts[knob], len(items)) - 1]


def front(advance=True):
    """What's in front for this call, from the `front` knob: its items up to the next "BACK", one
    per call (the last one repeated), until as many Back keys as BACKs before them were sent."""
    parts = [[]]
    for item in behavior()["front"]:
        if item == "BACK":
            parts.append([])
        else:
            parts[-1].append(item)
    path = STATE / "counters.json"
    counts = json.loads(path.read_text()) if path.exists() else {}
    part = min(counts.get("backs", 0), len(parts) - 1)
    key = f"front_{part}"
    if advance:
        counts[key] = counts.get(key, 0) + 1
        path.write_text(json.dumps(counts))
    return parts[part][min(max(counts.get(key, 1), 1), len(parts[part])) - 1]


def hang_if(call):
    """Never returns for the first adb_hangs[call] calls, until something kills this process."""
    if take(f"hang_{call}", behavior()["adb_hangs"].get(call, 0)):
        time.sleep(3600)


def log_call(tool, argv):
    if os.environ.get("FAKE_NO_LOG"):    # set by the sandbox for calls that only arrange a test
        return
    with open(STATE / "calls.jsonl", "a") as f:
        f.write(json.dumps({"tool": tool, "argv": argv, "time": time.time(),
                            "android_serial": os.environ.get("ANDROID_SERIAL")}) + "\n")


LATE_CALLS = {"emu_kill": lambda tool, args: tool == "adb" and args[-2:] == ["emu", "kill"]}


def wait_if_late(tool, args):
    """For the calls adb_late names: waits until the last 0.1 s before the next whole second."""
    if any(LATE_CALLS[call](tool, args) for call in behavior()["adb_late"]):
        time.sleep((0.9 - time.time() % 1) % 1)


def fail(message, code=1):
    print(message, file=sys.stderr)
    sys.exit(code)


# --- AVDs -----------------------------------------------------------------------------------

def avd_home():
    """The folder AVDs are created in and listed from, following the real tools' variables."""
    override = behavior()["avd_home"]
    if override:
        return Path(override)
    env = os.environ
    if env.get("ANDROID_AVD_HOME"):
        return Path(env["ANDROID_AVD_HOME"])
    if env.get("ANDROID_EMULATOR_HOME"):
        return Path(env["ANDROID_EMULATOR_HOME"]) / "avd"
    if env.get("ANDROID_USER_HOME"):
        return Path(env["ANDROID_USER_HOME"]) / "avd"
    if env.get("ANDROID_SDK_HOME"):
        return Path(env["ANDROID_SDK_HOME"]) / ".android" / "avd"
    return Path(env["HOME"]) / ".android" / "avd"


def avdmanager_home():
    """The folder avdmanager creates AVDs in: the emulator's, except with avdmanager_xdg."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    avd_env = os.environ.get("ANDROID_AVD_HOME")
    if behavior()["avdmanager_xdg"] and xdg and not (avd_env and Path(avd_env).is_dir()):
        return Path(xdg) / ".android" / "avd"
    return avd_home()


def avd_folder(name):
    """The <name>.avd folder of an AVD, as its <name>.ini's path= line says."""
    ini = avd_home() / f"{name}.ini"
    for line in ini.read_text().splitlines():
        if line.startswith("path="):
            return Path(line[len("path="):])
    return avd_home() / f"{name}.avd"


def avd_names():
    home = avd_home()
    return sorted(p.stem for p in home.glob("*.ini")) if home.is_dir() else []


# --- Running emulators and devices ----------------------------------------------------------

def alive(pid):
    """Whether a process runs; a killed one its parent hasn't reaped yet (a zombie) doesn't."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def running():
    """{serial: info} of the running fake emulators whose process is still alive."""
    result = {}
    for path in sorted(RUNNING.glob("emulator-*.json")):
        try:
            info = json.loads(path.read_text())
        except ValueError:
            continue
        if not alive(info["pid"]):
            continue
        if not info.get("hidden"):
            result[path.stem] = info
    return result


def listed_exited(poll=False):
    """{serial: info} of the fake emulators whose process has exited but that adb still lists
    (adb_lists_exited); poll=True counts this as one of those listings (adb devices)."""
    limit = behavior()["adb_lists_exited"]
    result = {}
    for path in sorted(RUNNING.glob("emulator-*.json")) if limit else ():
        try:
            info = json.loads(path.read_text())
        except ValueError:
            continue
        if alive(info["pid"]) or info.get("hidden"):
            continue
        counter = f"listed_exited_{info['pid']}"
        listed = take(counter, limit) if poll else counters().get(counter, 0) < limit
        if listed:
            result[path.stem] = info
    return result


def physical_devices():
    path = STATE / "devices.json"
    return json.loads(path.read_text()) if path.exists() else []


def is_offline(info):
    state = info.get("offline")
    return state in ("until_reconnect", "forever") or (isinstance(state, int) and state > 0)


def write_running(serial, info):
    tmp = RUNNING / f".{serial}.tmp"
    tmp.write_text(json.dumps(info))
    tmp.rename(RUNNING / f"{serial}.json")   # atomic: adb never sees a half-written file


# --- adb ------------------------------------------------------------------------------------

def adb(args):
    serial = None
    if args[:1] == ["-s"]:
        serial, args = args[1], args[2:]
    if args[:1] == ["devices"]:
        print("List of devices attached")
        for s, info in running().items():
            print(f"{s}\t{'offline' if is_offline(info) else 'device'}")
        for s in listed_exited(poll=True):
            print(f"{s}\toffline")
        for s in physical_devices():
            print(f"{s}\tdevice")
        print()
        return
    if args == ["reconnect", "offline"]:
        for s, info in running().items():
            if is_offline(info):
                print(f"reconnecting {s}")
                if info["offline"] == "until_reconnect":
                    info["offline"] = None
                    write_running(s, info)
        return
    if args[:1] in (["start-server"], ["kill-server"]):
        return

    emulators = running()
    devices = list(emulators) + physical_devices()
    serial = serial or os.environ.get("ANDROID_SERIAL")
    if serial is None:
        if not devices:
            fail("adb: no devices/emulators found")
        if len(devices) > 1:
            fail("adb: more than one device/emulator")
        serial = devices[0]
    if serial not in devices and serial in listed_exited():
        if args[:1] == ["emu"]:
            fail(f"error: could not connect to TCP port {serial.split('-')[1]}: Connection refused")
        fail("error: device offline")
    if serial not in devices:
        fail(f"adb: device '{serial}' not found")

    if args[:1] == ["wait-for-device"]:
        return
    if args[:1] == ["shell"] and not sys.stdin.isatty():
        sys.stdin.read()   # the real adb shell forwards its stdin to the device, using it up
    if args[:1] == ["shell"] and serial in emulators and is_offline(emulators[serial]):
        info = emulators[serial]
        if isinstance(info["offline"], int):
            info["offline"] -= 1
            write_running(serial, info)
        fail("error: device offline")
    if args[:1] == ["emu"]:
        if serial not in emulators:
            fail(f"error: {serial} is not an emulator")
        adb_emu(serial, emulators[serial], args[1:])
    elif args[:3] == ["shell", "getprop", "sys.boot_completed"]:
        hang_if("getprop")
        if serial in emulators:
            info = emulators[serial]
            info["polls"] += 1
            write_running(serial, info)
            ready = info["polls"] > behavior()["boot_polls"]
        else:
            ready = True
        sys.stdout.write("1\r\n" if ready else "\r\n")   # real adb shell output ends in \r\n
    elif args[:4] == ["shell", "settings", "get", "secure"] and len(args) == 5:
        settings = emulators[serial]["settings"] if serial in emulators else {}
        sys.stdout.write(f"{settings.get(args[4], 'null')}\r\n")
    elif args[:1] == ["push"] and len(args) == 3:
        if behavior()["push_error"]:
            fail(behavior()["push_error"])
        try:
            text = Path(args[1]).read_bytes().decode("latin-1")   # a dex isn't text
        except OSError:
            fail(f"adb: error: cannot stat '{args[1]}': No such file or directory")
        state = device_state(serial)
        state["files"][args[2]] = text
        write_device_state(serial, state)
        print(f"{args[1]}: 1 file pushed, 0 skipped.")
    elif len(args) == 2 and args[0] == "shell" and (found := GESTURE.fullmatch(args[1])):
        gesture(serial, found)
    elif len(args) == 2 and args[0] == "shell" and (found := UI_DUMP.fullmatch(args[1])):
        ui_dump(serial, found["path"])
    elif len(args) == 2 and args[0] == "shell" and args[1].startswith("input text "):
        input_text(serial, args[1])
    elif args[:2] == ["exec-out", "cat"] and len(args) == 3:
        exec_out_cat(serial, args[2])
    elif args == ["exec-out", "screencap", "-p"]:
        exec_out_screencap()
    elif args[:3] == ["shell", "input", "keyevent"] and len(args) == 4:
        if args[3] in ("BACK", "4"):
            take("backs", 0)   # only counts them, for front()
    elif args == ["shell", "getprop", "ro.build.version.sdk"]:
        sys.stdout.write(f"{behavior()['api_level']}\r\n")
    elif args[:2] == ["shell", "cmd"] and behavior()["api_level"] < 24:
        sys.stdout.write("/system/bin/sh: cmd: not found\r\n")
    elif args[:4] == ["shell", "cmd", "package", "resolve-activity"] \
            and "android.intent.category.HOME" in args:
        sys.stdout.write("priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 "
                         f"isDefault=true\r\n{step('home_resolves')}\r\n")
    elif args[:4] == ["shell", "cmd", "package", "query-activities"] \
            and "android.intent.category.HOME" in args and "--components" in args:
        listed = home_activities()
        sys.stdout.write("".join(f"{a}\r\n" for a in listed) if listed else "No activities found\r\n")
    elif args == ["shell", "dumpsys", "user"]:
        dumpsys_user()
    elif args == ["shell", "dumpsys", "window"]:
        shown = front()
        if isinstance(shown, dict):
            sys.stdout.write(shown["window"].replace("\n", "\r\n"))
        else:
            dumpsys_window(*shown)
    elif args == ["shell", "dumpsys", "window", "displays"]:
        dumpsys_window_displays()
    elif args == ["shell", "dumpsys", "activity", "activities"]:
        shown = front(advance=False)
        if isinstance(shown, dict):
            sys.stdout.write(shown["activities"].replace("\n", "\r\n"))
        else:
            dumpsys_activities(shown[0])
    elif args == ["shell", "dumpsys", "package", "write"]:
        # Up to API 31 Android writes the app states and says so; from 33 on it prints the dump.
        if behavior()["api_level"] < 33:
            sys.stdout.write("Settings written.\r\n")
        else:
            sys.stdout.write("Database versions:\r\n  Internal:\r\n    sdkVersion=36\r\n"
                             * 200)
    elif args == ["shell", "sync"]:
        if behavior()["sync_error"]:
            fail(behavior()["sync_error"])
    elif args == ["shell", "logcat", "-b", "events", "-d", "-v", "epoch", "-s",
                  "commit_sys_config_file"]:
        package_write_events()
    else:
        fail(f"fake adb: unsupported command {args}")


def package_write_events():
    """The events log's commit_sys_config_file events: one of package-user-0 from long ago (unless
    earlier_package_write is False), and a new one pending_package_write seconds after the first
    call, if set."""
    if behavior()["earlier_package_write"]:
        sys.stdout.write("      1790000000.000   500   600 I commit_sys_config_file: [package-user-0,3]\r\n")
    sys.stdout.write("      1790000001.000   500   600 I commit_sys_config_file: [settings-2-0,2]\r\n")
    delay = behavior()["pending_package_write"]
    if delay is None:
        return
    first = STATE / "first_events_look"
    if not first.exists():
        first.write_text(str(time.time()))
    written = float(first.read_text()) + delay
    if time.time() >= written:
        sys.stdout.write(f"      {written:.3f}   500   600 I commit_sys_config_file: [package-user-0,4]\r\n")


def task_of(activity):
    """The home app's task (7) for an activity of its package, else one of its own (9)."""
    return 7 if activity.split("/")[0] == home_package() else 9


def record(activity):
    """An activity's record, as both dumps name it: ActivityRecord{<hash> u0 <activity> t<task>},
    with the task outside the braces on API 33. The hash stays the same for the same activity."""
    braces = "} " if behavior()["api_level"] == 33 else " "
    return f"ActivityRecord{{{zlib.crc32(activity.encode()):x} u0 {activity}{braces}t{task_of(activity)}}}"


def home_activity():
    """The home app's activity: the one a HOME intent resolves to (the latest answer to
    resolve-activity; before API 24, the last of home_resolves)."""
    items = behavior()["home_resolves"]
    if behavior()["api_level"] < 24:
        return items[-1]
    return items[min(counters().get("home_resolves", 1), len(items)) - 1]


def user_unlocked():
    unlocked = behavior()["user_unlocked"]
    return home_activity() != FALLBACK_HOME if unlocked is None else unlocked


def home_activities():
    if behavior()["home_activities"] is not None:
        return step("home_activities")
    if not user_unlocked() or home_activity() == FALLBACK_HOME:
        return [FALLBACK_HOME]
    return [home_activity(), FALLBACK_HOME]


def dumpsys_user():
    """`dumpsys user`, its lines on user 0's state in the format of the API level: the state's
    number up to API 32 (3: RUNNING_UNLOCKED, 1: RUNNING_LOCKED), its name from 33 on; a State
    line of its own from API 26 on."""
    level = behavior()["api_level"]
    state = "RUNNING_UNLOCKED" if user_unlocked() else "RUNNING_LOCKED"
    lines = ["Users:", "  UserInfo{0:Owner:c13} serialNo=0 isPrimary=true"]
    if level >= 26:
        lines.append(f"    State: {state}")
    lines += ["    Created: <unknown>", "", "  Device owner id:-10000", ""]
    if level >= 33:
        lines.append(f"  Started users state: [0={state}]")
    else:
        lines.append(f"  Started users state: {{0={3 if user_unlocked() else 1}}}")
    lines.append("  Max users: 1 (limit reached: true)")
    sys.stdout.write("".join(f"{line}\r\n" for line in lines))


def home_package():
    return home_activity().split("/")[0]


def dumpsys_window(activity, window):
    """The lines of `dumpsys window` on focus, among others, in the format of the API level."""
    focused = record(activity) if activity else "null"
    if activity and behavior()["api_level"] < 29:
        focused = f"AppWindowToken{{1c158a9c token=Token{{9f08a0f {focused}}}}}"
    focus = f"Window{{299ed2cc u0 {window}}}" if window else "null"
    sys.stdout.write("WINDOW MANAGER LAST ANR (dumpsys window lastanr)\r\n"
                     "  <no ANR has occurred since boot>\r\n\r\n"
                     "WINDOW MANAGER WINDOWS (dumpsys window windows)\r\n"
                     f"  Window #0 Window{{5e1 u0 StatusBar}}:\r\n    mOwnerUid=10012\r\n"
                     f"  mCurrentFocus={focus}\r\n  mFocusedApp={focused}\r\n")


def dumpsys_activities(activity):
    """`dumpsys activity activities`: the focused activity at the top, resumed and idle, in the
    home app's task (7) if it's of the home app's package, with the activity HOME resolves to
    under it, else in a task of its own (9) above the home app's. Before API 24 each task shows
    the intent that started it: a HOME intent for the home app's. With no focused activity, the
    home app's alone."""
    home = home_activity()
    old = behavior()["api_level"] < 24
    hist = "* Hist  #" if behavior()["api_level"] >= 34 else "* Hist #"
    tasks = {}   # task -> activities in it, from the top down
    if activity:
        tasks.setdefault(task_of(activity), []).append(activity)
    if home != activity:
        tasks.setdefault(7, []).append(home)
    lines = ["ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)", "Display #0 (activities "
             "from top to bottom):", "  Stack #0:"]
    for task, activities in tasks.items():
        if old:
            intent = ("act=android.intent.action.MAIN cat=[android.intent.category.HOME] "
                      "flg=0x10800000" if task == 7 else "act=android.settings.SETTINGS flg=0x10000000")
            lines += [f"    * TaskRecord{{36c46df{task} #{task} I={activities[-1]} U=0 sz=1}}",
                      f"      intent={{{intent} cmp={activities[-1]}}}"]
        else:
            lines += [f"    * Task{{36c46df{task} #{task} type={'home' if task == 7 else 'standard'} "
                      "A=1000:x U=0 visible=true mode=fullscreen translucent=false sz=1}"]
        for n, shown in enumerate(activities):
            top = shown == (activity or home) and n == 0
            lines += [f"      {hist}{len(activities) - 1 - n}: {record(shown)}",
                      f"          Intent {{ cmp={shown} }}",
                      f"          state={'RESUMED' if top else 'STOPPED'} stopped={str(not top).lower()} "
                      "delayedResume=false finishing=false",
                      "          keysPaused=false inHistory=true visible=true sleeping=false idle=true"]
    focused = record(activity) if activity else "null"
    lines += [f"  mFocusedActivity: {focused}" if old else f"  ResumedActivity: {focused}"]
    sys.stdout.write("\r\n".join(lines) + "\r\n")


def device_state(serial):
    path = STATE / "device" / f"{serial}.json"
    return json.loads(path.read_text()) if path.exists() else {"files": {}, "gestures": [], "typed": []}


def write_device_state(serial, state):
    (STATE / "device").mkdir(exist_ok=True)
    (STATE / "device" / f"{serial}.json").write_text(json.dumps(state))


# The command mobile-touch.sh runs on a device: the program, or first a test whether it's there. A device
# without it says otherwise: "otherwise" of the test, or the error of app_process.
GESTURE = re.compile(r"(?:if \[ -f (?P<wanted>\S+) \]; then )?"
                     r"CLASSPATH=(?P<dex>\S+) app_process /system/bin Gesture (?P<args>.*?)"
                     r"(?:; else echo (?P<otherwise>\S+); fi)?")


def gesture(serial, command):
    """`CLASSPATH=<dex> app_process /system/bin Gesture <arguments>`: runs only with its dex pushed
    to the device, and records its arguments. Prints what the real program prints when it has sent
    its events, or gesture_output if it failed."""
    state = device_state(serial)
    if command["wanted"] and command["wanted"] not in state["files"]:
        print(command["otherwise"])
        return
    hang_if("gesture")
    if command["dex"] not in state["files"]:
        print(f"Error: Unable to open class path: {command['dex']}")
        return
    if behavior()["gesture_output"]:
        sys.stdout.write(behavior()["gesture_output"].replace("\n", "\r\n") + "\r\n")
        sys.exit(1 if behavior()["api_level"] >= 24 else 0)
    state["gestures"].append(command["args"].split())
    write_device_state(serial, state)
    print("Events injected: 2")


UI_DUMP = re.compile(r"rm -f (?P<path>\S+); uiautomator dump (?P=path)")


def ui_dump(serial, path):
    """`rm -f <path>; uiautomator dump <path>`: the dump, or nothing and an error while the screen
    keeps animating. Android's real message has that typo."""
    state = device_state(serial)
    state["files"].pop(path, None)
    if take("ui_idle", behavior()["ui_idle_failures"]):
        write_device_state(serial, state)
        sys.stdout.write("ERROR: could not get idle state.\r\n")
        return
    state["files"][path] = step("ui_hierarchy")
    write_device_state(serial, state)
    sys.stdout.write(f"UI hierchary dumped to: {path}\r\n")


def exec_out_cat(serial, path):
    files = device_state(serial)["files"]
    if path not in files:
        fail(f"cat: {path}: No such file or directory")
    sys.stdout.write(files[path])


def exec_out_screencap():
    if behavior()["screenshot"] is None:
        fail("error: closed")
    sys.stdout.buffer.write(behavior()["screenshot"].encode("latin-1"))


def input_text(serial, command):
    """`input text <text>`, as the device's shell passes it on: what it would type is recorded."""
    try:
        text = shlex.split(command)[2:]
    except ValueError:
        fail("/system/bin/sh: syntax error: unmatched quote")
    if len(text) != 1:
        fail(f"Error: input text takes one argument, not {text}")
    state = device_state(serial)
    state["typed"] += text
    write_device_state(serial, state)


def dumpsys_window_displays():
    """The line of `dumpsys window displays` with the screen's size: init= stays the natural size
    when the screen turns, cur= is the size as it's turned now."""
    print("WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)\r")
    size = behavior()["screen_size"]
    if size:
        width, height = size.split("x")
        turned = f"{height}x{width}" if behavior()["screen_turned"] else size
        print(f"  Display: mDisplayId=0\r\n    init={size} 420dpi cur={turned} app={turned} "
              f"rng=1080x1017-2400x2337\r")


def adb_emu(serial, info, args):
    if info.get("console_hung"):
        time.sleep(3600)
    if args == ["avd", "name"]:
        hang_if("avd_name")
        sys.stdout.write(f"{info['avd']}\r\nOK\r\n")
    elif args == ["avd", "path"]:
        sys.stdout.write(f"{avd_folder(info['avd'])}\r\nOK\r\n")
    elif args == ["avd", "discoverypath"]:
        if info.get("discoverable", True):
            sys.stdout.write(f"{discovery_folder()}/pid_{info['pid']}.ini\r\nOK\r\n")
        else:
            sys.stdout.write("allows you to control (e.g. start/stop) the execution of the virtual "
                             "device\r\n\r\navailable sub-commands:\r\n    name             "
                             "query virtual device name\r\n\r\nKO:  bad sub-command\r\n")
    elif args == ["kill"]:
        hang_if("emu_kill")
        if behavior()["emulator_already_exiting"]:
            os.kill(info["pid"], signal.SIGTERM)
            deadline = time.time() + 5
            while alive(info["pid"]) and time.time() < deadline:
                time.sleep(0.02)
            fail(f"error: could not connect to TCP port {serial.split('-')[1]}: Connection refused")
        print("OK: killing emulator, bye bye")
        if info.get("stuck"):
            return
        delay = behavior()["emulator_exit_delay"]
        if delay:
            # Still running until it has saved its snapshot (see boot()), but gone from adb.
            info["stop_at"] = time.time() + delay
            info["hidden"] = True
            write_running(serial, info)
        else:
            (RUNNING / f"{serial}.json").unlink(missing_ok=True)
            os.kill(info["pid"], signal.SIGTERM)
    else:
        fail(f"fake adb: unsupported emu command {args}")


# --- emulator -------------------------------------------------------------------------------

def emulator(args):
    if args == ["-list-avds"]:
        if behavior()["emulator_noise"]:
            print("INFO    | Storing crashdata in: /tmp/android-unknown/emu-crash-37.db")
        for name in avd_names():
            print(name)
        return
    if args[:1] != ["-avd"] or len(args) < 2:
        fail(f"fake emulator: unsupported arguments {args}")
    print("INFO         | Android emulator version 37.1.11.0 (fake)")
    crash = behavior()["emulator_crash"]
    if crash:
        fail(crash)
    if behavior()["emulator_signal"]:
        die_of_signal(getattr(signal, "SIG" + behavior()["emulator_signal"]))
    name = args[1]
    if name not in avd_names():
        fail(f"ERROR        | Unknown AVD name [{name}], use -list-avds to see valid list.")
    boot(name)


def die_of_signal(signum):
    """Ends this process by the signal itself, not by an exit status, as a crash does. Without a
    core dump: the host's crash handler (apport, systemd-coredump, WSL's) would record one."""
    sys.stdout.flush()
    ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)   # PR_SET_DUMPABLE 0
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def discovery_folder():
    """Where emulators advertise themselves, as the real one picks it ($XDG_RUNTIME_DIR, which the
    sandbox always sets, so the host's /run/user/<uid> is never touched)."""
    return Path(os.environ.get("XDG_RUNTIME_DIR") or STATE / "run") / "avd" / "running"


def boot(name):
    """Registers as a running emulator on the first free port, then runs until killed.
    Like the real one, it writes its PID into hardware-qemu.ini.lock in the AVD's folder
    (NUL-padded), and its discovery file (pid_<PID>.ini in discovery_folder()), and deletes them
    when it exits, unless it's killed with SIGKILL; or it writes neither (emulator_lock_file,
    emulator_discovery_file). Several can run for one AVD, as real -read-only ones can."""
    taken = set(running())
    port = FIRST_PORT
    while f"emulator-{port}" in taken:
        port += 2
    serial = f"emulator-{port}"
    stuck = behavior()["emulator_stuck"]
    signal.signal(signal.SIGTERM, signal.SIG_IGN if stuck else lambda *_: sys.exit(0))
    lock = avd_folder(name) / "hardware-qemu.ini.lock" if behavior()["emulator_lock_file"] else None
    if lock:
        lock.write_bytes(str(os.getpid()).encode().ljust(8, b"\0"))
    discovery = None
    if behavior()["emulator_discovery_file"]:
        discovery = discovery_folder() / f"pid_{os.getpid()}.ini"
        discovery.parent.mkdir(parents=True, exist_ok=True)
        # The real file's keys, in its order, with fake values where the scripts don't read them.
        discovery.write_text(f"grpc.port=8{serial[-3:]}\n"
                             f'cmdline="{sys.argv[0]}" "-avd" "{name}"\n'
                             f"avd.dir={avd_folder(name)}\nemulator.version=37.1.11.0\n"
                             f"avd.name={name}\nport.adb={int(serial[9:]) + 1}\n"
                             f"port.serial={serial[9:]}\navd.id={name}\n")
    write_running(serial, {"avd": name, "pid": os.getpid(), "polls": 0,
                           "settings": dict(behavior()["device_settings"]),
                           "offline": behavior()["adb_offline"],
                           "hidden": behavior()["emulator_hidden"], "stuck": stuck,
                           "discoverable": behavior()["emulator_discoverable"],
                           "console_hung": behavior()["emulator_console_hangs"]})
    print(f"INFO         | Booted {name} as {serial} (fake)", flush=True)
    path = RUNNING / f"{serial}.json"
    deadline = time.time() + 120   # never outlive a test run, even if cleanup is skipped
    try:
        while time.time() < deadline and path.exists():
            try:
                stop_at = json.loads(path.read_text()).get("stop_at")
            except (OSError, ValueError):
                stop_at = None
            if stop_at and time.time() >= stop_at:
                path.unlink(missing_ok=True)
                break
            time.sleep(0.1)
    finally:
        if lock:
            lock.unlink(missing_ok=True)
        if discovery:
            discovery.unlink(missing_ok=True)


# --- avdmanager -----------------------------------------------------------------------------

def option(args, name):
    return args[args.index(name) + 1] if name in args else None


def avdmanager(args):
    if args[:2] == ["create", "avd"]:
        sys.stdin.read()   # the script pipes "no" to the custom-hardware-profile question
        error = behavior()["avdmanager_error"]
        if error:
            fail(error)
        name = option(args, "--name") or option(args, "-n")
        home = avdmanager_home()
        if (home / f"{name}.ini").exists():
            fail(f"Error: Android Virtual Device '{name}' already exists.")
        folder = home / f"{name}.avd"
        folder.mkdir(parents=True)
        (home / f"{name}.ini").write_text(
            f"avd.ini.encoding=UTF-8\npath={folder}\npath.rel=avd/{name}.avd\n"
            "target=android-36\n")
        # The keys the script changes are present with other values, as in a real config.ini.
        image = option(args, "--package") or option(args, "-k")
        tag = option(args, "--tag") or option(args, "-g") or "default"
        (folder / "config.ini").write_text(
            "avd.ini.encoding=UTF-8\nhw.keyboard=no\nhw.ramSize=1536\n"
            f"image.sysdir.1={image.replace(';', '/')}/\n"
            f"hw.initialOrientation=portrait\ntag.id={tag}\ntag.ids={tag}\n"
            "hw.lcd.width=1080\nhw.lcd.height=2400\nhw.lcd.density=420\n")
    elif args[:2] == ["list", "avd"]:
        print("\n".join(avd_names()))
    else:
        fail(f"fake avdmanager: unsupported arguments {args}")


# --- host commands --------------------------------------------------------------------------

def getent(args):
    if args == ["group", "kvm"]:
  # The gid decides whether the kvm group owns the device: mobile-start-emulator.sh compares it
        # with the device's own gid, and a mismatch means joining the group can't grant access.
        gid = behavior()["kvm_group_gid"]
        if gid is None:
            gid = os.stat(os.environ["AWDT_KVM_DEVICE"]).st_gid
        print(f"kvm:x:{gid}:" + ",".join(behavior()["kvm_group_members"]))
    else:
        sys.exit(2)


def android(args):
    # Presence-only: the scripts suggest "android sdk install ..." in messages but never run it.
    fail("fake android: the scripts must not run the android CLI")


def sdkmanager(args):
    fail("fake sdkmanager: the scripts must not run sdkmanager")


def javac(args):
    # javac -d <folder> ...: writes the class files of what it compiles there.
    if behavior()["javac_error"]:
        fail(behavior()["javac_error"])
    (Path(option(args, "-d")) / "Gesture.class").write_text("class")


def d8(args):
    # d8 --output <folder> <classes>: writes classes.dex there, with the version of its build-tools.
    version = Path(sys.argv[0]).resolve().parent.name
    (Path(option(args, "--output")) / "classes.dex").write_text(f"built by d8 {version}")


def sg(args):
    # sg <group> -c <command>: the real one runs the command with the group added. The fake
    # can't grant anything, so the command runs as is; tests see whether and how it was called.
    if len(args) == 3 and args[1] == "-c":
        os.execvp("bash", ["bash", "-c", args[2]])
    fail(f"fake sg: unsupported arguments {args}")


def id_(args):
    # id -un: the user's name. id -nG <user>: that user's groups from the user database, primary
    # group first (the primary group's getent line doesn't list its users).
    b = behavior()
    if args == ["-un"]:
        print(b["user"])
    elif args[:1] == ["-nG"] and len(args) == 2:
        user = args[1]
        primary = "kvm" if user == b["user"] and b["kvm_primary_group"] else user
        others = ["kvm"] if user in b["kvm_group_members"] and primary != "kvm" else []
        print(" ".join([primary, *others]))
    else:
        fail(f"fake id: unsupported arguments {args}")


def python3(args):
  # ui_tree.py runs for real: it only reads a file, and mobile-ui.sh's behavior is what it finds there.
    if args[:1] and args[0].endswith("/ui_tree.py"):
        os.execv(sys.executable, [sys.executable, *args])
  # Stands in for mobile-wslg-toolbar.py, which reports what it did on stdout.
    print("mobile-wslg-toolbar: toolbar hidden")
    sys.exit(behavior()["python3_exit"])


TOOLS = {"adb": adb, "emulator": emulator, "avdmanager": avdmanager,
         "android": android, "sdkmanager": sdkmanager,
         "getent": getent, "id": id_, "sg": sg, "python3": python3, "javac": javac, "d8": d8}


def main(tool):
    args = sys.argv[1:]
    wait_if_late(tool, args)
    log_call(tool, args)
    TOOLS[tool](args)
