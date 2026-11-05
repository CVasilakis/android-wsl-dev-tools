# bin/

The commands, and nothing else: users may put this folder on their `PATH`
([how](../README.md#optional-put-the-commands-on-your-path)), so what they share lives in
[`../lib/`](../lib/README.md). Commands are shown by name; without `PATH` set up, call them by their
path, e.g. `../android-wsl-dev-tools/bin/mobile-start-emulator.sh`.

| Command | Purpose | Guide |
|---|---|---|
| [`mobile-create-avd.sh`](mobile-create-avd.sh) | Creates a phone or tablet emulator with the right settings. | [`EMULATORS.md`](../docs/EMULATORS.md#creating-one) |
| [`mobile-start-emulator.sh`](mobile-start-emulator.sh) | Boots it, and returns once Android is ready (with `--wait-for-home`, once its home screen has settled). | [`EMULATORS.md`](../docs/EMULATORS.md#booting-one) |
| [`mobile-stop-emulator.sh`](mobile-stop-emulator.sh) | Has Android save its recent changes, stops it, and returns once it has exited. | [`EMULATORS.md`](../docs/EMULATORS.md#stopping-one) |
| [`mobile-touch.sh`](mobile-touch.sh) | Touches the screen: taps, long presses, swipes, drags, two-finger pinches and rotations. | [`DRIVING.md`](../docs/DRIVING.md#touch) |
| [`mobile-ui.sh`](mobile-ui.sh) | Sees what's on the screen, and acts on it by what it says. | [`DRIVING.md`](../docs/DRIVING.md#seeing-the-screen) |
| [`mobile-sensor.sh`](mobile-sensor.sh) | Sets an emulator's sensors: tilts it, at once or smoothly, or gives any sensor values of its own. | [`DRIVING.md`](../docs/DRIVING.md#sensors) |
| [`mobile-wslg-toolbar.py`](mobile-wslg-toolbar.py) | Hides or shows the emulator's side toolbar, which misbehaves under WSLg. | [`WSLG.md`](../docs/WSLG.md) |

Each one prints its usage with `--help`, and has a header comment with its usage, common errors and
the reasons behind its less obvious lines.

## Finding your setup

Nothing about the SDK, AVD or device is hardcoded; each is taken from the first match below.

| What | Where from |
|---|---|
| Android SDK | `$ANDROID_HOME`, `$ANDROID_SDK_ROOT`, `sdk.dir` in the `local.properties` of the project you're in (the nearest one in the current folder or above it, as Gradle does), the SDK of the `adb` on `$PATH`, `~/Android/Sdk` |
| `adb`, `emulator`, `avdmanager`, `android` | inside that SDK (`cmdline-tools/latest`, else the newest `cmdline-tools/<version>`), else on `$PATH` |
| AVD folder | `$ANDROID_AVD_HOME`, `$ANDROID_EMULATOR_HOME/avd`, `$ANDROID_USER_HOME/avd`, `$ANDROID_SDK_HOME/.android/avd`, `~/.android/avd`; each AVD is located through its `<name>.ini` |
| AVD to create or boot | the name given on the command line, `$AWDT_AVD`, `phone_api36`; `mobile-start-emulator.sh` then also accepts the only phone or tablet AVD |
| Emulator to talk to | `mobile-touch.sh` and `mobile-ui.sh`: the serial given with `-s` (any device), `$ANDROID_SERIAL`, or the only running emulator. `mobile-sensor.sh`: the same, but only an emulator. `mobile-stop-emulator.sh`: the AVD name or serial given, `$ANDROID_SERIAL`, or the only running emulator, never a physical device. `mobile-start-emulator.sh` matches running emulators by AVD name. `mobile-wslg-toolbar.py`: the AVD given, or the only emulator window |

`local.properties` is the only thing the commands read from the folder they're called from. To use
your own AVD without typing its name each time: `export AWDT_AVD=<name>`.
