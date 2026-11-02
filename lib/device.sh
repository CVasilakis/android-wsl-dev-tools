# shellcheck shell=bash
# shellcheck disable=SC2034  # the variables set here are used by the scripts that source this file
# Talking to running devices with time limits. Needs sdk.sh.

# adb with a time limit, for calls that are repeated until something changes. On an emulator
# that's half booted or starved of CPU (a small CI runner), `adb shell` or `adb emu` can hang
# without ever answering, and a loop waiting on it would never reach its own time limit. A call
# that runs out of time fails like one that got no answer. AWDT_ADB_TIMEOUT exists for the tests.
# The emulator tier copies its default and the 5 s (tests/emulator/test_on_emulator.py).
ADB_TIMEOUT="${AWDT_ADB_TIMEOUT:-15}"
adb_bounded() {
    timeout -k 5 "$ADB_TIMEOUT" "$ADB" "$@"
}

# time_is_up <start> <seconds>: whether at least that many seconds have passed since <start>, a
# value of $SECONDS. $SECONDS counts whole seconds of the clock, so `$SECONDS - start >= n` can be
# true only n - 1 s and a bit after the start (a limit of 1 s could end at once); more than n whole
# seconds is at least n s, and at most n + 1. A limit of 0 is up at once.
time_is_up() {
    [ "$2" -eq 0 ] || [ $((SECONDS - $1)) -gt "$2" ]
}

# Serials of the running emulators, one per line (physical devices are left out).
running_emulators() {
    adb_bounded devices 2>/dev/null | awk '$1 ~ /^emulator-[0-9]+$/ { print $1 }'
}

# The AVD name of a running emulator, asked through its console. Empty if it doesn't answer yet.
emulator_avd() {
    adb_bounded -s "$1" emu avd name 2>/dev/null | head -n 1 | tr -d '\r'
}

# pick_device [<serial>]: the device a command acts on: the serial given, else $ANDROID_SERIAL, else
# the only running emulator. Phones connected at the same time are used only when named, so that a
# gesture never goes to one by accident. Dies with what to do otherwise.
pick_device() {
    local emulators=()
    if [ -n "${1:-}" ]; then echo "$1"; return 0; fi
    if [ -n "${ANDROID_SERIAL:-}" ]; then echo "$ANDROID_SERIAL"; return 0; fi
    mapfile -t emulators < <(running_emulators)
    case ${#emulators[@]} in
        0) die "no running emulator. Start one with: $(command_for mobile-start-emulator.sh)" ;;
        1) echo "${emulators[0]}" ;;
        *) die "several emulators are running (${emulators[*]}). Name one with -s <serial>, or set \$ANDROID_SERIAL." ;;
    esac
}

# screen_size <serial>: "<width> <height>" of the screen as it's turned now, in pixels: what `dumpsys
# window displays` calls cur=, which `wm size` isn't (it keeps the physical size when the screen
# turns). Prints nothing if the device doesn't say.
screen_size() {
    adb_bounded -s "$1" shell dumpsys window displays < /dev/null 2>/dev/null \
        | grep -m 1 -oE ' cur=[0-9]+x[0-9]+' | sed 's/.*=//; s/x/ /' || true
}
