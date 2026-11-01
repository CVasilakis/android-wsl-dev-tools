#!/usr/bin/env bash
# Builds TouchProbe.apk from this folder: the app the emulator tier installs. Run it after changing
# anything here, and commit the result. Needs a JDK and, from the Android SDK (found as the scripts
# find it), build-tools' aapt2, d8, zipalign and apksigner and a platform's android.jar.
# No Gradle, as the app has no dependencies and the tier must not need a Gradle project. The APK is
# signed with a key made here and thrown away: nothing depends on who signed it, the tier uninstalls
# the app before it installs it.
set -euo pipefail
PROBE_DIR="$(dirname "$(readlink -f "$0")")"
# shellcheck source=../../../lib/sdk.sh
. "$PROBE_DIR/../../../lib/sdk.sh"

newest() { printf '%s\n' "$@" | sort -V | tail -n 1; }
tools="$(dirname "$(newest "$SDK"/build-tools/*/aapt2)")"
jar="$(newest "$SDK"/platforms/android-*/android.jar)"
[ -x "$tools/aapt2" ] || die "no aapt2 under $SDK/build-tools: install build-tools"
[ -f "$jar" ] || die "no android.jar under $SDK/platforms: install a platform"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/res" "$work/java" "$work/classes"
"$tools/aapt2" compile --dir "$PROBE_DIR/res" -o "$work/res/compiled.zip"
"$tools/aapt2" link -I "$jar" --manifest "$PROBE_DIR/AndroidManifest.xml" --java "$work/java" \
    -o "$work/probe.apk" "$work/res/compiled.zip"
javac --release 8 -Xlint:-options -cp "$jar" -d "$work/classes" \
    "$work/java/awdt/probe/R.java" "$PROBE_DIR/src/awdt/probe/ProbeActivity.java"
find "$work/classes" -name '*.class' -print0 | xargs -0 "$tools/d8" --min-api 21 --lib "$jar" --output "$work"
(cd "$work" && python3 -I -c "import zipfile; z = zipfile.ZipFile('probe.apk', 'a'); z.write('classes.dex'); z.close()")
"$tools/zipalign" -f 4 "$work/probe.apk" "$work/aligned.apk"
keytool -genkeypair -keystore "$work/key" -storepass probe-key -alias probe -keyalg RSA \
    -keysize 2048 -validity 36500 -dname CN=probe 2> /dev/null
"$tools/apksigner" sign --ks "$work/key" --ks-pass pass:probe-key --out "$PROBE_DIR/../TouchProbe.apk" \
    "$work/aligned.apk"
rm -f "$PROBE_DIR/../TouchProbe.apk.idsig"
echo "Built $(readlink -f "$PROBE_DIR/../TouchProbe.apk") ($(wc -c < "$PROBE_DIR/../TouchProbe.apk") bytes)"
