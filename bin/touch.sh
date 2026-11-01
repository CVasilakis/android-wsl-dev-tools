#!/usr/bin/env bash
# Touches the screen of an emulator or device from the terminal or a script: taps, long presses,
# swipes, drags, and two-finger pinches and rotations, the same on every API level.
#
# Usage:   touch.sh [-s <serial>] <gesture> <arguments>     (touch.sh --help lists them)
# Target:  the serial given, else $ANDROID_SERIAL, else the only running emulator. Phones connected
#          at the same time are only used when named, so a gesture never goes to one by accident.
#
# Each gesture is played by a small program of ours on the device (lib/Gesture.java, built into
# lib/Gesture.dex), as the shell user, through app_process, not by `adb shell input`: each `input`
# call is a process of its own, too slow for a double tap; it has one finger; and before API 24 it
# can't hold a touch and then move it. The program goes to /data/local/tmp the first time, under a
# name that holds its checksum, and stays there, so only the first gesture pays for the push; a
# factory reset removes it.
#
# Android sees these touches as a touchscreen's (it can't tell them from a finger's, except that
# they're marked as injected), and hands them to whichever window is under them, so a screen in
# front of the app gets them instead.
#
# Troubleshooting:
#   "several emulators are running"  -> name one: touch.sh -s emulator-5554 ...
#   "the gesture failed"             -> the program's output follows; the device may be busy or gone
set -uo pipefail

usage() {
    cat <<'EOF'
Usage: touch.sh [-s <serial>] <gesture> <arguments>

Touches the screen of an emulator or device, the same on every API level. Coordinates are pixels
of the screen as it's turned now, or percentages of it (50%), which fit any screen.

  tap <x> <y>                          a short touch
  double-tap <x> <y>                   two quick ones
  long-press <x> <y> [ms]              a touch held (default: twice the device's long-press timeout)
  swipe <x1> <y1> <x2> <y2> [ms]       a touch moving at an even speed (default: 300); a short
                                       time is a fling (e.g. 80)
  drag <x1> <y1> <x2> <y2> [ms]        long-press, move, then let go at rest (default: 600 for
                                       the move)
  pinch <x> <y> <from> <to> [ms]       two fingers level with (x, y), <from> px apart at first and
                                       <to> at the end: less to zoom out, more to zoom in
                                       (default: 500)
  rotate <x> <y> <distance> <degrees> [ms]
                                       two fingers <distance> px apart turning round (x, y),
                                       clockwise for positive degrees (default: 500)

  -s <serial>  the device, e.g. emulator-5554. Default: $ANDROID_SERIAL, else the only running
               emulator
  -h, --help   show this help

A percentage of a distance is of the screen's width. Exits 0 once the app has handled the last
touch, 1 if the gesture failed, 2 for wrong arguments.
EOF
}

SERIAL=""
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    -s)        [ $# -ge 2 ] || { usage >&2; exit 2; }
               SERIAL="$2"; shift 2 ;;
esac
[ $# -ge 1 ] || { usage >&2; exit 2; }
GESTURE="$1"
shift

# Checks the arguments' number and form before anything reaches the device: <at least> <at most>
# arguments; the last one, when given beyond <at least>, is a time in ms.
check_args() {
    local least="$1" most="$2" value
    shift 2
    if [ $# -lt "$least" ] || [ $# -gt "$most" ]; then usage >&2; exit 2; fi
    for value in "$@"; do
        [[ "$value" =~ ^-?[0-9]+(\.[0-9]+)?%?$ ]] || { usage >&2; exit 2; }
    done
    if [ $# -gt "$least" ] && ! [[ "${*: -1}" =~ ^[0-9]+$ ]]; then usage >&2; exit 2; fi
}
case "$GESTURE" in
    tap|double-tap) check_args 2 2 "$@" ;;
    long-press)     check_args 2 3 "$@" ;;
    swipe|drag)     check_args 4 5 "$@" ;;
    pinch)          check_args 4 5 "$@" ;;
    rotate)         check_args 4 5 "$@"
                    [[ "$4" != *% ]] || { usage >&2; exit 2; } ;;
    *)              usage >&2; exit 2 ;;
esac

LIB_DIR="$(dirname "$(readlink -f "$0")")/../lib"
# shellcheck source=../lib/sdk.sh
source "$LIB_DIR/sdk.sh"
# shellcheck source=../lib/device.sh
source "$LIB_DIR/device.sh"
require "$ADB" "platform-tools"
SERIAL="$(pick_device "$SERIAL")" || exit 1
ADB=("$ADB" -s "$SERIAL")

# pixels <value> <size>: a coordinate in pixels, from pixels or a percentage of <size>.
pixels() {
    if [[ "$1" == *% ]]; then awk -v v="${1%\%}" -v s="$2" 'BEGIN { printf "%d", v * s / 100 }'
    else echo "$1"; fi
}

# x_of and y_of turn percentages into pixels, once the screen's size is known
# (screen_size, device.sh, is only asked when a percentage needs it).
WIDTH=""
HEIGHT=""
need_screen() {
    [[ "$*" == *%* ]] && [ -z "$WIDTH" ] || return 0
    read -r WIDTH HEIGHT < <(screen_size "$SERIAL") || true
    [ -n "$WIDTH" ] || die "couldn't read the screen's size from $SERIAL."
}
x_of() { pixels "$1" "$WIDTH"; }
y_of() { pixels "$1" "$HEIGHT"; }

# hold_time: how long a touch must stay for Android to take it as a long press, with room to spare:
# twice the device's long-press timeout (500 ms when unset). The setting decides, not a fixed time:
# an accessibility setting can change it.
hold_time() {
    local timeout
    timeout="$("${ADB[@]}" shell settings get secure long_press_timeout < /dev/null 2>/dev/null \
        | tr -d '\r')"
    [[ "$timeout" =~ ^[0-9]+$ ]] || timeout=500
    echo $((2 * timeout))
}

# play <ms> <arguments of Gesture>: runs the program on the device, pushing it first if it isn't
# there yet. <ms> is how long the gesture takes, added to adb's time limit.
# - `timeout`: a gesture that hangs on a device starved of CPU must not hang the script.
# - Before API 24 `adb shell` doesn't pass on exit statuses, so success is read from the output.
# - </dev/null: `adb shell` forwards its stdin, which would swallow what a calling script feeds on.
play() {
    local ms="$1" dex name device_dex output limit
    shift
    dex="$LIB_DIR/Gesture.dex"
    name="$(cksum < "$dex" | awk '{ print $1 }')"
    device_dex="/data/local/tmp/awdt-gesture-$name.dex"
    limit=$((ADB_TIMEOUT + ms / 1000 + 1))
    output="$(timeout -k 5 "$limit" "${ADB[@]}" shell "if [ -f $device_dex ]; then \
CLASSPATH=$device_dex app_process /system/bin Gesture $*; else echo not-pushed; fi" \
        < /dev/null 2>&1)"
    if [[ "$output" == *not-pushed* ]]; then
        "${ADB[@]}" push "$dex" "$device_dex" < /dev/null > /dev/null 2>&1 \
            || die "couldn't push the gesture program to $SERIAL."
        output="$(timeout -k 5 "$limit" "${ADB[@]}" shell \
            "CLASSPATH=$device_dex app_process /system/bin Gesture $*" < /dev/null 2>&1)"
    fi
    if ! grep -q "Events injected: [1-9]" <<<"$output"; then
        echo "touch.sh: the gesture failed on $SERIAL:" >&2
        tr -d '\r' <<<"${output:-adb gave no answer}" | grep -v '^[[:space:]]*$' | tail -n 5 >&2
        exit 1
    fi
}

need_screen "$@"
case "$GESTURE" in
    tap|double-tap)
        play 500 "$GESTURE" "$(x_of "$1")" "$(y_of "$2")" ;;
    long-press)
        ms="${3:-$(hold_time)}"
        play "$ms" hold "$(x_of "$1")" "$(y_of "$2")" "$ms" ;;
    swipe)
        ms="${5:-300}"
        play "$ms" swipe "$(x_of "$1")" "$(y_of "$2")" "$(x_of "$3")" "$(y_of "$4")" "$ms" ;;
    drag)
        ms="${5:-600}"
        hold="$(hold_time)"
        play $((hold + ms)) drag "$(x_of "$1")" "$(y_of "$2")" "$(x_of "$3")" "$(y_of "$4")" \
            "$hold" "$ms" ;;
    pinch)
        ms="${5:-500}"
        play "$ms" pinch "$(x_of "$1")" "$(y_of "$2")" "$(x_of "$3")" "$(x_of "$4")" "$ms" ;;
    rotate)
        ms="${5:-500}"
        play "$ms" rotate "$(x_of "$1")" "$(y_of "$2")" "$(x_of "$3")" "$4" "$ms" ;;
esac
