#!/usr/bin/env bash
# Sets an emulator's sensors from the terminal or a script: tilts the virtual device, at once or
# smoothly over a time, or gives any sensor values of its own. The same on every API level.
#
# Usage:   mobile-sensor.sh [-s <serial>] <command> <arguments>     (mobile-sensor.sh --help lists them)
# Target:  the serial given, else $ANDROID_SERIAL, else the only running emulator. Only an emulator:
#          the sensors are set through its console (`adb emu sensor`), which a phone doesn't have.
#
# The console sets one sensor at a time, and doesn't keep the others in line with it, so `tilt`
# works out every motion sensor the emulator has from one attitude, and sets them all together:
# gravity, Earth's magnetic field and the deprecated orientation sensor as a device held that way
# sees them, and the gyroscope's rate of turn while it moves. They all go in one `adb emu` call, one
# command per line: the console answers each in turn, and the call costs about as much as a single
# command, so a smooth move can take a step every AWDT_SENSOR_STEP_MS. The steps follow the clock,
# not a count: on a slow host there are fewer of them, and the move still takes the time asked.
# The magnetic field is the emulator's own (as its resting values show), with the device's top
# edge towards magnetic north.
#
# What the console doesn't check, and so is checked here before anything is sent: it takes fewer
# values than a sensor has and keeps the others, drops extra ones, and reads "1,5" as 1. It answers
# OK or KO for each command, while `adb emu` exits 0 either way, so success is read from the answers.
#
# Troubleshooting:
#   "... is not an emulator"     -> only an emulator's sensors can be set: name one with -s
#   "the console of ... refused" -> its answer follows; mobile-sensor.sh status lists the sensors there are
set -uo pipefail

usage() {
    cat <<'EOF'
Usage: mobile-sensor.sh [-s <serial>] <command> <arguments>

Sets an emulator's sensors, as if the device were held or moved: tilts it, or gives any sensor
values of its own.

  status                       the sensors the emulator has: one per line, its name, then its values
  get <sensor>                 a sensor's values, e.g. "0 9.81 0" for acceleration
  set <sensor> <value>...      gives a sensor these values, as many as get shows
  tilt <pitch> <roll> [ms]     holds the device at this angle, in degrees from lying face up: pitch
                               raises its top edge (90: upright, facing you), roll lowers its right
                               edge. With ms, it turns there smoothly from where it is, in that
                               time. Sets every motion sensor, so that they agree.
  flat [ms]                    lying face up, screen to the sky: tilt 0 0

  -s <serial>  the emulator, e.g. emulator-5554. Default: $ANDROID_SERIAL, else the only running
               emulator
  -h, --help   show this help

  AWDT_SENSOR_STEP_MS  how often a smooth tilt sets the sensors, in ms (default: 20)

Values are in the units apps get: m/s² (acceleration), rad/s (gyroscope), µT (magnetic-field),
degrees (orientation). Exits 0 once the emulator has the values, 1 if it refused them or couldn't
be reached, 2 for wrong arguments.
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

# The arguments' number and form, before anything reaches the device. Numbers are decimals, with an
# exponent if need be, as the console reads them and as `get` shows tiny ones (1e-05), so that what
# get prints can be set again; a sensor's name is the console's.
NUMBER='^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$'
check_numbers() {
    local value
    for value in "$@"; do [[ "$value" =~ $NUMBER ]] || { usage >&2; exit 2; }; done
}
check_ms() {
    [ $# -eq 0 ] || [[ "$1" =~ ^[0-9]+$ ]] || { usage >&2; exit 2; }
}
check_sensor() {
    [[ "$1" =~ ^[a-z][a-z0-9-]*$ ]] || { usage >&2; exit 2; }
}
case "$COMMAND" in
    status) [ $# -eq 0 ] || { usage >&2; exit 2; } ;;
    get)    [ $# -eq 1 ] || { usage >&2; exit 2; }
            check_sensor "$1" ;;
    set)    [ $# -ge 2 ] || { usage >&2; exit 2; }
            check_sensor "$1"
            check_numbers "${@:2}" ;;
    tilt)   [ $# -eq 2 ] || [ $# -eq 3 ] || { usage >&2; exit 2; }
            check_numbers "$1" "$2"
            check_ms "${@:3}" ;;
    flat)   [ $# -le 1 ] || { usage >&2; exit 2; }
            check_ms "$@" ;;
    *)      usage >&2; exit 2 ;;
esac

LIB_DIR="$(dirname "$(readlink -f "$0")")/../lib"
# shellcheck source=../lib/sdk.sh
source "$LIB_DIR/sdk.sh"
# shellcheck source=../lib/device.sh
source "$LIB_DIR/device.sh"
STEP_MS="${AWDT_SENSOR_STEP_MS:-20}"
[[ "$STEP_MS" =~ ^[1-9][0-9]*$ ]] \
    || die "AWDT_SENSOR_STEP_MS must be a number of milliseconds, not '$STEP_MS'."
require "$ADB" "platform-tools"
SERIAL="$(pick_device "$SERIAL")" || exit 1
[[ "$SERIAL" =~ ^emulator-[0-9]+$ ]] \
    || die "$SERIAL is not an emulator: only an emulator's sensors can be set. Name one with -s <serial>."

# console <command>...: sends the commands to the emulator's console in one call, one per line, and
# prints the lines it answered with, without the OK that ends each answer. Fails (exit 1), with the
# console's answer on stderr, if any of them didn't get its OK (each answer ends with OK or KO);
# called in $(...), the caller must then exit too.
console() {
    local text answer what="'$1'"
    [ $# -eq 1 ] || what="one of $# commands"
    text="$(printf '%s\n' "$@")"
    answer="$(adb_bounded -s "$SERIAL" emu "$text" 2>&1 | tr -d '\r')"
    if [ "$(grep -c '^OK$' <<<"$answer")" -ne $# ]; then
        echo "mobile-sensor.sh: the console of $SERIAL refused $what:" >&2
        grep -v '^OK$' <<<"${answer:-adb gave no answer}" | grep -v '^[[:space:]]*$' | tail -n 5 >&2
        exit 1
    fi
    grep -v '^OK$' <<<"$answer" || true
}

# values <sensor>...: each sensor's values, as "<name> <value> <value>...", one line each. The
# console says "<name> = <a>:<b>:<c>".
values() {
    console "${@/#/sensor get }" | sed -n 's/^\([^ ]*\) = /\1 /p' | tr ':' ' '
}

# enabled_sensors: the names of the sensors the emulator has enabled. The console says
# "<name>: enabled." or "<name>: disabled." for each one it knows.
enabled_sensors() {
    console "sensor status" | sed -n 's/^\([^:]*\): enabled\.$/\1/p'
}

# The motion sensors `tilt` sets, those of them the emulator has.
MOTION=(acceleration acceleration-uncalibrated gyroscope gyroscope-uncalibrated magnetic-field
        magnetic-field-uncalibrated orientation)
motion_sensors() {
    local enabled name
    enabled=" $(enabled_sensors | tr '\n' ' ') " || exit 1
    [[ "$enabled" == *" acceleration "* ]] || die "$SERIAL has no acceleration sensor to tilt."
    for name in "${MOTION[@]}"; do
        if [[ "$enabled" == *" $name "* ]]; then echo "$name"; fi
    done
}

# attitude <pitch> <roll> <pitch rate> <roll rate> <sensor>...: the console commands that set
# each of these sensors as a device held at that attitude sees it, turning at those rates (degrees,
# degrees per second). The attitude is lying face up turned by pitch about the screen's x axis
# (raising its top edge), then by roll about its own y axis (lowering its right edge): its rotation
# R = Rx(pitch) Ry(roll) takes the device's axes to the world's (east, north, up), so a world
# vector seen from the device is R's transpose times it, the rows of R weighted by its parts.
# - Gravity: the accelerometer reads 9.81 m/s² straight up, as at rest the emulator does.
# - Magnetic field: the emulator's own, 48.4 µT north and 5.9 µT up.
# - Gyroscope: the rate of turn in the device's axes, (pitch' cos roll, roll', pitch' sin roll).
# - Orientation (Sensor.TYPE_ORIENTATION): azimuth, pitch and roll as Android's own fused one
#   computes them from the up vector u: pitch atan2(-u.y, u.z), roll asin(u.x), in degrees.
attitude() {
    awk -v pitch="$1" -v roll="$2" -v pitch_rate="$3" -v roll_rate="$4" -v sensors="${*:5}" '
    function rad(d) { return d * PI / 180 }
    function deg(x) { return x * 180 / PI }
    function number(v) { v = sprintf("%.6g", v); return (v ~ /e-/ || v == "-0") ? 0 : v }
    function triple(a, b, c) { return number(a) ":" number(b) ":" number(c) }
    BEGIN {
        PI = atan2(0, -1)
        p = rad(pitch); r = rad(roll)
        # The rows of R: east, north and up, in the axes of the device.
        ex = cos(r);           ey = 0;      ez = sin(r)
        nx = sin(p) * sin(r);  ny = cos(p); nz = -sin(p) * cos(r)
        ux = -cos(p) * sin(r); uy = sin(p); uz = cos(p) * cos(r)
        value["acceleration"] = triple(9.81 * ux, 9.81 * uy, 9.81 * uz)
        value["magnetic-field"] = triple(48.4 * nx + 5.9 * ux, 48.4 * ny + 5.9 * uy, 48.4 * nz + 5.9 * uz)
        value["gyroscope"] = triple(rad(pitch_rate) * cos(r), rad(roll_rate), rad(pitch_rate) * sin(r))
        azimuth = deg(atan2(ey, ny)); if (azimuth < 0) azimuth += 360
        if (ux > 1) ux = 1; if (ux < -1) ux = -1
        value["orientation"] = triple(azimuth, deg(atan2(-uy, uz)), deg(atan2(ux, sqrt(1 - ux * ux))))
        value["acceleration-uncalibrated"] = value["acceleration"]
        value["gyroscope-uncalibrated"] = value["gyroscope"]
        value["magnetic-field-uncalibrated"] = value["magnetic-field"]
        n = split(sensors, names, " ")
        for (i = 1; i <= n; i++) print "sensor set " names[i] " " value[names[i]]
    }'
}

# route <ax> <ay> <az> <pitch> <roll>: where a move to (pitch, roll) starts, from the acceleration
# the emulator has now, and how far it turns: "<pitch> <roll> <pitch turn> <roll turn>". The same
# gravity comes from (pitch, roll) and (180 - pitch, roll + 180); the move starts from whichever
# needs the shorter turn, each angle the short way round. No gravity at all starts from lying flat.
route() {
    awk -v ax="$1" -v ay="$2" -v az="$3" -v pitch="$4" -v roll="$5" '
    function deg(x) { return x * 180 / PI }
    function floor(x) { return x == int(x) ? x : (x < 0 ? int(x) - 1 : int(x)) }
    function wrap(d) { return d - 360 * floor((d + 180) / 360) }
    function abs(x) { return x < 0 ? -x : x }
    BEGIN {
        PI = atan2(0, -1)
        size = sqrt(ax * ax + ay * ay + az * az)
        p0 = 0; r0 = 0
        if (size > 1e-6) {
            uy = ay / size; if (uy > 1) uy = 1; if (uy < -1) uy = -1
            p0 = deg(atan2(uy, sqrt(1 - uy * uy))); r0 = deg(atan2(-ax, az))
        }
        dp = wrap(pitch - p0); dr = wrap(roll - r0)
        dp2 = wrap(pitch - (180 - p0)); dr2 = wrap(roll - (r0 + 180))
        if (abs(dp2) + abs(dr2) < abs(dp) + abs(dr)) { p0 = 180 - p0; r0 += 180; dp = dp2; dr = dr2 }
        print p0, r0, dp, dr
    }'
}

# now_us: the clock in microseconds, whatever the locale's decimal separator.
now_us() { echo "${EPOCHREALTIME//[!0-9]/}"; }

# tilt <pitch> <roll> [ms]: sets the motion sensors for that attitude; with ms, first moves there
# from the current one, a step every STEP_MS, each at the attitude its time on the clock calls for,
# with the gyroscope at the move's rate of turn. The last step is the attitude itself, at rest.
tilt() {
    local pitch="$1" roll="$2" ms="$((10#${3:-0}))" found start total next now elapsed
    local name ax ay az p0 r0 dp dr p r pitch_rate roll_rate
    local -a sensors commands
    found="$(motion_sensors)" || exit 1
    mapfile -t sensors <<<"$found"
    if [ "$ms" -gt 0 ]; then
        found="$(values acceleration)" || exit 1
        read -r name ax ay az <<<"$found"
        read -r p0 r0 dp dr <<<"$(route "$ax" "$ay" "$az" "$pitch" "$roll")"
        total=$((ms * 1000))
        start="$(now_us)"
        next="$start"
        while elapsed=$(($(now_us) - start)); [ "$elapsed" -lt "$total" ]; do
            read -r p r pitch_rate roll_rate <<<"$(awk -v p0="$p0" -v r0="$r0" -v dp="$dp" \
                -v dr="$dr" -v t="$elapsed" -v total="$total" 'BEGIN { f = t / total
                    printf "%.6f %.6f %.6f %.6f\n", p0 + f * dp, r0 + f * dr, dp * 1e6 / total,
                        dr * 1e6 / total }')"
            mapfile -t commands <<<"$(attitude "$p" "$r" "$pitch_rate" "$roll_rate" "${sensors[@]}")"
            console "${commands[@]}" > /dev/null || exit 1
            next=$((next + STEP_MS * 1000))
            [ "$next" -le $((start + total)) ] || next=$((start + total))
            now="$(now_us)"
            if [ "$now" -lt "$next" ]; then
                sleep "$(printf '%d.%06d' $(((next - now) / 1000000)) $(((next - now) % 1000000)))"
            else
                next="$now"
            fi
        done
    fi
    mapfile -t commands <<<"$(attitude "$pitch" "$roll" 0 0 "${sensors[@]}")"
    console "${commands[@]}" > /dev/null || exit 1
}

case "$COMMAND" in
    status)
        found="$(enabled_sensors)" || exit 1
        [ -z "$found" ] && exit 0
        mapfile -t names <<<"$found"
        values "${names[@]}" || exit 1 ;;
    get)
        found="$(values "$1")" || exit 1
        echo "${found#* }" ;;
    set)
        sensor="$1"
        shift
        have="$(values "$sensor" | wc -w)" || exit 1
        [ "$((have - 1))" -eq $# ] \
            || die "$sensor takes $((have - 1)) values, not $#: $(command_for mobile-sensor.sh) get $sensor shows them."
        console "sensor set $sensor $(IFS=:; echo "$*")" > /dev/null ;;
    tilt)
        tilt "$@" ;;
    flat)
        tilt 0 0 "$@" ;;
esac
