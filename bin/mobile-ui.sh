#!/usr/bin/env bash
# Sees what's on the screen of an emulator or device, and acts on it by what it says rather than by
# coordinates, so that a script or an agent can drive an app the way a person reads one.
#
# Usage:   mobile-ui.sh [-s <serial>] <command> <arguments>     (mobile-ui.sh --help lists them)
# Target:  as mobile-touch.sh: the serial given, else $ANDROID_SERIAL, else the only running emulator.
#
# It reads the screen with `uiautomator dump` (lib/ui_tree.py reads what that writes) and leaves
# gestures to mobile-touch.sh. `uiautomator dump` answers only once the screen has been idle for a moment,
# so on an animating screen it fails with "could not get idle state": each look tries again, for up
# to $AWDT_UI_TIMEOUT seconds. What uiautomator can't see: the inside of a WebView that doesn't
# publish its content, a game's canvas, a secure window. A screenshot (mobile-ui.sh shot) shows those.
#
# Troubleshooting:
#   "no element matches"              -> mobile-ui.sh list shows what's there; the screen may have moved on
#   "couldn't read the screen"        -> the screen keeps animating, or the device is gone
#   "several emulators are running"   -> name one: mobile-ui.sh -s emulator-5554 ...
set -uo pipefail

usage() {
    cat <<'EOF'
Usage: mobile-ui.sh [-s <serial>] <command> <arguments>

Sees what's on the screen of an emulator or device, and acts on it by what it says.

  list                       the elements on the screen, one per line
  front                      the activity in front, and the window with the focus
  shot <file.png>            save a screenshot
  find <selector>            print the center of an element, "<x> <y>"; exit 1 if there's none
  tap <selector>             tap an element
  long-press <selector>      long-press an element
  wait <selector> [s]        wait until an element shows (default: 30 s); exit 1 if it doesn't
  wait-gone <selector> [s]   wait until no element matches (default: 30 s); exit 1 if one stays
  type <text>                type text into the focused field (ASCII only)

A selector is text, found in an element's text or description, or one field: text:<text>,
desc:<description>, id:<resource id>, class:<class name>. Text ignores case; an element that holds
exactly that comes first, else one that contains it. Of several, the first in reading order.

  -s <serial>  the device, e.g. emulator-5554. Default: $ANDROID_SERIAL, else the only running
               emulator
  -h, --help   show this help

Environment:
  AWDT_UI_TIMEOUT  seconds one look at the screen keeps trying while it animates (default: 10)
EOF
}

SERIAL=""
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    -s)        [ $# -ge 2 ] || { usage >&2; exit 2; }
               SERIAL="$2"; shift 2 ;;
esac
[ $# -ge 1 ] || { usage >&2; exit 2; }
COMMAND="$1"
shift
case "$COMMAND" in
    list|front)         [ $# -eq 0 ] || { usage >&2; exit 2; } ;;
    shot|find|tap|long-press|type)
                        if [ $# -ne 1 ] || [ -z "$1" ]; then usage >&2; exit 2; fi ;;
    wait|wait-gone)     if [ $# -lt 1 ] || [ $# -gt 2 ] || [ -z "$1" ] \
                                || ! [[ "${2:-0}" =~ ^[0-9]+$ ]]; then usage >&2; exit 2; fi ;;
    *)                  usage >&2; exit 2 ;;
esac

LIB_DIR="$(dirname "$(readlink -f "$0")")/../lib"
# shellcheck source=../lib/sdk.sh
source "$LIB_DIR/sdk.sh"
# shellcheck source=../lib/device.sh
source "$LIB_DIR/device.sh"
require "$ADB" "platform-tools"
SERIAL="$(pick_device "$SERIAL")" || exit 1

UI_TIMEOUT="${AWDT_UI_TIMEOUT:-10}"
[[ "$UI_TIMEOUT" =~ ^[0-9]+$ ]] || die "AWDT_UI_TIMEOUT must be a number of seconds, not '$UI_TIMEOUT'."
DEVICE_DUMP=/data/local/tmp/awdt-ui.xml
DUMP="$(mktemp)"
trap 'rm -f "$DUMP"' EXIT

# read_screen: one `uiautomator dump` into $DUMP. Fails if there's no whole dump to read: the device
# answers "could not get idle state" while the screen animates.
read_screen() {
    adb_bounded -s "$SERIAL" shell "rm -f $DEVICE_DUMP; uiautomator dump $DEVICE_DUMP" \
        < /dev/null 2>&1 | grep 'dumped to' > /dev/null || return 1
    adb_bounded -s "$SERIAL" exec-out cat "$DEVICE_DUMP" < /dev/null > "$DUMP" 2>/dev/null \
        && python3 "$LIB_DIR/ui_tree.py" list "$DUMP" > /dev/null 2>&1
}

# look: read_screen, again and again while the screen animates, for up to UI_TIMEOUT s.
look() {
    local started=$SECONDS
    until read_screen; do
        time_is_up "$started" "$UI_TIMEOUT" && return 1
        sleep 0.5
    done
}

# look_or_die: look, or the end of the command, with why.
look_or_die() {
    look || die "couldn't read the screen of $SERIAL: it kept animating, or the device is gone."
}

# locate <selector>: prints "<x> <y>" of the element on the screen read last, then a line about it;
# fails if there's none.
locate() {
    python3 "$LIB_DIR/ui_tree.py" find "$DUMP" "$1"
}

# wait_for <selector> <seconds> <wanted>: until the element shows (wanted: 0, locate's status), or
# none does (1). A look that couldn't read the screen counts as "not yet".
wait_for() {
    local started=$SECONDS status
    while true; do
        if read_screen; then
            python3 "$LIB_DIR/ui_tree.py" find "$DUMP" "$1" > /dev/null 2>&1
            status=$?
            if [ "$status" -eq "$3" ]; then return 0; fi
        fi
        time_is_up "$started" "$2" && return 1
        sleep 0.5
    done
}

# touch_element <gesture> <selector>: the gesture, by mobile-touch.sh, on that element.
touch_element() {
    local place x y
    look_or_die
    place="$(locate "$2")" || die "no element matches '$2' on $SERIAL. See what's there: $(command_for mobile-ui.sh) list"
    read -r x y <<< "$place"
    "$BIN_DIR/mobile-touch.sh" -s "$SERIAL" "$1" "$x" "$y"
}

# type_text <text>: `adb shell input text`, which takes %s for a space. The text goes through the
# device's shell inside single quotes, so nothing in it is special there.
type_text() {
    local text="$1" quoted
    if LC_ALL=C grep -q '[^ -~]' <<< "$text"; then
        die "mobile-ui.sh type sends ASCII only: \`input text\` drops anything else."
    fi
    text="${text// /%s}"
    quoted="'${text//\'/\'\\\'\'}'"
    adb_bounded -s "$SERIAL" shell "input text $quoted" < /dev/null
}

case "$COMMAND" in
    list)
        look_or_die
        python3 "$LIB_DIR/ui_tree.py" list "$DUMP" ;;
    front)
        # The last of each: after an ANR, the dump starts with a copy of the state then, and API 29
        # names the focused app twice.
        adb_bounded -s "$SERIAL" shell dumpsys window < /dev/null | tr -d '\r' | awk '
            /^ *mCurrentFocus=/ { focus = $0 }
            /^ *mFocusedApp=/ { app = $0 }
            END {
                sub(/^ */, "", focus); sub(/^ */, "", app)
                if (focus != "") print focus
                if (app != "") print app
            }' ;;
    shot)
        adb_bounded -s "$SERIAL" exec-out screencap -p < /dev/null > "$1" \
            || die "couldn't take a screenshot of $SERIAL."
        echo "$1" ;;
    find)
        look_or_die
        locate "$1" | head -n 1
        exit "${PIPESTATUS[0]}" ;;
    tap)
        touch_element tap "$1" ;;
    long-press)
        touch_element long-press "$1" ;;
    wait)
        wait_for "$1" "${2:-30}" 0 || die "no element matched '$1' on $SERIAL within ${2:-30} s." ;;
    wait-gone)
        wait_for "$1" "${2:-30}" 1 || die "an element still matches '$1' on $SERIAL after ${2:-30} s." ;;
    type)
        type_text "$1" ;;
esac
