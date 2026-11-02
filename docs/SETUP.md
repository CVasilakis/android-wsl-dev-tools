# Development environment setup

How to set up the toolchain for developing Android phone and tablet apps from the command line on
WSL2, with emulators and without Android Studio. What's supported is in
[Scope](../README.md#scope). For using the emulators once they're set up, see
[`EMULATORS.md`](EMULATORS.md); for a CI runner, see [`CI.md`](CI.md).

Locations below are defaults, not requirements. An existing SDK (e.g. Android Studio's) or AVD
works as-is: Gradle and the commands find it through `ANDROID_HOME`, `local.properties` and the
other places listed in [Finding your setup](../bin/README.md#finding-your-setup), so only the
missing pieces need installing. The commands that run a script assume you're in this repository.

## Components

The versions are the ones this setup was tested with; newer ones should work too.

| Component | Tested version | Location |
|---|---|---|
| JDK | OpenJDK 21 (`openjdk-21-jdk-headless`) | `/usr/lib/jvm/java-21-openjdk-amd64` |
| Android SDK root | — | `~/Android/Sdk` |
| cmdline-tools | 22.0 | `~/Android/Sdk/cmdline-tools/latest` |
| `android` CLI | downloaded by `cmdline-tools/latest/bin/android` on its first run | `~/.android/cli`, `~/.android/bin` |
| platform-tools (adb) | 37.0.1 | `~/Android/Sdk/platform-tools` |
| SDK platform | the `compileSdk` of your project, e.g. android-36 | `~/Android/Sdk/platforms/android-36` |
| Build-tools | 36.0.0, installed automatically by the Android Gradle Plugin on the first build | `~/Android/Sdk/build-tools` |
| Emulator | 37.1.11 | `~/Android/Sdk/emulator` |
| System image | `system-images;android-36;default;x86_64` (Android 16) | `~/Android/Sdk/system-images/android-36/default/x86_64` |
| Optional: more system images, to test on other Android versions | `system-images;android-<level>;default;x86_64`, and Google's `…;google_apis;x86_64` ([tested images](EMULATORS.md#tested-images)) | `~/Android/Sdk/system-images/android-<level>/…` |
| AVD | `phone_api36` (`medium_phone`); optionally `phone_api<level>` for other levels, `phone_gapi<level>` for Google APIs, `tablet_api<level>` | `~/.android/avd/phone_api36.avd` |
| Gradle | per project, through its wrapper (`./gradlew`) | `~/.gradle` |

### Sizes

Downloads are what goes over the network; "on disk" is what the finished install occupies.

| Item | Download | On disk |
|---|---|---|
| cmdline-tools zip | ~174 MB | 175 MB (`cmdline-tools/`) |
| JDK package (Ubuntu's) | ~83 MB | |
| platform-tools | ~9 MB | 22 MB |
| platforms;android-36 | ~66 MB | 146 MB |
| build-tools (automatic, first build) | ~64 MB | 147 MB |
| emulator | ~354 MB | 821 MB |
| The API 36 system image | ~844 MB | 2.0 GB |
| The emulator's system libraries (`libpulse0`, …, step 1) | a few MB | |
| the `android` CLI, on its first run | ~250 MB | ~250 MB (`~/.android`) |
| **The SDK once everything above is installed** | | **~3.3 GB** (`~/Android/Sdk`) |
| Optional: the system images of other levels | table below | table below |
| An AVD, once booted | | ~0.5 GB from API 28 on, 1.3 GB on API 24 to 27, 4.4 GB on API 21 to 23; it grows with snapshots and apps |
| A Gradle distribution (first `./gradlew` of a project) | ~150 MB | |
| Gradle/Maven dependencies of a project (AGP, Kotlin, test libraries, …) | a few hundred MB | ~1.3 GB (`~/.gradle`) |

The plain images (`system-images;android-<level>;default;x86_64`):

| API | Android | Download | On disk |
|---|---|---|---|
| 21 | 5.0 | ~293 MB | 3.2 GB |
| 22 | 5.1 | ~300 MB | 3.3 GB |
| 23 | 6.0 | ~365 MB | 3.6 GB |
| 24 | 7.0 | ~419 MB | 3.1 GB |
| 25 | 7.1 | ~423 MB | 3.3 GB |
| 26 | 8.0 | ~474 MB | 3.2 GB |
| 27 | 8.1 | ~492 MB | 3.2 GB |
| 28 | 9 | ~565 MB | 2.7 GB |
| 29 | 10 | ~690 MB | 3.2 GB |
| 30 | 11 | ~676 MB | 3.2 GB |
| 31 | 12 | ~657 MB | 4.2 GB |
| 32 | 12L | ~668 MB | 4.2 GB |
| 33 | 13 | ~694 MB | 4.2 GB |
| 34 | 14 | ~721 MB | 1.7 GB |
| 35 | 15 | ~782 MB | 1.7 GB |
| 36 | 16 | ~844 MB | 2.0 GB |
| 37 | 17 | ~908 MB | 2.5 GB |

The Google APIs images (`system-images;android-<level>;google_apis;x86_64`; API 27's is `x86`, API
37's folder `android-37.0`), with Google Play services and Google's apps:

| API | Android | Download | On disk |
|---|---|---|---|
| 21 | 5.0 | ~0.4 GB | 3.5 GB |
| 22 | 5.1 | ~0.6 GB | 3.5 GB |
| 23 | 6.0 | ~0.7 GB | 3.6 GB |
| 24 | 7.0 | ~1.1 GB | 3.1 GB |
| 25 | 7.1 | ~1.3 GB | 3.6 GB |
| 26 | 8.0 | ~1.0 GB | 3.2 GB |
| 27 | 8.1 | ~0.8 GB | 3.2 GB |
| 28 | 9 | ~1.1 GB | 2.7 GB |
| 29 | 10 | ~1.3 GB | 3.2 GB |
| 30 | 11 | ~1.4 GB | 3.3 GB |
| 31 | 12 | ~1.5 GB | 4.3 GB |
| 32 | 12L | ~1.5 GB | 4.3 GB |
| 33 | 13 | ~1.7 GB | 8.2 GB |
| 34 | 14 | ~1.6 GB | 4.2 GB |
| 35 | 15 | ~1.7 GB | 3.5 GB |
| 36 | 16 | ~1.9 GB | 4.3 GB |
| 36.1 | 16 QPR | ~2.0 GB | 4.3 GB |
| 37 | 17 | ~2.1 GB | 5.3 GB |

**Memory:** a running emulator takes 1.3–1.5 GB of RAM on API 21 to 25, about 1.9 GB on API 26 and
27, and 2.4–3.1 GB from API 28 on; the Google APIs images take more, up to 4.7 GB. A host needs that
much free beside what Gradle takes. Run one at a time on a small host, as a build next to an
emulator can run out of memory.

## Prerequisites

- WSL2 with **WSLg** (Windows 11, or a recent Windows 10 build): `echo $DISPLAY` prints `:0`.
- Hardware virtualization, so `/dev/kvm` exists: `ls -l /dev/kvm`. For WSL2 that's nested
  virtualization, enabled by default.
- `unzip`, `curl` and `python3` 3.10+ (used by `mobile-wslg-toolbar.py`, `mobile-ui.sh` and the
  tests).

## Steps

### 1. System packages and KVM access (needs sudo)

This is the whole sudo part of the setup; everything after it runs as your own user.

```bash
sudo apt-get install -y openjdk-21-jdk-headless \
    libpulse0 libnss3 libxkbfile1 libsm6 libxext6 libxi6 libdrm2 libpng16-16t64
sudo usermod -aG kvm $USER
```

- A JRE alone (`openjdk-21-jre`) is **not** enough: the
  Android build needs `javac` and `jlink`.
- Current Android Gradle Plugin versions need JDK 17+; Robolectric tests on recent API levels
  need 21 or newer. A JDK only works with a Gradle that can run on it: 21 with Gradle 8.5 or
  newer, 25 with 9.1 or newer, so a project whose wrapper is still on 8.x fails on JDK 25 with
  `Unsupported class file major version 69`.
- The `lib…` packages are the system libraries the emulator needs and doesn't bundle. Ubuntu's WSL
  image lacks `libpulse0`, `libnss3`, `libxkbfile1` and `libsm6`; a more minimal Ubuntu, such as a
  container, lacks the others too. Without one of them the emulator fails before showing anything,
  even with `-no-audio`, e.g. `qemu-system-i386: error while loading shared libraries: libnss3.so:
  cannot open shared object file`.
- `sudo` needs a password, so run these in a regular terminal. Tools that run commands without a
  terminal (such as an AI agent's shell) can't prompt for it.

Check: `/usr/lib/jvm/java-21-openjdk-amd64/bin/javac -version` prints 21.

#### Make `/dev/kvm` writable

The x86 emulator won't start without hardware acceleration, and `/dev/kvm` is only writable by
root and by the group that owns it. Two separate things have to be true, so check the device
rather than assuming `usermod` was enough:

```bash
ls -ln /dev/kvm            # the 4th column is the group id that owns the device
getent group kvm           # kvm:x:<gid>:<members>
```

- **The gids match** and you're a member: you're done for new sessions. The new group only
  applies to sessions started after `usermod` (on WSL: after `wsl --shutdown` from Windows, then
  reopening the terminal). `mobile-start-emulator.sh` also works in an already-open session by
  re-running itself with `sg kvm`.
- **The gids differ**: the device belongs to a group that isn't `kvm`, so being in `kvm` grants
  nothing. This happens on WSL, where `/dev/kvm` is created before udev applies
  `50-udev-default.rules`. Hand the device to the `kvm` group, and keep that across restarts:

  ```bash
  sudo chgrp kvm /dev/kvm && sudo chmod 660 /dev/kvm
  echo 'z /dev/kvm 0660 root kvm -' | sudo tee /etc/tmpfiles.d/kvm.conf
  ```

  With **several WSL distros**, that isn't enough: they share one kernel and one `/dev`, and when
  another distro boots, its udev hands `/dev/kvm` to *its* `kvm` group, whose gid may differ, while
  this distro keeps running. Give the `kvm` group the same gid in every distro that has one, e.g.
  in the other distro (with 993 being this distro's `kvm` gid, and free there):
  `sudo groupmod -g 993 kvm`.

`mobile-start-emulator.sh` tells the two cases apart and prints the fix for the one you have.

Check: `test -w /dev/kvm && echo ok` in a session started after `usermod` (or under `sg kvm`).

### 2. Command-line tools

Download `commandlinetools-linux-*_latest.zip` from
<https://developer.android.com/studio#command-tools>. The tools must live in `cmdline-tools/latest`,
or they can't work out which SDK they belong to. Run this from the folder you downloaded the zip
into:

```bash
mkdir -p ~/Android/Sdk/cmdline-tools
unzip -q commandlinetools-linux-*_latest.zip -d ~/Android/Sdk/cmdline-tools/
mv ~/Android/Sdk/cmdline-tools/cmdline-tools ~/Android/Sdk/cmdline-tools/latest
```

The zip unpacks to a folder named `cmdline-tools`, which is why the `mv` renames it rather than
moving it into place. Unpacked this way the package has no `package.xml`, so
`android sdk list --no-metrics` shows its version as `unknown`; that's harmless, everything still
works.

### 3. Environment variables and the `android` CLI

Put this in `~/.bashrc` (where exactly, and why, below), then open a new terminal:

```bash
# Android SDK
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
```

**Put it above the interactive check, not at the end of the file.** Ubuntu's stock
`~/.bashrc` starts with

```bash
case $- in
    *i*) ;;
      *) return;;
esac
```

so anything below it is skipped by non-interactive shells — build scripts, CI, and the shells AI
agents run commands in. Appending the block to the end of the file works when you type commands
yourself and then fails with `SDK location not found` from `bash -lc './gradlew …'`.

Check both:

```bash
bash -lic 'echo $ANDROID_HOME'    # interactive
bash -lc  'echo $ANDROID_HOME'    # non-interactive: must print the same path
```

A shell that is neither interactive nor a login shell (`bash -c …`) reads no startup file at all,
so give those the variable explicitly or rely on the project's `local.properties` (step 7).

Gradle and `avdmanager` run the JDK in `JAVA_HOME`. The `java` and `javac` on `PATH` are whichever
JDK `update-alternatives` picked, which with several JDKs installed can be
another one, so check the JDK through `JAVA_HOME`:

```bash
"$JAVA_HOME/bin/javac" -version    # prints 21
```

To also call this repository's commands by name, see
[`README.md`](../README.md#optional-put-the-commands-on-your-path).

#### The `android` CLI

cmdline-tools 22.0 deprecates `sdkmanager`: running it prints a warning pointing at the `android`
CLI, whose `android sdk` subcommand replaces it. From cmdline-tools 23.0 on, `sdkmanager` is only
a wrapper that runs `android sdk`: like `android`, its first run downloads the CLI, and it exits 0
for a package that doesn't exist (notes below), but it can't turn telemetry off
([Telemetry](#telemetry)). The steps below use `android`:

| Task | `android` | deprecated `sdkmanager` |
|---|---|---|
| install packages | `android sdk install <pkg>…` | `sdkmanager "<pkg>"…` |
| list what's installed | `android sdk list` | `sdkmanager --list_installed` |
| list everything available | `android sdk list --all` | `sdkmanager --list` |
| update packages | `android sdk update` | `sdkmanager --update` |
| remove a package | `android sdk remove <pkg>` | `sdkmanager --uninstall "<pkg>"` |
| accept licenses up front | not needed (see below) | `yes \| sdkmanager --licenses` |

Every `android` command in this document carries `--no-metrics`; see [Telemetry](#telemetry).

Notes before you use it:

- **The first run downloads the CLI itself** (~250 MB into `~/.android`), so it takes a while and
  needs network even when every package is already installed.
- **Package ids take `/` or `;`**: `android sdk list` prints `platforms/android-36`, and both
  `android sdk install "platforms;android-36"` and `.../android-36` work. This document keeps the
  `;` form, which is also what Gradle error messages and `package.xml` use.
- **It exits 0 when a package doesn't exist**, printing only `Package … not found.` on stdout, so
  `android sdk install <typo> && …` carries on as if it had worked. Check with
  `android sdk list --no-metrics` rather than trusting the exit status.
- **It accepts licenses as it installs**, so there's no `sdkmanager --licenses` step:
  `android sdk install` writes the license of each package to `$ANDROID_HOME/licenses/`. The
  packages of step 4 are under `android-sdk-license`, so after step 4 that file exists and the
  Android Gradle Plugin can install build-tools by itself. A package under a different license
  accepts its own on first install.

#### Telemetry

The `android` CLI reports usage to Google unless told not to. Its first run prints a notice saying
it collects "commands, sub-commands, and flags used", and names `--no-metrics` as the way to
disable it. What that means in practice:

- **Each invocation writes one event** to `~/.android/cli/analytics/metrics/spool/*.bproto`, and a
  separate `upload-metrics` process sends spooled events to `https://play.google.com/log` on an
  interval. Read one with `strings`; a plain `android sdk list` records:

  ```
  android2  --sdk  <redacted>2  sdk2  list:  <VARIABLE_NAME>:  <VARIABLE_NAME>
  ```

  the command, the subcommand, the flag names, and **the names of some of the environment
  variables that are set** (not their values; argument values are written as a literal
  `<redacted>`).
- **`--no-metrics` writes nothing at all**: no spool file appears. The flag works anywhere on the
  command line, and per its own help text disables "metrics/crash reports collection", so it
  covers crash reports too.
- **`~/.android/analytics.settings` doesn't stop it.** That file is the older SDK-wide opt-out
  (`"hasOptedIn":false`); events are spooled regardless of it. It may still gate the upload, but
  the recording on disk happens either way.
- **`sdkmanager` can't opt out.** From cmdline-tools 23.0 on, it runs `android sdk` without
  `--no-metrics`, so each call writes an event, and it refuses the flag (it prints its usage and
  exits 1).
- **There is no persistent opt-out** — no config file, no subcommand, no environment variable.
  (`ANDROID_CLI_ANALYTICS_URL` and `ANDROID_CLI_CRASH_URL` only change where reports are sent.)
  So the flag has to be on every call, which is why every `android` command here carries it.

To opt in, drop `--no-metrics`. To discard what was collected before you opted out:

```bash
rm -f ~/.android/cli/analytics/metrics/spool/*.bproto
```

### 4. SDK packages

```bash
android sdk install --no-metrics "platform-tools" "platforms;android-36" "emulator"
```

(`android-36` is your project's `compileSdk`.)

Check: `android sdk list --no-metrics` lists `emulator`, `platform-tools` and
`platforms/android-36`.

### 5. The system image

```bash
android sdk install --no-metrics "system-images;android-36;default;x86_64"
```

**Optional: other Android versions.** The tested images are in
[`EMULATORS.md`](EMULATORS.md#tested-images), their sizes [above](#sizes). Pick the ones you need,
for example:

```bash
android sdk install --no-metrics "system-images;android-24;default;x86_64" "system-images;android-30;default;x86_64"
android sdk install --no-metrics "system-images;android-37.0;default;x86_64"      # from API 37 on, levels have a minor version
android sdk install --no-metrics "system-images;android-36;google_apis;x86_64"    # with Google Play services
```

`android sdk list --no-metrics --all | grep system-images` lists every image available.

### 6. Emulator (AVD)

```bash
bin/mobile-create-avd.sh                # creates the AVD "phone_api36"
bin/mobile-create-avd.sh --api 30       # optional: "phone_api30", from the API 30 image of step 5
bin/mobile-create-avd.sh --tablet --api 36  # optional: "tablet_api36"
```

avdmanager prints a devices.xml error that's harmless ([`EMULATORS.md`](EMULATORS.md#creating-one)).
`mobile-create-avd.sh` only writes files, so it works without KVM access; booting the AVD (step 7)
is the first thing that needs it.

### 7. Use it from a project

From the project's folder (here cloned next to this repository):

```bash
./gradlew assembleDebug                                 # the first run downloads Gradle, AGP, Kotlin and build-tools
../android-wsl-dev-tools/bin/mobile-start-emulator.sh   # boots phone_api36, returns when Android is ready
./gradlew installDebug
```

`local.properties` (git-ignored in Android projects) is created by Android Studio, not by Gradle on
the command line, so create it by hand:

```bash
echo "sdk.dir=$HOME/Android/Sdk" > local.properties
```

It's redundant whenever `ANDROID_HOME` reaches the build, but it costs nothing and it's the only
thing that works in a shell that reads no startup file (step 3), so it's worth creating once per
project.

### 8. Test tools (only to work on this repository)

The tests need only Python 3.10+; two optional tools enable more of them. See
[`tests/README.md`](../tests/README.md).

## When a step fails

Each message and its cause: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md#setup).
