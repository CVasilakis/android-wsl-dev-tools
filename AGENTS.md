# AGENTS.md

Guidance for AI coding agents (and humans) working on this repository.

## Project in one paragraph

android-wsl-dev-tools: command-line tools for developing Android phone and tablet apps without
Android Studio, on Ubuntu under WSL2. Bash scripts plus a little Python (standard library only) and
one small program that runs on the device: they create and boot emulators, touch their screens, and
read what's on them. They're used from other repositories' projects, called by a relative path or
through `PATH`, so they must never depend on the current folder or on any particular app. Start
with [`README.md`](README.md), then [`docs/README.md`](docs/README.md), the map of everything else.

## Commands

```bash
tests/run.py                  # hermetic tests, no SDK or emulator needed
tests/run.py -k touch -v      # a subset, one line per test
tests/run.py --strict         # fail on any skipped test, as CI does
tests/run.py --emulator       # real-emulator tier: boots your AVD headless
```

The commands themselves are in [`bin/README.md`](bin/README.md).

## Rules

- **Location-independent.** Scripts find `lib/` and each other through `readlink -f
  "$0"`/`$BIN_DIR`, never through the current folder or `$PATH`. The only thing read from the
  current folder is the project's `local.properties`. Messages that suggest another command use
  `command_for <script>`.
- **`lib/Gesture.dex` is built from `lib/Gesture.java`** by `lib/build-gesture.sh`, and
  `tests/emulator/TouchProbe.apk` from `tests/emulator/probe/` by its `build.sh`: rebuild and commit
  both sides whenever the source changes.
- **Every command starts with `mobile-`**, so it can share `PATH` with the sibling Android TV tools,
  whose commands start with `tv-`, and a plain name never means one or the other.
- **`bin/` holds only commands**: users may put it on `PATH`. What they share goes in `lib/`, one
  job per file ([`lib/README.md`](lib/README.md)); a script sources only what it needs.
- **Scope** ([`README.md`](README.md#scope)): phone and tablet apps, on Ubuntu under WSL2. Don't
  claim support for a distribution, image or API level that hasn't been tested, and update
  [Tested images](docs/EMULATORS.md#tested-images) when that changes.
- **App-agnostic.** No app names, package names or project paths in scripts or docs. Environment
  variables of these tools start with `AWDT_`, so that they can't reach the sibling Android TV
  tools, whose variables start with `ADT_`.
- **Every script change or new option gets a test**; a bug fix starts with a failing test. How to
  write them: [`tests/README.md`](tests/README.md#writing-tests).
- **No dependencies**: bash, coreutils and the Python standard library (3.10+) only. New tools
  (even test-only) need the user's agreement.
- **Before a release, run the emulator tier locally** on every tested image
  ([`tests/README.md`](tests/README.md)): CI runs only the hermetic tier.
- **The docs follow [their own rules](docs/README.md#writing-the-docs)**: each fact in one document,
  a parent names its children and doesn't repeat them, the current state and not history, no
  machine-specific measurements, paths with `~`. This file: rules for changes, and pointers.
- **The public interface is versioned** ([`README.md`](README.md#versions)). Breaking it needs the
  user's agreement and means a new major version; when you report a change, say whether it breaks,
  extends or only fixes that interface, for the release notes. Only the user creates tags and
  releases.
- Downloads are large ([`docs/SETUP.md`](docs/SETUP.md#sizes)). Ask before triggering big SDK
  downloads.
- `sudo` needs a password and there's no terminal to type it into, so ask the user to run sudo
  commands themselves in a regular terminal.
- **One emulator at a time** on a small host, and nothing else heavy beside it. A command that waits
  must end on its own: start any wait loop with `timeout <seconds>`, never wait on `pgrep -f` or
  `pkill -f` ([why](docs/EMULATORS.md#stopping-one)).
- **The user's desktop:** don't run anything that opens and closes many windows on the real display
  ([`docs/WSLG.md`](docs/WSLG.md#what-scripts-cant-do-there)). Boot emulators for tests with
  `-no-window`.

## Commit messages

Agents commit only when the user says so. Read recent history (`git log`) first and match its style
and level of detail.

- **Subject: the outcome, not the activity** ("classify lock storage failures as storage errors",
  not "update locking code"). Use a conventional prefix (`fix(locking): …`) only if recent
  history does.
- **Body: understandable without the diff.** Say what changed, why, which module or layer owns
  it, and which behavior was deliberately kept (invariants, compatibility). Explain non-obvious
  decisions, such as why a port or boundary was added or why responsibilities stay in separate
  layers.
- Describe behavior, not file inventories, symbol lists or the order things were implemented in.
- Left-aligned `-` bullets, one purpose each; don't repeat the subject or another bullet.
- No filler, promotional wording or vague phrases ("improve robustness", "various fixes")
  unless the concrete behavior follows right away.
- Mention tests only if they ran, with the exact passing count when known. Never claim a run
  passed if it failed or didn't run.
- No trailers or sign-offs of any kind (`Co-Authored-By`, "Generated with …", …).
- Make it detailed enough to keep the design intent, and no longer than that.

## Things that look removable but aren't

Each of these fixes a real problem. The reasons are in the linked file; read them before changing
anything.

| What | Where | Why |
|---|---|---|
| `GPU_MODE=swangle_indirect` rather than the emulator's usual `swiftshader_indirect` | `lib/sdk.sh` | With `swiftshader_indirect`, every cold boot on API 36 and 37 ended with "System UI isn't responding" over the home screen, which takes every touch until tapped ([`docs/EMULATORS.md`](docs/EMULATORS.md#the-renderer)). |
| Playing gestures with our own program rather than `adb shell input`; touches sent with the device's touchscreen as their device | `bin/mobile-touch.sh`, `lib/Gesture.java` | [`docs/DRIVING.md`](docs/DRIVING.md#touch). |
| The dex's name holding its checksum | `bin/mobile-touch.sh` | A changed program must reach a device that holds the old one. |
| Success read from the output, not `adb shell`'s exit status | `bin/mobile-touch.sh`, `bin/mobile-ui.sh` | Before API 24 `adb shell` always exits 0. |
| `read_screen` asking `ui_tree.py` whether a dump parses, not only whether one came | `bin/mobile-ui.sh` | A dump cut short made `wait-gone` report that the element was gone. |
| `grep … > /dev/null`, not `grep -q`, after a pipe from adb | `bin/mobile-ui.sh`, `bin/mobile-start-emulator.sh` | `grep -q` stops reading, and under `pipefail` that can fail a good look. |
| `readlink -f` when sourcing `lib/` and in `TOOLS_DIR` | `bin/*.sh`, `lib/sdk.sh` | Scripts called through a symlink on `PATH` must still find the repository. |
| AVD settings (`hw.keyboard`, `disk.dataPartition.size`, …) | `bin/mobile-create-avd.sh` | Each one's comment. |
| `image_level`, `image_abi` | `lib/avd.sh` | Their comments: an image's folder isn't always `android-<level>/…/x86_64`. |
| `sg kvm` re-exec (by the real path), waiting for `sys.boot_completed` | `bin/mobile-start-emulator.sh` | KVM access without restarting WSL; installing too early fails. |
| Comparing `/dev/kvm`'s gid with the `kvm` group's | `bin/mobile-start-emulator.sh` | On WSL the device often belongs to no group, and then `usermod -aG kvm` can never help. |
| Cold boot by default, the offline watchdog only with `--quick` | `bin/mobile-start-emulator.sh` | A restored snapshot can leave adb `offline` for good; a cold boot is offline for a while normally. |
| Only the serial on stdout, every message on stderr | `bin/mobile-start-emulator.sh` | Scripts and CI capture the serial with `serial="$(mobile-start-emulator.sh)"`; it's part of the public interface. |
| `-no-window` added when `$DISPLAY` is empty | `bin/mobile-start-emulator.sh` | Without a display the emulator aborts, and its log doesn't say why. |
| `is_handheld_avd` | `bin/mobile-start-emulator.sh` | The AVD folder is shared with TV and other emulators. |
| `install_hint`'s fallback to `sdkmanager` | `lib/sdk.sh` | `android` only ships from cmdline-tools 22.0. |
| Toolbar hidden by default under WSL; everything in `bin/mobile-wslg-toolbar.py` | `bin/mobile-start-emulator.sh`, `bin/mobile-wslg-toolbar.py` | The script's docstring, [`docs/WSLG.md`](docs/WSLG.md). |
| The PID from the console, else from the discovery files, else from `hardware-qemu.ini.lock`, each checked against the process's command line, instead of `pgrep` | `bin/mobile-stop-emulator.sh` | Its header: `pgrep -f` also matches the shell running it, and a hung console names nothing. |
| `time_is_up` instead of comparing `$SECONDS` with a limit | `lib/device.sh`, `bin/*.sh` | `$SECONDS` counts whole seconds, so a direct comparison can end a limit up to a second early. |
| `id -nG "$(id -un)"` for kvm membership, not `$USER` or the `getent` line | `bin/mobile-start-emulator.sh` | Counts kvm as a primary group, doesn't mistake `ci` for `ci-bot`, and works where `$USER` is unset. |
| Everything `wait_for_home` checks | `lib/home.sh` | Its comment: a look can catch a state that's gone a moment later. |
| Before `adb emu kill`, `dumpsys package write` or the wait for Android's own write, then `sync` | `bin/mobile-stop-emulator.sh` | `adb emu kill` doesn't shut Android down ([`docs/EMULATORS.md`](docs/EMULATORS.md#stopping-one)). |
| Xvfb's `-noreset` | `tests/support/x11.py` | Without it the server resets between two tests, and the next test's connection fails under load. |
| The emulator tier's limits for the scripts computed from the scripts' own; the class cleanup that stops its emulator, registered before the boot | `tests/emulator/test_on_emulator.py` | A script Python stops on the way can't stop the emulator it started, and `tearDownClass` isn't called when `setUpClass` fails. |
| `AWDT_KVM_DEVICE`, `AWDT_PROC_VERSION`, `WSLG_TOOLBAR_TIMEOUT`, `AWDT_OFFLINE_TIMEOUT`, `AWDT_PROGRESS_INTERVAL`, `AWDT_ADB_TIMEOUT`, `AWDT_BACK_AFTER` | `lib/`, `bin/` | Let the tests simulate other machines and not wait 30 or 60 s ([`tests/README.md`](tests/README.md)). |

## Emulator facts that save time

Read these before driving an emulator:

- [Touch](docs/DRIVING.md#touch) and [seeing the screen](docs/DRIVING.md#seeing-the-screen):
  gestures and elements from a script. Host-level input (xdotool) doesn't reach the emulator under
  WSLg.
- [What each image does on its own](docs/EMULATORS.md#what-the-images-do-on-their-own): what differs
  between API levels.
- [What an emulator can't do](docs/EMULATORS.md#what-an-emulator-cant-do): when only a real phone
  will tell.
