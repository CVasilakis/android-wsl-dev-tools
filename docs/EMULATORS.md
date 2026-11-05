# Emulators

Creating emulators, booting and stopping them, and what each image does on its own. What to install
first: [`SETUP.md`](SETUP.md). Using a running one: [`DRIVING.md`](DRIVING.md).

## Tested images

The [emulator tier](../tests/README.md#the-emulator-tier) passes on each of these:

- **Plain (AOSP) x86_64 images: API 21 to 37**, every level, as `phone_api<level>`.
- **Google APIs images: API 21 to 37, and 36.1**, every level, x86_64 except API 27's, which is x86,
  as `phone_gapi<level>`.
- **Tablets:** `tablet_api30` and `tablet_api36`, from the plain images.

`mobile-sensor.sh`, and the tier's tests of it, so far only on the plain images of API 21, 30 and
36 ([what each one's apps get](DRIVING.md#sensors)).

A foldable (`pixel_9_pro_fold`, API 36) boots and lists its folded states, but the tier hasn't run
on one. Untested: the Google Play images (`google_apis_playstore`), which have no root; the 16 KB
page size images; and any level below 21.

## Creating one

`mobile-create-avd.sh [--api <level>] [--google-apis] [--tablet] [--device <profile>] [--size
<W>x<H>] [--density <dpi>] [--if-missing] [name]`

```bash
mobile-create-avd.sh                 # phone_api36: Android 16
mobile-create-avd.sh --api 24        # phone_api24: Android 7.0
mobile-create-avd.sh --api 37        # phone_api37: Android 17
mobile-create-avd.sh --api 30 my_phone  # the same image under another name
mobile-create-avd.sh --tablet --api 34  # tablet_api34: a tablet on Android 14
mobile-create-avd.sh --google-apis --api 34  # phone_gapi34: with Google Play services
mobile-create-avd.sh --device pixel_9_pro_fold --api 36  # pixel_9_pro_fold_api36: any device profile
mobile-create-avd.sh --size 720x1280 --density 320 small_phone  # another screen
```

It creates the AVD from the image of that level, `system-images;android-<level>;default;x86_64`
(`google_apis` with `--google-apis`), which must be installed first
([`SETUP.md`](SETUP.md#5-the-system-image); the script prints the install command if it's missing),
with the `medium_phone` device profile (`medium_tablet` with `--tablet`), then sets in the AVD's
`config.ini` what avdmanager has no flags for:

| Setting | Value | Why |
|---|---|---|
| `hw.keyboard` | yes | the PC's keyboard types into fields, with no soft keyboard in the way |
| `hw.ramSize` | 2048 | enough for a test app, while leaving memory to Gradle |
| `hw.cpu.ncore` | 4 | |
| `disk.dataPartition.size` | 4G | room for many test apps |
| `hw.gpu.mode` | swangle_indirect | [the renderer](#the-renderer) |
| `showDeviceFrame` | no | no device skin around the screen |
| `hw.audioInput` | no | no microphone needed |

The device profiles have a multi-touch screen (`hw.screen=multi-touch`) and an on-screen navigation
bar (`hw.mainKeys=no`), so nothing else is needed for touch.

`--size <W>x<H>` and `--density <dpi>` replace the profile's screen (`hw.lcd.width`,
`hw.lcd.height`, `hw.lcd.density`); each one given alone keeps the profile's value for the other.
`avdmanager list device -c` lists the profiles for `--device`.

With `--api`, the default name follows the level even when `$AWDT_AVD` is set, so a second AVD
doesn't take the name of your everyday one. Images from API 37 on live in a folder with a minor
version, `android-37.0`: `--api 37` finds it, and `--api 36.1` names one exactly. Any image of a
level also prints `Error: Could not load devices from …/devices.xml` from avdmanager: that file is
missing from images, avdmanager uses its own profiles, and the AVD is fine.

**Where the AVD goes.** In the folder the emulator looks in, the first of the AVD folders in
[Finding your setup](../bin/README.md#finding-your-setup). The script creates that folder and passes
it to avdmanager as `ANDROID_AVD_HOME`, because avdmanager left to itself can pick another one:
cmdline-tools 12.0, the version on GitHub's runners, uses `$XDG_CONFIG_HOME/.android/avd` when
`XDG_CONFIG_HOME` is set, and the emulator never finds an AVD there.

It never overwrites an existing AVD: it fails instead (exit 1). To recreate one: `avdmanager delete
avd -n phone_api36 && mobile-create-avd.sh`. For scripts and CI jobs that cache their AVDs,
`--if-missing` accepts an existing AVD made from the same system image and leaves it as it is (exit
0); one of the same name from another image, or with another `--size` or `--density` than the ones
given, is still an error.

### The renderer

The AVDs render with `swangle_indirect`: software rendering, so it works on any host, WSLg included,
and needs no GPU. The emulator's usual software renderer, `swiftshader_indirect`, makes System UI
miss its startup limit on API 36 and 37 ("failed to complete startup"), on every cold boot, and
leaves "System UI isn't responding" over the home screen: that dialog doesn't close with Back, and
takes every touch until `mobile-ui.sh tap Wait`. With `swangle_indirect` that doesn't happen, the
boot is faster, and the emulator takes less memory. A `-gpu` flag of your own replaces it for one
boot, and AWDT_TEST_EMULATOR_FLAGS for the tests.

### Other screens

On a running emulator, no new AVD and no reboot; the change stays until it's reset:

```bash
adb shell wm size 720x1280 && adb shell wm density 320   # pretend to be a smaller phone
adb shell wm size reset && adb shell wm density reset    # back to the AVD's own screen
```

For a screen you test on often, make an AVD of it with `--size`, `--density` or `--device`.

## Booting one

`mobile-start-emulator.sh [--quick] [--wait-for-home] [name] [emulator flags…]`

```bash
mobile-start-emulator.sh                   # cold boot the default AVD
mobile-start-emulator.sh phone_api30       # another AVD
mobile-start-emulator.sh --quick           # boot from its Quick Boot snapshot instead
mobile-start-emulator.sh --wait-for-home   # also wait until the home screen has settled (tests, CI)
mobile-start-emulator.sh -wipe-data        # factory reset
mobile-start-emulator.sh my_phone -gpu host  # another AVD, another renderer
EMULATOR_TOOLBAR=show mobile-start-emulator.sh  # keep the side toolbar (WSLG.md)
```

It runs `emulator -avd <name> -gpu swangle_indirect -no-snapshot-load -no-boot-anim -no-audio` in
the background (a `-gpu` flag of your own replaces the default), logs to
`${TMPDIR:-/tmp}/emulator-<name>.log`, finds the emulator's serial by asking each running emulator
for its AVD name, waits until `sys.boot_completed=1` (so it can be chained with `./gradlew
installDebug`), and on WSL finishes with `mobile-wslg-toolbar.py <name> hide`. If the emulator exits
during boot, it stops waiting and prints how it exited (its exit status, or the signal that killed
it) and the end of the log.

**Already running.** An AVD that's already running isn't started again, but it may still be
booting, e.g. started by another call or CI step a moment ago. The script then waits for its boot
like for its own, with the same timeout, and prints its serial once Android is ready. It never
stops an emulator it didn't start: on a timeout it only fails, and if the emulator is stopped
meanwhile, it stops waiting.

**Waiting for the home app (`--wait-for-home`).** `sys.boot_completed=1` comes before the device
has settled. From API 24 on, until the user is unlocked, Settings' `FallbackHome` holds the screen
and a HOME intent resolves to it; the home app comes to the front only then, which can be after
`sys.boot_completed`, and on a host short of CPU no window had the focus long after the boot, so a
test's first touch would reach no app. With `--wait-for-home`, once Android has booted, the script
also waits until the home app's screen is in front, has finished starting and has the focus, at two
looks in a row. [`wait_for_home`'s comment](../lib/home.sh) says exactly what it checks, and when:

- when a window of another app has kept the focus for 10 s, it presses Back, twice at most, and only
  on an emulator whose boot it waited for: one that had booted before may be in use;
- once the same window of another app has kept the focus for `AWDT_OTHER_APP_TIMEOUT` seconds
  (default 60; `0`: no such limit), it fails at once, naming that screen;
- when no home app is enabled (API 24 on), it fails at once, saying so;
- after `AWDT_HOME_TIMEOUT` seconds (default 600; `0`: no limit), counted from when Android has
  booted, it fails, naming what was in front.

A failure stops the emulator it started, as after a boot timeout; one that was already running is
left running.

**Output.** stdout holds the emulator's serial (e.g. `emulator-5554`) and nothing else; every
message goes to stderr. So scripts capture it without parsing messages:

```bash
serial="$(mobile-start-emulator.sh)" && export ANDROID_SERIAL="$serial"
```

**Without a display.** The emulator's window needs an X display: without `$DISPLAY` (a CI runner,
an SSH session) the emulator aborts, and its log doesn't say why. So there the script adds
`-no-window` and says so.

**Boot timeout.** If Android hasn't finished booting after `AWDT_BOOT_TIMEOUT` seconds (default
900), the script stops the emulator it started, prints the end of the log and fails, so a stuck
boot can't keep it (or a CI job) waiting forever. Raise it on a slow host; `AWDT_BOOT_TIMEOUT=0`
waits without limit. While it waits, it prints a line every minute on stderr, e.g.
`'phone_api36' is still booting (120 s so far; the limit is 900 s)...`, so a slow boot doesn't look
like a hang in a CI log. Each adb call that checks the boot gets 15 s, because on an emulator
that's half booted or short of CPU, adb can hang without answering; a call that runs out of time
counts as "not booted yet", so the limit still applies.

**Cold boot or Quick Boot.** By default Android starts from scratch (`-no-snapshot-load`).
`--quick` (anywhere on the command line) instead restores the snapshot the emulator saved when it
was last stopped. A snapshot also restores `adbd`, the adb service inside Android, in
the middle of its old connection, and sometimes adb then lists the
emulator as `offline` and never gets through. So with `--quick`, if
the emulator stays `offline` for 30 s, the script runs `adb reconnect offline`, and if it's still
offline 30 s later it stops and says how to cold boot instead of waiting forever. A cold boot is
also `offline` until `adbd` starts, which is normal, so it's never cut short.

**KVM.** It checks access to `/dev/kvm` before starting anything, and prints the fix for the
problem it finds ([`SETUP.md`](SETUP.md#make-devkvm-writable)). When you're in the `kvm`
group but this session predates it, it re-runs itself through `sg kvm` instead.

## Stopping one

`mobile-stop-emulator.sh [--all] [--no-save] [name|serial]`

```bash
mobile-stop-emulator.sh            # $ANDROID_SERIAL, else the only running emulator
mobile-stop-emulator.sh phone_api36   # by AVD name
mobile-stop-emulator.sh emulator-5556  # by serial
mobile-stop-emulator.sh --all      # every running emulator
mobile-stop-emulator.sh --no-save --all  # every running emulator, without saving first
```

It runs `adb -s <serial> emu kill` and returns once the emulator's process has exited, so the
same AVD can be started again right away. It exits 0 also when the emulator wasn't running, so
it can be called just in case; it never stops a physical device, and a name that's neither a
running emulator nor an AVD is an error, so a typo doesn't pass as "not running". Messages go to
stderr; stdout stays empty.

**Saving first.** Before it stops the emulator, it has Android save the changes it hasn't saved
yet ([why](#recent-changes)), then commits them to the disk
image with `sync`:

| API level | How it has Android save | Time |
|---|---|---|
| 22 to 31 | `adb shell dumpsys package write` writes the app states at once ("Settings written."); a 1 s pause lets a setting changed just before be written | about 1 s |
| 33 and newer | that command no longer writes (it prints the whole package dump), so it waits for Android's own write, which Android scheduled at the change and logs in the events log (`commit_sys_config_file: [package-user-0,…]`), at most `AWDT_SAVE_WAIT` seconds (default 12) | up to 12 s, the full 12 s when nothing was pending |

It says "Saved" only once Android has confirmed a write ("Settings written.", or a new event).
From API 33 on nothing shows a write Android has yet to make, and no shell command makes it write
at once, so when no event comes within `AWDT_SAVE_WAIT` the script can't tell whether nothing was
pending or Android is late: it writes 10 s after a change, but on a starved emulator it
wrote nothing for minutes while it compiled an update of Google Play services. Then it says so,
and since when a change could be unsaved (its last logged write), rather than "Saved". To keep
such a change, wait until `adb logcat -b events -s commit_sys_config_file` shows a new
`package-user-0` line before stopping. On a host short of CPU, Android's write 10 s after a change
can slip well past 12 s (21.6 s after an enable, seen on a laptop with the emulator pinned to one
CPU), so there raise `AWDT_SAVE_WAIT` (e.g. `AWDT_SAVE_WAIT=30`), or wait for the logged write. The
default stays short because the stop waits all of it whenever nothing is pending.

Each adb call has a time limit, and an emulator that doesn't answer as a booted device is
stopped anyway, unsaved; the script says what it did. A `-read-only` emulator keeps no change,
so there it skips the save. It keeps its changes meanwhile in disk overlays in its own scratch
folder, `/tmp/android-<user>/` whatever `$TMPDIR` is (`emulator-*.qcow2`, a few tens of MB), and
deletes them when it exits; killed (SIGKILL), it leaves them there, to delete by hand.

### Recent changes

`adb emu kill` stops the emulator without shutting Android
down, and Android saves a change only a while after it's made, so a change made just before is
lost: the next cold boot starts as if the command had never run. Measured on the same Android
versions' TV images:

| What | When it's safe from a kill |
|---|---|
| An app's enabled state (`pm enable`, `pm disable-user`) | Android writes it 10 s after the first unsaved change  |
| A setting (`settings put`) | Android writes it about 0.2 s later (0.34 s at most on a starved emulator) |
| Both on API 22 | written at once |
| Then, every file | up to 5 s more: Android keeps the old file as a backup until the new one is complete, and until the filesystem's journal has recorded that (every 5 s), a boot reads the backup |

So a change is safe 15 s after it at the latest. **Wait 30 s before stopping the emulator after
a change that should stay**: twice that. `adb reboot` and `adb shell reboot -p` don't save it
either. `mobile-stop-emulator.sh` needs no wait: it has Android save first.

### Without saving

`--no-save`: from API 33 on, the save waits all of `AWDT_SAVE_WAIT` when nothing is pending, since
Android shows no sign of a write it has yet to make. When the changes since Android's last save
don't matter, e.g. after a test run whose state you don't want to keep, `--no-save` skips the save,
with a named emulator or with `--all`: the stop is as fast as on API 31, and whatever Android hadn't
saved yet is lost, as with `adb emu kill`. Leave it out after a change that should stay, such as an
app you disabled or a setting you changed. Never use it on a new AVD's first boot: [API 23's next
boot hangs](#what-the-images-do-on-their-own).

### When it can't stop

`adb emu kill` alone returns at once, before the emulator has exited, and
`adb wait-for-disconnect` waits for that without a time limit. Neither can stop an emulator whose
console doesn't answer, so a script built on them can hang. `mobile-stop-emulator.sh` always ends:

| What happens | What it does |
|---|---|
| The emulator exits (it saves its Quick Boot snapshot first) | waits for its process, then until adb no longer lists it |
| It hasn't exited `AWDT_STOP_TIMEOUT` seconds (default 60) after `adb emu kill` | kills it (SIGKILL): its Quick Boot snapshot isn't saved |
| Its console doesn't answer `adb emu kill`, or adb doesn't list it (e.g. stuck early in its boot; name it by its AVD) | sends SIGTERM, which lets it shut down, and SIGKILL if it's still running `AWDT_STOP_TIMEOUT` seconds later |
| Its console doesn't answer, and its process can't be found (e.g. it was exiting already, sent SIGTERM with a test run that was killed) | waits up to `AWDT_STOP_TIMEOUT` seconds for adb to stop listing it |
| Its process can't be found or killed, and it doesn't exit (adb keeps listing it) | fails (exit 1) and says it's still running |
| Its process can't be found, and adb stops listing it | exits 0, and says its process may still be exiting |

It says which of these happened. Each time limit lasts at least its number of seconds, and at
most a second longer. The process is found through its PID:

- The emulator's console names the file the emulator advertises itself in,
  `pid_<PID>.ini` (`adb emu avd discoverypath`, e.g.
  `/run/user/1000/avd/running/pid_12345.ini`), which it deletes when it exits. This names the very
  instance the serial belongs to.
- Without that answer (a console that's hung, or doesn't know the command), the script reads
  those files itself, in `$XDG_RUNTIME_DIR/avd/running/` (else `/run/user/<uid>/avd/running/`,
  where the emulator writes them then too). Each holds the emulator's console port (`port.serial=`,
  the number in its serial) and its AVD's name (`avd.name=`), so the serial's file names its
  instance, and its AVD, which a hung console doesn't tell.
- Else the PID is the one the emulator writes into `hardware-qemu.ini.lock` in the AVD's folder
  and deletes when it exits. An emulator started with `-read-only` writes no lock file, and
  several of them can run for one AVD. (A normal instance can't run next to them: the emulator
  refuses to start with "Another emulator instance is running".)
- Else, named by its AVD alone, the discovery files of that AVD. If they name several
  `-read-only` instances, whose consoles all don't answer, the script stops none of them: it fails
  and lists their serials, so you can name one.

A PID counts only if that process's command line names the AVD, so a lock file or discovery
file left behind by a killed emulator can't make the script stop another process. A hung
emulator whose discovery file isn't found (e.g. it was started with another `$XDG_RUNTIME_DIR`)
can only be found through its lock file, in its AVD's folder: to stop it, name its AVD rather
than its serial. Stopped by its AVD's name, a hung emulator may stay in adb's list for a moment
after the script returns, until adb notices it's gone.

An emulator that's exiting, or has exited, when the script gets to it isn't a failure to stop it.
Its console answers nothing from the moment it starts shutting down, so the script can't learn its
AVD's name (with `--all` or a serial) or its PID from it; adb lists it until a moment after its
process has exited (seen after a SIGTERM: listed as a device for 2 s while it shut down, then as
offline with qemu already a zombie, then gone). While its discovery file still names its process,
the script waits for that; otherwise it waits for adb to stop listing it. A zombie, an exited
process its parent hasn't reaped yet, has exited: its command line is empty, so its PID never counts
as the AVD's.

Don't wait for an emulator by searching for its process by name: `pgrep -f`/`pkill -f` match
their pattern against every command line, including the shell that runs them when the command
is passed as a string (`bash -c '…'`, as scripts and AI agents do). A loop like
`while pgrep -f 'qemu.*phone_api36'; do …; done` then finds itself and never ends.

## Several Android versions

To test an app on more than one Android version, create one AVD per API level and boot them one
after the other: a running emulator takes [up to a few GB of memory](SETUP.md#sizes).

```bash
for avd in phone_api24 phone_api30 phone_api36; do
    mobile-start-emulator.sh --wait-for-home "$avd" && ./gradlew connectedDebugAndroidTest
    mobile-stop-emulator.sh --no-save "$avd"
done
```

With several devices connected, `adb` refuses to guess, and `./gradlew installDebug` installs on all
of them. Set `ANDROID_SERIAL` to the serial `mobile-start-emulator.sh` prints to use only that one.

## What the images do on their own

The commands work the same on every [tested image](#tested-images); these are the differences you
may run into:

| API | Difference |
|---|---|
| 21–22 | The launcher is `com.android.launcher`, with `com.android.launcher2.Launcher` as its activity. `logcat`'s default format is another one: pass `-v threadtime` when a script reads it. No `cmd` on the device. |
| 21–23 | The images declare no Wi-Fi at all (`android.hardware.wifi`). An AVD takes 4.4 GB once booted. |
| 23 | A new AVD's first boot must be saved: [stopped with `--no-save`](#without-saving), its next boot with a window hangs (below). |
| 23 on | The launcher is `com.android.launcher3`. |
| 24 on | Until the user is unlocked after a boot, a HOME intent resolves to Settings' `FallbackHome`. |
| Before 26 | `adb shell input` has no `draganddrop`, so no way to hold a touch and then move it; `mobile-touch.sh` has. |
| Before 28 | The images don't declare Wi-Fi Direct (`android.hardware.wifi.direct`). |
| 29 | `dumpsys window` names the focused app twice. |
| Before 30 | `adb shell input` has no `motionevent`. `adb shell cmd uimode` doesn't work on the levels tried (21, 24). |
| 21, 30 | `adb logcat -c` leaves lines behind. |
| 36, 37 | Only `swiftshader_indirect` makes System UI miss its startup limit ([the renderer](#the-renderer)). |

On the Google APIs images the launcher can differ (`com.google.android.apps.nexuslauncher` on recent
levels). `mobile-start-emulator.sh --wait-for-home` asks Android which one it is, and names it.

**The hang on API 23.** Each image runs a one-time setup activity (`com.android.sdksetup`) on a new
AVD's first boot. When a stop throws away what that boot had yet to save, the next boot runs it
again, and with a window it stays `FINISHING` under a keyguard that never draws, so
`sys.boot_completed` never comes. The boot after that one works. `mobile-stop-emulator.sh` saves by
default, so only `--no-save` right after a new AVD's first boot leads there.

## What an emulator can't do

An emulator runs Android, not a phone's radios. Seen on these images:

- **No Miracast, no Wi-Fi Display.** The display service has no `WifiDisplayAdapter` (`adb shell
  dumpsys display` lists the adapters), so an app finds no Wi-Fi display to connect to, and only a
  physical device can tell whether its build has one.
- **No Wi-Fi Direct in practice.** From API 28 on the images declare the feature, but Wi-Fi P2P
  stays in `P2pDisabledState` (`adb shell dumpsys wifip2p`), with no interface for it.
- **A second screen works.** An overlay display is a real `Presentation` target, with
  `FLAG_PRESENTATION` ([how](DRIVING.md#changing-the-device)), so what an app shows there can be
  developed here.

**Wi-Fi** itself works from API 24 on: the emulator's own `AndroidWifi` network. Foldables work as a
device profile (`mobile-create-avd.sh --device pixel_9_pro_fold --api 36`), with their folded states
(`adb shell cmd device_state print-states`).
