#!/usr/bin/env bash
# Builds Gesture.dex from Gesture.java: the program mobile-touch.sh runs on a device. Run it after changing
# Gesture.java, and commit both. Needs a JDK's javac and, from the Android SDK (found as the other
# scripts find it), build-tools' d8 and a platform's android.jar.
set -euo pipefail
LIB_DIR="$(dirname "$(readlink -f "$0")")"
# shellcheck source=sdk.sh
. "$LIB_DIR/sdk.sh"

d8="$(printf '%s\n' "$SDK"/build-tools/*/d8 | sort -V | tail -n 1)"
jar="$(printf '%s\n' "$SDK"/platforms/android-*/android.jar | sort -V | tail -n 1)"
[ -e "$d8" ] || die "no d8 under $SDK/build-tools: build something with Gradle once, or install build-tools"
[ -e "$jar" ] || die "no android.jar under $SDK/platforms: install a platform"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
javac --release 8 -Xlint:-options -cp "$jar" -d "$work" "$LIB_DIR/Gesture.java"
"$d8" --min-api 21 --output "$work" "$work"/Gesture*.class
cp "$work/classes.dex" "$LIB_DIR/Gesture.dex"
echo "Built $LIB_DIR/Gesture.dex ($(wc -c < "$LIB_DIR/Gesture.dex") bytes)"
