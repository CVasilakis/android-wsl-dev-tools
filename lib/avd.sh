# shellcheck shell=bash
# shellcheck disable=SC2034  # the variables set here are used by the scripts that source this file
# The AVDs on this machine: where they live, what they were made from. Needs sdk.sh.

# The folders AVDs can live in, in the order the emulator and avdmanager look at them.
avd_homes() {
    [ -n "${ANDROID_AVD_HOME:-}" ] && echo "$ANDROID_AVD_HOME"
    [ -n "${ANDROID_EMULATOR_HOME:-}" ] && echo "$ANDROID_EMULATOR_HOME/avd"
    [ -n "${ANDROID_USER_HOME:-}" ] && echo "$ANDROID_USER_HOME/avd"
    [ -n "${ANDROID_SDK_HOME:-}" ] && echo "$ANDROID_SDK_HOME/.android/avd"
    echo "$HOME/.android/avd"
}

# Prints the <name>.avd folder of an existing AVD (the one holding config.ini); fails if none.
# Each AVD has a <name>.ini next to it whose path= line says where its folder is.
avd_dir() {
    local home path
    while IFS= read -r home; do
        [ -f "$home/$1.ini" ] || continue
        path="$(sed -n 's/^path=//p' "$home/$1.ini" | tr -d '\r')"
        [ -d "$path" ] || path="$home/$1.avd"
        if [ -f "$path/config.ini" ]; then echo "$path"; return 0; fi
    done < <(avd_homes)
    return 1
}

# The system image an AVD folder (from avd_dir) was made from, as its config.ini's image.sysdir.1
# names it: system-images/android-36/default/x86_64/ ("key = value" once the emulator has
# rewritten the file). Empty if config.ini doesn't say.
avd_image() {
    sed -n 's/^image\.sysdir\.1 *= *//p' "$1/config.ini" | head -n 1 | tr -d '\r'
}

# Names of all AVDs, one per line. Newer emulators also print log lines here; drop them.
list_avds() {
    "$EMULATOR" -list-avds 2>/dev/null | grep -E '^[A-Za-z0-9._-]+$' || true
}

# The AVD create-avd.sh makes by default, which start-emulator.sh boots by default.
DEFAULT_API=36
DEFAULT_AVD="phone_api$DEFAULT_API"

# image_level <api> <tag>: the level as the SDK names an image's folder and package. From API 37 on
# Android's levels have a minor version, and the first release of a level is android-37.0; a level
# given with its minor version (36.1) is taken as it is. Below 37 a plain level is the folder's
# name; an installed folder wins, for a level that later gets the other form.
image_level() {
    if [[ "$1" == *.* ]] || [ -d "$SDK/system-images/android-$1/$2" ]; then echo "$1"
    elif [ -d "$SDK/system-images/android-$1.0/$2" ] || [ "$1" -ge 37 ]; then echo "$1.0"
    else echo "$1"; fi
}

# image_abi <level> <tag>: x86_64, the ABI every level has, except Google APIs on API 27, which
# Google publishes for x86 only.
image_abi() {
    if [ "$1" = 27 ] && [ "$2" = google_apis ]; then echo x86; else echo x86_64; fi
}
