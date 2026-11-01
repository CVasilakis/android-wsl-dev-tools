# shellcheck shell=bash
# shellcheck disable=SC2034  # the variables set here are used by the scripts that source this file
# The base every script sources: finds the Android SDK and its tools wherever the user keeps them,
# so the scripts work with any setup, not only the one in docs/SETUP.md, and says what's missing.
# After sourcing: $TOOLS_DIR (this repository), $BIN_DIR, $LIB_DIR, $SDK, $ADB, $EMULATOR,
# $AVDMANAGER, $ANDROID_CLI, $SDKMANAGER (each tool is empty if it isn't installed) and the
# functions below.
#
# The scripts are called by a relative path, through $PATH, or through a symlink to them, from any
# folder. So nothing here depends on the current folder, except local.properties, which belongs to
# the project the user works in. readlink -f resolves symlinks, so a symlinked script still finds
# the real repository.

TOOLS_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
BIN_DIR="$TOOLS_DIR/bin"
LIB_DIR="$TOOLS_DIR/lib"

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

# The local.properties of the Gradle project the user is in: the nearest one in the current folder
# or above it, so it's found from a project's subfolders too. Fails if there's none.
find_local_properties() {
    local dir="$PWD"
    while true; do
        if [ -f "$dir/local.properties" ]; then echo "$dir/local.properties"; return 0; fi
        if [ "$dir" = / ]; then return 1; fi
        dir="$(dirname "$dir")"
    done
}

# The SDK, searched in this order: $ANDROID_HOME, the deprecated $ANDROID_SDK_ROOT, sdk.dir in the
# project's local.properties (what Gradle uses, written by Android Studio), the SDK that the adb on
# $PATH belongs to, then Android Studio's default location. The first existing folder wins.
find_sdk() {
    local dir adb_on_path properties
    adb_on_path="$(command -v adb 2>/dev/null || true)"
    properties="$(find_local_properties || true)"
    for dir in \
        "${ANDROID_HOME:-}" \
        "${ANDROID_SDK_ROOT:-}" \
        "${properties:+$(sed -n 's/^sdk\.dir=//p' "$properties" | sed 's/\\\(.\)/\1/g')}" \
        "${adb_on_path:+$(dirname "$(dirname "$(readlink -f "$adb_on_path")")")}" \
        "$HOME/Android/Sdk"; do
        if [ -n "$dir" ] && [ -d "$dir" ]; then echo "$dir"; return 0; fi
    done
    echo "$HOME/Android/Sdk"   # doesn't exist: the tool checks below report what's missing
}

# The first candidate that is an executable file, else the command of that name on $PATH.
find_tool() {
    local name="$1" candidate
    shift
    for candidate in "$@"; do
        if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
    done
    command -v "$name" 2>/dev/null || true
}

SDK="$(find_sdk)"
ADB="$(find_tool adb "$SDK/platform-tools/adb")"
EMULATOR="$(find_tool emulator "$SDK/emulator/emulator")"
# cmdline-tools/latest is the standard layout; versioned folders (cmdline-tools/19.0) also occur,
# newest first.
mapfile -t _versioned_avdmanagers < <(printf "%s\n" "$SDK"/cmdline-tools/*/bin/avdmanager | sort -rV)
AVDMANAGER="$(find_tool avdmanager "$SDK/cmdline-tools/latest/bin/avdmanager" "${_versioned_avdmanagers[@]}")"
# The 'android' CLI replaces the deprecated sdkmanager, but only exists from cmdline-tools 22.0,
# so install hints fall back to sdkmanager on older ones (see install_hint).
mapfile -t _versioned_android_clis < <(printf "%s\n" "$SDK"/cmdline-tools/*/bin/android | sort -rV)
ANDROID_CLI="$(find_tool android "$SDK/cmdline-tools/latest/bin/android" "${_versioned_android_clis[@]}")"
mapfile -t _versioned_sdkmanagers < <(printf "%s\n" "$SDK"/cmdline-tools/*/bin/sdkmanager | sort -rV)
SDKMANAGER="$(find_tool sdkmanager "$SDK/cmdline-tools/latest/bin/sdkmanager" "${_versioned_sdkmanagers[@]}")"

# The command that installs an SDK package, for messages that suggest one. 'android sdk install'
# is the current tool; sdkmanager is deprecated but is all there is before cmdline-tools 22.0, so
# suggest whichever this SDK actually has, and the new one when it has neither. --no-metrics keeps
# the suggested command from reporting usage to Google, which the android CLI does by default and
# can only be turned off per call (docs/SETUP.md, "Telemetry").
install_hint() {
    if [ -z "$ANDROID_CLI" ] && [ -n "$SDKMANAGER" ]; then
        echo "sdkmanager \"$1\""
    else
        echo "android sdk install --no-metrics \"$1\""
    fi
}

# Exits with an install hint if a tool wasn't found. $1 = variable value, $2 = SDK package name.
# Without any SDK there's nothing to install with either, so that case points to SETUP.md instead.
require() {
    [ -n "$1" ] && return 0
    [ -d "$SDK" ] || die "no Android SDK found. Set \$ANDROID_HOME to your SDK, or install one
as described in $TOOLS_DIR/docs/SETUP.md (steps 2-5). Looked in: \$ANDROID_HOME, \$ANDROID_SDK_ROOT,
sdk.dir in local.properties, the adb on \$PATH, $SDK."
    die "'$2' not found in the SDK ($SDK) or on \$PATH. Install it with:
  $(install_hint "$2")
or point \$ANDROID_HOME at your SDK (see $TOOLS_DIR/docs/SETUP.md)."
}

# How to call one of the scripts in bin/, for messages that suggest a command: its bare name when
# that name on $PATH is this very script, else the way the running script was called (e.g.
# ../android-wsl-dev-tools/bin/start-emulator.sh), so the suggestion can be pasted as is.
command_for() {
    local on_path
    on_path="$(command -v "$1" 2>/dev/null || true)"
    if [ -n "$on_path" ] && [ "$(readlink -f "$on_path")" = "$BIN_DIR/$1" ]; then
        echo "$1"
    else
        echo "$(dirname "$0")/$1"
    fi
}

# Host facts. The overrides exist for the tests (tests/), which simulate other machines; nothing
# else should set them.
KVM_DEVICE="${AWDT_KVM_DEVICE:-/dev/kvm}"
is_wsl() { grep -qi microsoft "${AWDT_PROC_VERSION:-/proc/version}" 2>/dev/null; }

# The emulator's renderer: software, so it works on any host, WSLg included, and without SwiftShader's
# JIT, which SELinux denies on Fedora. swiftshader_indirect is the usual choice elsewhere, but here
# System UI misses its startup limit with it on API 36 and 37 ("failed to complete startup"), which
# leaves an ANR dialog over the home screen on every cold boot, and it takes more memory
# (docs/EMULATORS.md). create-avd.sh writes it into the AVD, start-emulator.sh passes it.
GPU_MODE=swangle_indirect

