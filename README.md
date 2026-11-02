# android-wsl-dev-tools

> **Not an official Google or Microsoft product.** This is an independent project, not affiliated
> with, sponsored or endorsed by Google LLC or Microsoft Corporation. Android is a trademark of
> Google LLC; Windows and WSL are trademarks of Microsoft Corporation. They're named here only to
> say what the tools work with.

Command-line tools for developing Android phone and tablet apps without Android Studio, on Ubuntu
under WSL2: create, boot and stop emulators on every Android version, touch their screens, and see
what's on them, from a terminal, a script or a coding agent. They work with any Gradle project, and
find the SDK, AVDs and emulators on their own.

The commands start with `mobile-`, as they cover phones and tablets. For Android TV, the same tools
exist in [android-tv-wsl-dev-tools](https://github.com/CVasilakis/android-tv-wsl-dev-tools), whose
commands start with `tv-`, so both can be on your `PATH`, and a name never means two things.

## Documentation

[`docs/README.md`](docs/README.md) is the map: the reading order, every guide, and how the docs are
written. To start, [`docs/SETUP.md`](docs/SETUP.md) installs the toolchain and
[`bin/README.md`](bin/README.md) lists the commands.

## Scope

**Where:** Ubuntu on WSL2 (Windows 11, or a recent Windows 10 build, with WSLg), tested on Ubuntu
24.04. Other Debian-based distributions, and Ubuntu outside WSL, may work but are untested; the
WSLg workarounds are skipped outside WSL. GitHub's Ubuntu runners are covered for headless use in
CI ([`docs/CI.md`](docs/CI.md)). macOS and native Windows aren't supported.

**What:** phone and tablet apps, on x86_64 emulators with a touchscreen. TV, Wear OS and Automotive
apps are out of scope: their emulators need other hardware settings and input.

**A physical phone** works with `mobile-touch.sh` and `mobile-ui.sh` once adb sees it, as they only
talk to adb, but that's untested, and getting adb in WSL to a phone is up to you. Anything an
emulator can't do needs one: see [what an emulator can't
do](docs/EMULATORS.md#what-an-emulator-cant-do).

**Tested emulator images:** in [`docs/EMULATORS.md`](docs/EMULATORS.md#tested-images).

## Getting started

1. Clone this repository anywhere, for example next to your projects.
2. Follow [`docs/SETUP.md`](docs/SETUP.md), skipping the parts you already have (an Android Studio
   SDK or AVD works as is). It ends with booting the emulator from your project.
3. Call the commands by their path from any folder (`../android-wsl-dev-tools/bin/mobile-touch.sh`),
   or put them on your `PATH`.

### Optional: put the commands on your `PATH`

To type `mobile-start-emulator.sh` instead of its path, either add `bin/` to your `PATH` (in
`~/.bashrc`):

```bash
export PATH="$PATH:$HOME/android-wsl-dev-tools/bin"
```

or symlink the commands into a folder that's already on it:

```bash
ln -s ~/android-wsl-dev-tools/bin/* ~/.local/bin/
```

Both work the same way: the commands resolve symlinks to find the rest of this repository. `bin/`
holds only the commands, so nothing else lands on your `PATH`. Messages that suggest a command show
its bare name when it's on your `PATH`, and otherwise the path you called the script by, so they
can be pasted as is.

## Versions

Releases are git tags named `vMAJOR.MINOR.PATCH` ([semantic versioning](https://semver.org)), with
release notes on GitHub. `main` can change at any time, so anything automated should pin a release
tag, or a full commit SHA.

The version covers the commands' names, options and defaults as their `--help` shows them (including
the AVD `mobile-create-avd.sh` creates), where they look for the SDK and AVDs, the environment
variables they read, their exit statuses, and `mobile-start-emulator.sh`'s stdout (the serial
alone). Breaking any of these is a new major version; new options or tested API levels are a new
minor one. Messages, [`lib/`](lib/README.md) and [`tests/`](tests/README.md) can change in any
release.
