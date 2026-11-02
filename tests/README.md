# tests/

Behavior tests for the commands in [`../bin/`](../bin/README.md) and what they share in
[`../lib/`](../lib/README.md). They run the real scripts and check what a user would see and what
the scripts do to the machine: exit codes, messages, the files they write, and every call they make
to `adb`, `emulator` and `avdmanager`. Python standard library only (Python 3.10+), nothing to
install.

```bash
tests/run.py                  # hermetic tier, no SDK or emulator needed
tests/run.py -k touch -v      # only tests whose name contains "touch", one line each
tests/run.py --emulator       # real-emulator tier: boots your AVD headless (see below)
tests/run.py --all            # both
tests/run.py --strict         # fail if any test was skipped (what CI runs)
```

CI ([`../.github/workflows/tests.yml`](../.github/workflows/tests.yml)) runs the hermetic tier with
`--strict` on every push to `main` and every pull request, on Python 3.10 and the newest Python.
It installs the optional tools below, so there a skip fails the run instead of hiding a test that
no longer runs; a test that needs another optional tool must have it installed in the workflow
too. The emulator tier isn't run there; run it locally before a release.

## Tiers

| Tier | Folder | Needs | Checks |
|---|---|---|---|
| hermetic | [`hermetic/`](hermetic) | Python 3; optional: Xvfb, shellcheck | Each script's behavior against fake tools and a fake machine. Run it after every script change. |
| emulator | [`emulator/`](emulator) | Your SDK and AVD (`AWDT_AVD` picks one) | What fakes can't show: see [below](#the-emulator-tier). |

Some hermetic tests skip, with the reason printed, when an optional tool is missing:
- **Xvfb** (`sudo apt-get install -y xvfb`) for the `mobile-wslg-toolbar.py` tests, which create
  emulator-like windows on a private X server. It runs on the first free display from `:99` up,
  reachable only through an abstract socket: under WSLg `/tmp/.X11-unix` is read-only, and a low
  display number would capture the desktop's own apps. It runs with `-noreset`: each test's windows
  live on their own connection, so between two tests the server has no clients; by default it resets
  then, and the next test's connection can fail while it does, more often the busier the machine.
  `SCRIPT_TESTS_DISPLAY=:0` runs the tests on an existing display instead; under WSLg you'll see
  small windows flash. Only use it to watch, with no Linux GUI app open that you'd mind losing:
  WSLg's compositor can crash during such a run, which closes every Linux GUI app and breaks the
  tests' X connections.
- **shellcheck** (`sudo apt-get install -y shellcheck`)
  for static analysis of the shell scripts.

## The emulator tier

It covers what only a real device shows, by what reaches an app: it installs
[`emulator/TouchProbe.apk`](emulator/probe), which logs each touch it gets, what Android's own
gesture detectors made of them, and how far two fingers moved; and removes it afterwards.

- **Booting:** the boot completes, `--wait-for-home` returns with the home app in front, and no app
  was reported as not responding meanwhile.
- **Gestures:** each one lands where it was asked for and is recognized as what it is, percentages
  included, on a screen as it's turned.
- **The screen:** `mobile-ui.sh` lists, finds, taps, types, waits and takes screenshots on a real
  screen.
- **The mouse:** the real emulator window on a private X server, with real pointer events (XTest,
  which WSLg's own display ignores), so a click, a held button and a drag are checked as touches.
  That covers everything from the X server on, not WSLg's own way to it, which needs a real mouse.
- **Stopping:** `mobile-stop-emulator.sh` returns only once the AVD can start again, also for a
  `-read-only` emulator, which writes no lock file, a frozen one, and one that's exiting already.

The tier reuses the AVD if it's already running and leaves it running. Otherwise it boots it (cold)
with `--wait-for-home -no-window -no-snapshot-save`, and stops it at the end. The tests that need
the AVD to themselves skip when it was already running. `AWDT_TEST_EMULATOR_FLAGS` adds emulator
flags to the boots it makes. It tests one AVD per run; to cover every [tested
image](../docs/EMULATORS.md#tested-images), one emulator at a time:

```bash
for l in 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37; do
    mobile-create-avd.sh --api $l --if-missing
    AWDT_AVD=phone_api$l tests/run.py --emulator
done
```

Its time limits hold for an emulator starved of CPU: a wait ends as soon as what it waits for is
there, so a long limit only makes a failure slower. Its limits for `mobile-start-emulator.sh` and
`mobile-stop-emulator.sh` are longer than the scripts' own, computed from them
([`test_conventions.py`](hermetic/test_conventions.py) checks the copies): a script always gets to
its own limit, stops what it started and says why, whereas Python stopping
`mobile-start-emulator.sh` would leave its emulator booting. An emulator the tier boots is stopped
at the end even when its boot failed.

## Layout

| Path | Contents |
|---|---|
| [`run.py`](run.py) | Entry point: picks the tiers, filters, prints skip reasons. |
| [`support/sandbox.py`](support/sandbox.py) | `Sandbox`: a throwaway machine per test. `ScriptTestCase`: the base class. |
| [`support/fake_tools.py`](support/fake_tools.py) | Fakes for `adb`, `emulator`, `avdmanager`, `android`, `sdkmanager`, `python3`, `getent`, `id`, `sg`, `javac` and `d8`. |
| [`support/screens.py`](support/screens.py) | Made-up screens as `uiautomator dump` writes them. |
| [`support/front_look.py`](support/front_look.py) | `front_look`: `home_look` from [`../lib/home.sh`](../lib/home.sh) for another activity than the home app's. |
| [`support/x11.py`](support/x11.py) | Private Xvfb server, `Pointer` (real pointer events into a window, for the emulator tier), fake emulator windows (the main window, the toolbar, and the hidden bar also titled "Emulator"; Xvfb has no window manager, so `raise_()` puts a window on top as one would when it maps it, and `set_wm_state()` and `set_frame_extents()` set `WM_STATE` and `_NET_FRAME_EXTENTS` as one would), and `WindowChurn`, a client that keeps opening and closing windows. |
| [`emulator/`](emulator) | The real-emulator tier, and [`probe/`](emulator/probe), the source of its app. |

## How the hermetic tier works

Each test gets a `Sandbox` (`self.sandbox`), a temporary folder with:
- a copy of `bin/` and `lib/`, and a separate project folder the scripts run in, so a real
  `local.properties` can't leak in;
- its own `$HOME`, `$TMPDIR`, `$XDG_RUNTIME_DIR` and a `$PATH` with only basic utilities plus
  fakes, so the host's SDK, AVDs, emulators, kvm group and WSL don't change the results;
- a fake KVM device and `/proc/version`, passed to the scripts through `AWDT_KVM_DEVICE` and
  `AWDT_PROC_VERSION` (read in [`lib/sdk.sh`](../lib/sdk.sh) for this purpose only).

The fakes behave like the real tools as far as the scripts can see: same output formats (including
the `\r` adb adds), exit codes and side effects. For example, the fake emulator registers on the
first free port, writes its PID into its AVD's `hardware-qemu.ini.lock` as the real one does, and
stays alive until `adb emu kill`. The fake `adb push` puts a file on the fake device, where the
gesture program's `[ -f <path> ]` then finds it; the program records its arguments on the device;
`uiautomator dump` writes a made-up hierarchy to the device's files, for `adb exec-out cat`. The
fake `python3` runs `lib/ui_tree.py` for real, and stands in for `mobile-wslg-toolbar.py`. All fakes
share state in the sandbox, so a test can arrange a situation and then check the result:

```python
class Example(ScriptTestCase):
    def test_boots_its_own_avd_next_to_another_emulator(self):
        self.sandbox.install_sdk()                        # fake SDK in ~/Android/Sdk
        self.sandbox.add_avd("phone_api36")               # AVDs, as avdmanager lays them out
        self.sandbox.add_avd("tablet")
        self.sandbox.start_emulator("tablet")             # already running, takes emulator-5554
        result = self.sandbox.run("mobile-start-emulator.sh")  # the real script
        self.assertSucceeded(result)
        self.assertIn("booted as emulator-5556", result.err)
        self.assertEqual(self.sandbox.running(), {"emulator-5554": "tablet", "emulator-5556": "phone_api36"})
```

`sandbox.run(script, how=…, cwd=…)` calls a script the way a user would: by its absolute path
(the default), by a path relative to `cwd`, by its bare name with `bin/` on `PATH`, or through
symlinks in `~/.local/bin`. `cwd` defaults to the project folder. Behavior that depends on how a
script was called (finding `lib/`, suggested commands) is tested every way. `sandbox.bash(snippet)`
runs a snippet with every library sourced, for what `lib/` offers the scripts.

Arrange failures and odd situations with `sandbox.set_behavior(...)`: `DEFAULT_BEHAVIOR` in
[`support/fake_tools.py`](support/fake_tools.py) lists every knob and what it does. Where a knob
makes a script wait, an environment variable shortens the wait:

| Situation | Knobs | Script's environment |
|---|---|---|
| What's in front over time | `front`, `home_resolves`, `user_unlocked`, `home_activities` | `AWDT_BACK_AFTER`, `AWDT_OTHER_APP_TIMEOUT`, `AWDT_HOME_TIMEOUT` |
| An emulator adb can't reach | `adb_offline` | `AWDT_OFFLINE_TIMEOUT` |
| A boot that doesn't end | `boot_polls`, `emulator_hidden`, `adb_hangs` | `AWDT_BOOT_TIMEOUT`, `AWDT_ADB_TIMEOUT`, `AWDT_PROGRESS_INTERVAL` |
| An emulator that won't exit | `emulator_stuck`, `emulator_console_hangs`, `emulator_already_exiting`, `adb_lists_exited` | `AWDT_STOP_TIMEOUT` |
| Android's own write of the app states | `api_level` 33 or more, `pending_package_write`, `earlier_package_write`, `sync_error` | `AWDT_SAVE_WAIT` |
| A gesture | `gesture_output`, `push_error`, `screen_size`, `screen_turned`, `device_settings` | |
| The screen | `ui_hierarchy`, `ui_idle_failures`, `screenshot` | `AWDT_UI_TIMEOUT` |

Also arrange `connect_device()` (a physical device), `wsl()`, and file permissions on `sandbox.kvm`.
Check the results with `result.code/out/err`, `sandbox.calls()`/`argvs(tool)` (each call has the
`time` it was made), `sandbox.running()`, `sandbox.device_state(serial)` and the files in
`sandbox.home`; `sandbox.emulator_pid(serial)` and `sandbox.alive(pid)` show whether an emulator's
process has exited (a zombie has: fake emulators are the test's children, so a killed one stays a
zombie until the cleanup reaps it).

## Writing tests

- **Test behavior, not lines.** Name each test after what a user relies on
  (`test_refuses_to_guess_between_several_phone_avds`) and assert on observable results. Don't
  source a script to call its internals. `lib/`'s functions are the exception, because they are its
  interface.
- **Every bug fix and every new option gets a test** in the script's `test_<script>.py`, named
  without the `mobile-` prefix. A new script gets a new file; `test_conventions.py` already makes it provide `--help`, a shebang, and
  a line in [`../bin/README.md`](../bin/README.md).
- **Stay hermetic.** A hermetic test never reads the real `$HOME`, SDK or devices. If a script
  needs a new external command, add a fake to `fake_tools.py` (or the command to `UTILITIES` in
  `sandbox.py` if it's a basic system utility).
- **Wait for a condition, not for a time.** On a busy machine a script gets everywhere several times
  later, so a test never sleeps on a fixed timer when it can wait for a condition with
  `self.wait_until(condition)`. To stop an emulator while `mobile-start-emulator.sh` waits for its
  boot, for example, start the script with `start_in_background()`
  ([`test_start_emulator.py`](hermetic/test_start_emulator.py)) and wait until the calls show its
  boot polls. To act while `mobile-wslg-toolbar.py show` has unmapped the toolbar, play the window
  manager (`EmulatorWindows.set_wm_state()`): the script goes on only once the test has set the
  toolbar's `WM_STATE` to Withdrawn. A time limit a test sets (`AWDT_BOOT_TIMEOUT=2`) must only end
  what never finishes by design, not race what the script does on the way, and a check on how long a
  script took belongs only where its output can't show which way it went. The scripts' own limits
  count whole seconds (`$SECONDS`, through `time_is_up` in [`lib/device.sh`](../lib/device.sh)), so
  where a test checks that one lasts its full length, it makes the script start it late in a second
  (`adb_late`) and measures between the calls' times. `$SECONDS` follows the wall clock, which WSL
  can step forward, so such a check measures with `time.time()`, never `time.monotonic()`. To try a
  test on a busy machine, share one CPU with busy loops:
  ```bash
  for i in $(seq 29); do timeout 600 taskset -c 0 bash -c 'while :; do :; done' & done
  taskset -c 0 tests/run.py -k <test>; kill $(jobs -p)
  ```
- **Check that a new test can fail.** Break the behavior on purpose, see the test fail, then restore
  it.
- Anything that needs the real emulator goes in `emulator/`, and must leave the developer's
  emulator as it found it.
