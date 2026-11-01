#!/usr/bin/env bash
# Creates a phone or tablet emulator for developing and testing Android apps.
#
# Usage:   create-avd.sh [avd-name]              (default: $AWDT_AVD, else phone_api36)
#          create-avd.sh --api 30 [avd-name]     (default: phone_api30)
#          create-avd.sh --tablet --api 34       (default: tablet_api34)
#          create-avd.sh --google-apis --api 34  (with Google's apps; default: phone_gapi34)
#          create-avd.sh --device pixel_9_pro_fold --api 36   (any profile of `avdmanager list device`)
#          create-avd.sh --size 720x1280 --density 320 small_phone   (another screen)
#          create-avd.sh --if-missing [...]      (an existing AVD of that image is fine: CI caches)
#          create-avd.sh --help
# Result:  <avd-name>.avd and <avd-name>.ini in the folder the emulator looks for AVDs in
#          ($ANDROID_AVD_HOME if set, ~/.android/avd by default)
#
# Requires (see docs/SETUP.md): cmdline-tools, and the SDK packages "emulator" and
# "system-images;android-<level>;default;x86_64" (google_apis with --google-apis). sdk.sh describes
# how the SDK is found.
#
# Common errors:
#   'Error: "emulator" package must be installed!'
#       avdmanager refuses to create any AVD without the emulator package:
#       android sdk install --no-metrics "emulator"
#   'Package path is not valid' / 'Invalid --tag default for the selected package'
#       The system image is missing or incomplete. `android sdk list --no-metrics` must list it
#       (its folder must contain package.xml). The script prints the install command when the
#       image's folder is missing.
#   'AVD ... already exists'
#       Printed by this script on purpose; it never overwrites an AVD (that would wipe its data).
#       With --if-missing, an existing AVD made from the same system image is accepted instead
#       (exit 0, left as it is), so a script or CI job can run this every time. An AVD of the same
#       name from another image, or with another --size or --density than the ones given, is
#       still an error: it isn't the AVD that was asked for.
#   'Error: Could not load devices from .../devices.xml'
#       Harmless: images lack that file, avdmanager then uses its own device profiles. avdmanager
#       prints it for every AVD once such an image is installed.
#
# The hardware settings below are deliberate choices, each explained next to it, so don't drop one
# just because the emulator seems to start without it.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: create-avd.sh [--api <level>] [--google-apis] [--tablet] [--device <profile>]
                     [--size <W>x<H>] [--density <dpi>] [--if-missing] [avd-name]

Creates a phone or tablet emulator (AVD) for developing Android apps: a multi-touch screen, and
the PC's keyboard as a hardware keyboard. Never overwrites an existing AVD.

  --api <level>     Android API level (default: 36, Android 16), e.g. 24 (Android 7.0),
                    30 (Android 11) or 37 (Android 17)
  --google-apis     use the Google APIs image of that level instead of the plain one (AOSP):
                    with Google Play services and Google's apps
  --tablet          a tablet (medium_tablet) instead of a phone (medium_phone)
  --device <profile>
                    any other device profile, as `avdmanager list device -c` lists them,
                    e.g. pixel_9_pro_fold
  --size <W>x<H>    screen size in pixels (default: the profile's), e.g. 720x1280
  --density <dpi>   screen density (default: the profile's), e.g. 320
  --if-missing      if the AVD already exists and was made from the same system image (and
                    with the --size and --density given), leave it as it is and succeed
                    (for scripts and CI caches)
  avd-name          name of the new AVD. Default: phone_api<level> (phone_gapi<level> with
                    --google-apis; tablet_… with --tablet; <profile>_… with --device);
                    without --api, $AWDT_AVD comes first
  -h, --help        show this help

Needs the SDK packages "cmdline-tools;latest", "emulator" and
"system-images;android-<level>;default;x86_64" ("...;google_apis;x86_64" with --google-apis; see
docs/SETUP.md). The SDK is the first of: $ANDROID_HOME, $ANDROID_SDK_ROOT, sdk.dir in the
local.properties of the project you're in, the SDK of the adb on $PATH, ~/Android/Sdk. The AVD goes
where the emulator looks for AVDs ($ANDROID_AVD_HOME if set, ~/.android/avd by default).
EOF
}
API=""
AVD_NAME=""
IF_MISSING=""
WIDTH=""                                  # --size and --density; empty: the device profile's
HEIGHT=""
DENSITY=""
TAG=default                               # the system image's tag: default or google_apis
DEVICE=medium_phone
KIND=phone                                # what a default name starts with
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --api)     [[ "${2:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { usage >&2; exit 2; }
                   API="$2"; shift 2 ;;
        --google-apis) TAG=google_apis; shift ;;
        --tablet)  DEVICE=medium_tablet; KIND=tablet; shift ;;
        --device)  [[ "${2:-}" =~ ^[A-Za-z0-9._-]+$ ]] || { usage >&2; exit 2; }
                   DEVICE="$2"; KIND="$2"; shift 2 ;;
        --size)    [[ "${2:-}" =~ ^([1-9][0-9]*)x([1-9][0-9]*)$ ]] || { usage >&2; exit 2; }
                   WIDTH="${BASH_REMATCH[1]}"; HEIGHT="${BASH_REMATCH[2]}"; shift 2 ;;
        --density) [[ "${2:-}" =~ ^[1-9][0-9]*$ ]] || { usage >&2; exit 2; }
                   DENSITY="$2"; shift 2 ;;
        --if-missing) IF_MISSING=1; shift ;;
        -*)        usage >&2; exit 2 ;;
        *)         [ -z "$AVD_NAME" ] || { usage >&2; exit 2; }
                   AVD_NAME="$1"; shift ;;
    esac
done

LIB_DIR="$(dirname "$(readlink -f "$0")")/../lib"
# shellcheck source=../lib/sdk.sh
source "$LIB_DIR/sdk.sh"
# shellcheck source=../lib/avd.sh
source "$LIB_DIR/avd.sh"

# With --api, the default name follows the level: $AWDT_AVD usually names the everyday AVD, and an
# AVD of another level taking that name would be a surprise.
KIND_TAG=api
if [ "$TAG" = google_apis ]; then KIND_TAG=gapi; fi
if [ -n "$API" ]; then
    AVD_NAME="${AVD_NAME:-${KIND}_$KIND_TAG$API}"
else
    API="$DEFAULT_API"
    AVD_NAME="${AVD_NAME:-${AWDT_AVD:-${KIND}_$KIND_TAG$API}}"
fi

# The image's folder and package. From API 37 on a level's folder has a minor version, android-37.0
# (image_level, avd.sh), and x86_64 is the ABI every level has, except for one image of Google's.
LEVEL="$(image_level "$API" "$TAG")"
ABI="$(image_abi "$LEVEL" "$TAG")"
IMAGE="system-images;android-$LEVEL;$TAG;$ABI"
IMAGE_DIR="$SDK/system-images/android-$LEVEL/$TAG/$ABI"
require "$AVDMANAGER" "cmdline-tools;latest"
require "$EMULATOR" "emulator"

# Never overwrite an AVD: that would wipe its data. With --if-missing, one made from the same
# image counts as done (avd_image, avd.sh).
if existing="$(avd_dir "$AVD_NAME")"; then
    if [ -z "$IF_MISSING" ]; then
        die "AVD '$AVD_NAME' already exists ($existing). Delete it first with:
  $AVDMANAGER delete avd -n $AVD_NAME
or pass --if-missing to keep it."
    fi
    existing_image="$(avd_image "$existing")"
    existing_image="${existing_image%/}"
    if [ "$existing_image" != "${IMAGE//;//}" ]; then
        die "AVD '$AVD_NAME' already exists ($existing), but was made from
${existing_image:-an unknown system image}, not ${IMAGE//;//}. Pick another name, or delete it with:
  $AVDMANAGER delete avd -n $AVD_NAME"
    fi
    # Only the screen settings given are compared: without --size, any existing size is fine.
    existing_setting() {
        sed -n "s/^$1 *= *//p" "$existing/config.ini" | head -n 1 | tr -d '\r'
    }
    for pair in "hw.lcd.width=$WIDTH" "hw.lcd.height=$HEIGHT" "hw.lcd.density=$DENSITY"; do
        key="${pair%%=*}"; wanted="${pair#*=}"
        [ -n "$wanted" ] || continue
        have="$(existing_setting "$key")"
        if [ "$have" != "$wanted" ]; then
            die "AVD '$AVD_NAME' already exists ($existing), but its $key is ${have:-not set}, not
$wanted. Pick another name, or delete it with:
  $AVDMANAGER delete avd -n $AVD_NAME"
        fi
    done
    echo "AVD '$AVD_NAME' already exists ($existing), made from $IMAGE; left as it is."
    exit 0
fi

# The AVD goes in the folder the emulator looks in (the first of avd_homes), and avdmanager is
# told so through ANDROID_AVD_HOME. Left to itself, avdmanager can pick another one: cmdline-tools
# 12.0 (on GitHub's runners) uses $XDG_CONFIG_HOME/.android/avd when XDG_CONFIG_HOME is set, and
# the emulator never finds the AVD there. That avdmanager ignores ANDROID_AVD_HOME while the
# folder doesn't exist, so it's created first.
read -r AVD_HOME < <(avd_homes)
mkdir -p "$AVD_HOME"

# avdmanager asks "Do you wish to create a custom hardware profile? [no]" interactively;
# piping 'no' keeps the script non-interactive. --tag/--abi are explicit so avdmanager fails
# loudly instead of guessing if the image layout ever changes. avdmanager's own error for a missing
# image lists every image it knows instead of naming the package to install, so the install
# command is added when the image's folder isn't there.
if ! echo no | ANDROID_AVD_HOME="$AVD_HOME" "$AVDMANAGER" create avd \
    --name "$AVD_NAME" \
    --package "$IMAGE" \
    --tag "$TAG" \
    --abi "$ABI" \
    --device "$DEVICE"; then
    if [ ! -f "$IMAGE_DIR/package.xml" ]; then
        die "avdmanager failed: the system image isn't installed in $SDK. Install it with:
  $(install_hint "$IMAGE")"
    fi
    die "avdmanager failed (see above). A device profile must be one of: avdmanager list device -c"
fi

# avdmanager has no flags for hardware settings, so config.ini is patched directly. Where
# avdmanager put the AVD depends on the user's environment variables; avd_dir finds it.
AVD_DIR="$(avd_dir "$AVD_NAME")" || die "created '$AVD_NAME', but found no $AVD_NAME.ini in any of:
$(avd_homes)
Set \$ANDROID_AVD_HOME to the folder avdmanager uses, then run this script again."
CONFIG="$AVD_DIR/config.ini"
# set_prop replaces an existing key or appends it, so re-running it is harmless.
set_prop() {
    if grep -q "^$1=" "$CONFIG"; then
        sed -i "s|^$1=.*|$1=$2|" "$CONFIG"
    else
        echo "$1=$2" >> "$CONFIG"
    fi
}
set_prop hw.keyboard yes                  # expose the PC keyboard to Android as a hardware keyboard:
                                          # typing into a field needs no soft keyboard
set_prop hw.ramSize 2048                  # enough for a test app; more starves Gradle on a small host
set_prop hw.cpu.ncore 4
set_prop disk.dataPartition.size 4G       # the image's default userdata can be too small for many test apps
set_prop hw.gpu.enabled yes
set_prop hw.gpu.mode "$GPU_MODE"            # see sdk.sh; start-emulator.sh passes -gpu too, unless you pass your own
set_prop showDeviceFrame no               # no device skin around the screen
set_prop hw.audioInput no                 # no microphone needed
# --size/--density replace the device profile's screen. No skin is set, so the emulator window
# takes hw.lcd.* as they are.
if [ -n "$WIDTH" ]; then
    set_prop hw.lcd.width "$WIDTH"
    set_prop hw.lcd.height "$HEIGHT"
fi
if [ -n "$DENSITY" ]; then set_prop hw.lcd.density "$DENSITY"; fi

echo "Created AVD '$AVD_NAME' in $AVD_DIR. Start it with: $(command_for start-emulator.sh) $AVD_NAME"
