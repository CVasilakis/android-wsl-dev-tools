# Troubleshooting

From a symptom or a message to its cause. The tables list what has been seen, by where it shows up;
the guides they link to explain the background.

## Setup

- **`emulator: ERROR: x86 emulation currently requires hardware acceleration`** or
  **`No access to /dev/kvm`**: not in the `kvm` group yet, or the device belongs to another
  group, or `/dev/kvm` doesn't exist (nested virtualization is off for WSL). See
  [Make `/dev/kvm` writable](SETUP.md#make-devkvm-writable).
- **`error while loading shared libraries: lib….so`** when the emulator starts: a system library is
  missing; install the packages of [step 1](SETUP.md#1-system-packages-and-kvm-access-needs-sudo).
- **`JAVA_HOME is set to an invalid directory`** from `avdmanager` or Gradle: `JAVA_HOME` names a
  JDK that isn't installed ([step 3](SETUP.md#3-environment-variables-and-the-android-cli)).
- **`sudo: a terminal is required to read the password`**: run the command in a regular terminal
  ([step 1](SETUP.md#1-system-packages-and-kvm-access-needs-sudo)).
- **`Error: "emulator" package must be installed!`** from `mobile-create-avd.sh`: [step
  4](SETUP.md#4-sdk-packages) is missing.
- **`Package … not found.`** from `android sdk install`, and the setup carries on regardless: a
  typo in a package id. The command exits 0 anyway, so check with `android sdk list --no-metrics`
  ([The `android` CLI](SETUP.md#the-android-cli)).
- **`android sdk install` or `android sdk list` sits there without a word**, while a
  `repo-index…tmp.part` in `/tmp` stays at 0 bytes: the host has an IPv6 address, but IPv6 doesn't
  reach Google (seen under WSL's mirrored networking), and the `android` CLI waits on it without
  falling back to IPv4 as `curl` does. `curl -6 -sI -m 10 https://dl.google.com/` timing out while
  `curl -4 …` answers confirms it. Install with `sdkmanager --install "<package>"…` (in
  `cmdline-tools/latest/bin`) instead: up to cmdline-tools 22.0 it's a Java program of its own,
  which uses IPv4. From 23.0 on it runs the `android` CLI ([The `android`
  CLI](SETUP.md#the-android-cli)), so there the fix is the host's network.
- **`WARNING: The SDK Manager CLI tool (sdkmanager) is deprecated`**: use `android sdk` instead;
  the table in [The `android` CLI](SETUP.md#the-android-cli) maps the old commands to the new ones.
- **`SDK location not found`** during a build, although `echo $ANDROID_HOME` works in your terminal:
  the build ran in a non-interactive shell that skipped the exports at the end of `~/.bashrc` ([step
  3](SETUP.md#3-environment-variables-and-the-android-cli)), or in one that reads no startup file.
  Move the block above the interactive check, and create `local.properties` ([step
  7](SETUP.md#7-use-it-from-a-project)).
- **Build fails with an error about `javac` or `jlink`**: only a JRE is installed ([step
  1](SETUP.md#1-system-packages-and-kvm-access-needs-sudo)).

## Creating an AVD

| Symptom | Cause / fix |
|---|---|
| `mobile-create-avd.sh: AVD '<name>' already exists` | it never overwrites one; `--if-missing` accepts it when it's from the same system image ([`EMULATORS.md`](EMULATORS.md#creating-one)) |
| `Error: Could not load devices from …/devices.xml` | harmless, the AVD is created correctly ([`EMULATORS.md`](EMULATORS.md#creating-one)) |
| `avdmanager failed: the system image isn't installed` | install it with the command the message prints |
| `'avdmanager' not found` (or `emulator`, `platform-tools`) | the SDK wasn't found, or lacks that package: set `ANDROID_HOME` ([Finding your setup](../bin/README.md#finding-your-setup)) |

## Booting

| Symptom | Cause / fix |
|---|---|
| "System UI isn't responding" over the home screen right after a boot, on an AVD of your own | it renders with `swiftshader_indirect`, which misses System UI's startup limit on API 36 and 37: boot it with `-gpu swangle_indirect`, the default here. The dialog itself stays until tapped: `mobile-ui.sh tap Wait` |
| `mobile-start-emulator.sh: the emulator exited with status …` | the printed log lines say why (e.g. an unknown flag); full log in `${TMPDIR:-/tmp}/emulator-<name>.log` |
| `mobile-start-emulator.sh: the emulator exited, killed by signal 11 (SIGSEGV)` | the emulator crashed; the log usually doesn't say why. Try another renderer: `mobile-start-emulator.sh <avd> -gpu swiftshader_indirect` |
| `mobile-start-emulator.sh: '<avd>' didn't finish booting within 900 s` | the host is slow: raise `AWDT_BOOT_TIMEOUT`; or Android can't boot: without `--quick` if you used it, else try `-wipe-data` (factory reset) |
| `mobile-start-emulator.sh: '<avd>' didn't finish booting …` with a window, on API 23, after a new AVD's first boot was stopped with `--no-save` | [the hang on API 23](EMULATORS.md#what-the-images-do-on-their-own): the next boot works |
| `mobile-start-emulator.sh: '<avd>' booted, but its home app wasn't in front with the focus within 600 s` (with `--wait-for-home`) | the next line says what was in front: nothing focused (a host short of CPU: raise `AWDT_HOME_TIMEOUT`), another app (on an emulator that had booted before: press Home, or leave out the flag), or a screen that two Backs didn't close |
| `mobile-start-emulator.sh: '<avd>' booted, but no home app is enabled` (with `--wait-for-home`, API 24 on) | every home app is disabled: `adb shell pm list packages -d` lists the disabled apps, `adb shell pm enable <package>` enables one |
| `mobile-start-emulator.sh: … was stopped before it finished booting` | the AVD was already running and booting (another call started it), and was stopped while this one waited; start it again |
| `mobile-start-emulator.sh: … adb can't reach it` (with `--quick`) | the restored snapshot left adb offline: `mobile-stop-emulator.sh <serial>`, then start it without `--quick` |
| `can't tell which AVD to use` / `there's no AVD named …` | pass the AVD name or set `AWDT_AVD`; the message lists the AVDs found |
| Black emulator window | if started with `--quick`, start it without |
| The emulator dies in a long series of app starts, the host out of memory (`page allocation failure` in `dmesg`, swap full) | its `qemu-system-…` process grows with every cold start of an app, and gives nothing back while it runs: stop it and start it again between batches of starts |

## Apps

| Symptom | Cause / fix |
|---|---|
| An app with an OpenGL ES view crashes as it starts: `FATAL EXCEPTION: GLThread` and `IllegalArgumentException` in `eglCreateContext` (`adb logcat -b crash`) | its EGL config chooser accepts none of the default renderer's configurations, e.g. it insists on RGB 565: boot with `-gpu swiftshader_indirect` ([the renderer](EMULATORS.md#the-renderer)) |

## Stopping

| Symptom | Cause / fix |
|---|---|
| `Android logged no write of app states on … within 12 s` | from API 33 on: nothing was pending, or Android is late with its write, so an app enabled or disabled since its last write may be lost; on a host short of CPU, raise `AWDT_SAVE_WAIT` ([`EMULATORS.md`](EMULATORS.md#stopping-one)) |
| `… It's still running.` | the emulator couldn't be stopped, or, without its PID, adb still listed it after `AWDT_STOP_TIMEOUT` seconds ([`EMULATORS.md`](EMULATORS.md#stopping-one)); kill its `qemu-system-…` process by the PID in the `pid_<PID>.ini` that `adb -s <serial> emu avd discoverypath` names, or reboot WSL (`wsl --shutdown` in Windows) |
| `adb devices` shows `offline` or `unauthorized` | `adb reconnect offline`; if that doesn't help, `adb kill-server && adb start-server`; else stop the emulator and cold boot it |

## Touch, the screen and the sensors

| Symptom | Cause / fix |
|---|---|
| A tap does nothing, and `mobile-touch.sh` exits 0 | a touch goes to the window under it: a dialog may be in front (`mobile-ui.sh front`, `mobile-ui.sh shot`) |
| `mobile-touch.sh: the gesture failed on …` | the program's last lines of output follow; usually the device is gone, offline or still booting: `adb devices` |
| `several emulators are running` | name one with `-s <serial>`, or set `ANDROID_SERIAL` |
| `adb: more than one device/emulator` | `export ANDROID_SERIAL=<serial>` (printed by `mobile-start-emulator.sh`) |
| `mobile-ui.sh: couldn't read the screen of …` | the screen kept animating for `AWDT_UI_TIMEOUT` seconds (a looping animation never goes idle: raise it, or use a screenshot), or the device is gone |
| `mobile-sensor.sh: … is not an emulator` | only an emulator's sensors can be set: a phone's are its own. Name an emulator with `-s <serial>` |
| `mobile-sensor.sh: the console of … refused …` | its answer follows: `unknown sensor name` or `sensor is disabled` (`mobile-sensor.sh status` lists the ones there are), or adb's own error, e.g. a device that's gone |
| `mobile-sensor.sh: … takes 3 values, not …` | `set` gives a sensor all its values: as many as `mobile-sensor.sh get <sensor>` shows |
| An app doesn't follow `mobile-sensor.sh tilt`, or follows it in jumps | it may read a sensor Android works out itself, such as gravity or a rotation vector, which lags behind, or one the image doesn't have; on API 21 and 30 new values reach apps every 0.8 s only ([what apps get](DRIVING.md#sensors)) |
| `mobile-ui.sh: no element matches …` | `mobile-ui.sh list` shows what's there; the app's view may be invisible to uiautomator ([`DRIVING.md`](DRIVING.md#seeing-the-screen)) |

## The window under WSLg

| Symptom | Cause / fix |
|---|---|
| No side toolbar | hidden on purpose ([`WSLG.md`](WSLG.md)) |
| Typed keys move focus between toolbar buttons | the toolbar is shown: `mobile-wslg-toolbar.py hide` |
| Toolbar buttons ignore clicks | `mobile-wslg-toolbar.py show` |
| `mobile-wslg-toolbar: no toolbar window found` | wrong AVD name or emulator not running; inspect with `xwininfo -root -tree \| grep qemu-system` |
| `mobile-wslg-toolbar: no running emulator window found` | emulator not running, or started with `-no-window` |
| `mobile-wslg-toolbar: several windows look like the toolbar` | an emulator version with another tall window titled "Emulator": compare them with `xwininfo -root -tree \| grep qemu-system` and update the script's search |
| `mobile-wslg-toolbar.py`: `X Error of failed request: BadWindow` | the emulator's toolbar or window closed while the script changed it: run it again once the emulator is up |
| The emulator's window opens behind your Windows apps | bring it forward from the taskbar: Windows decides which app is in front, so the scripts can't |
