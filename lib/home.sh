# shellcheck shell=bash
# shellcheck disable=SC2034  # the variables set here are used by the scripts that source this file
# Waiting for a booted device to settle on its home screen (start-emulator.sh --wait-for-home).
# Needs sdk.sh and device.sh.

# wait_for_home <serial> <seconds> [<backs>]: waits until a device has settled after its boot, which
# sys.boot_completed doesn't mean, and prints its home app's package. Settled is a state the device
# shows, seen at two looks in a row (the same activity record and the same window), not a time it
# has lasted: the top activity of `dumpsys activity activities` is in the home app's task, resumed
# and idle (Android's mark that it has finished starting: its main thread went idle after the
# resume, or 10 s passed), it's the focused activity (`dumpsys window`'s mFocusedApp), and its own
# window has the focus (mCurrentFocus; keys go only there, and on a device short of CPU none had
# it long after the boot). From API 24 on, the home app's task is the one of the activity a HOME
# intent resolves to, once that's no longer Settings' FallbackHome, which holds the screen until
# the user is unlocked. API 22 and 23 have neither `cmd` to ask nor FallbackHome: there it's a task
# a HOME intent started.
#
# What that counts: a screen the home app opens over itself, in its task, once it's on top, and on
# API 22 with another home app installed, Android's chooser (package android, in the task Home
# started). What it doesn't: a home app whose main thread is still busy after its resume. What no
# look can foresee is a screen the home app opens later of its own accord.
#
# Another app's screen can keep the focus, so when a window of another app than the home app's has
# kept the focus for BACK_AFTER s, once the user is unlocked, it presses Back, up to <backs> times
# (default 0: it only looks; never on a device someone may be using). Never on a screen of the home
# app's own: a Back there could end what the launcher is doing. After <seconds> (0: no limit) it
# prints what was in front instead, and fails (status 1).
#
# The long limit is for the device on its way to its home screen: the home app's own screens,
# FallbackHome, no focused window. Another app's
# screen is never on that way, so once the same window of another app has kept the focus for
# OTHER_APP_TIMEOUT s (after the Backs, if any), it prints what was in front and fails at once
# (status 2), rather than wait out <seconds> for a home app that can't come (an app left open on
# a device someone uses, a dialog that stays).
#
# Nor can a home app come when none is enabled (e.g. a stock launcher left disabled): from API 24
# on, once the user is unlocked, a HOME intent then still resolves to FallbackHome, which stays in
# front, so wait_for_home prints what was in front and fails at once (status 3) when, at two looks
# in a row, the user is unlocked and no activity but FallbackHome handles a HOME intent (no_home_app).
# Two looks, as an app being updated is missing from the query for a moment. Before API 24 there's
# no FallbackHome, and no `cmd` or other shell command that lists the enabled HOME activities, so
# there the wait for a home app that isn't enabled runs to <seconds>.
#
# BACK_AFTER is how long another app's screen must keep the focus to be taken as stuck: one that's
# only passing by while the device settles has left by then. AWDT_BACK_AFTER exists for the tests.
# OTHER_APP_TIMEOUT (AWDT_OTHER_APP_TIMEOUT; 0: none, only <seconds>) is far longer than any such
# passing screen (start-emulator.sh validates it).
BACK_AFTER="${AWDT_BACK_AFTER:-10}"
OTHER_APP_TIMEOUT="${AWDT_OTHER_APP_TIMEOUT:-60}"
wait_for_home() {
    local serial="$1" limit="$2" backs="${3:-0}" start=$SECONDS sdk="" resolved look settled=""
    local other="" other_since="" windows activities key window app homes package top shown
    local no_home=""
    while true; do
        [ -n "$sdk" ] || sdk="$(adb_bounded -s "$serial" shell getprop ro.build.version.sdk \
            < /dev/null 2>/dev/null | tr -d '\r' || true)"
        [[ "$sdk" =~ ^[0-9]+$ ]] || sdk=""
        resolved=""
        if [ -n "$sdk" ] && [ "$sdk" -ge 24 ]; then
            resolved="$(adb_bounded -s "$serial" shell cmd package resolve-activity --brief \
                -a android.intent.action.MAIN -c android.intent.category.HOME < /dev/null \
                2>/dev/null | tr -d '\r' | grep -E '^[[:alnum:]_.]+/[[:alnum:]_.$]+$' | tail -n 1 \
                || true)"
        fi
        windows="$(adb_bounded -s "$serial" shell dumpsys window < /dev/null 2>/dev/null \
            | tr -d '\r' || true)"
        activities="$(adb_bounded -s "$serial" shell dumpsys activity activities < /dev/null \
            2>/dev/null | tr -d '\r' || true)"
        mapfile -t look < <(home_look "${sdk:-0}" "$resolved" <(printf '%s\n' "$windows") \
            <(printf '%s\n' "$activities"))
        key="${look[1]:-}" app="${look[2]:-}" window="${look[3]:-}" homes="${look[4]:-}"
        package="${look[5]:-}" top="${look[6]:-}"
        shown="activity ${app:-none}, focused window ${window:-none}${resolved:+; a HOME intent \
resolves to $resolved}; the top activity is ${top:-none}"
        if [ -n "$sdk" ] && [ "$sdk" -ge 24 ] && [[ "$resolved" == */*FallbackHome ]] \
                && no_home_app "$serial"; then
            if [ -n "$no_home" ]; then echo "$shown"; return 3; fi
            no_home=1
        else
            no_home=""
        fi
        if [ -n "$sdk" ] && [ "${look[0]:-}" = 1 ]; then
            if [ "$key" = "$settled" ]; then echo "$package"; return 0; fi
            settled="$key"
            other=""
        else
            settled=""
            # The same window of another app than the home app's with the focus for BACK_AFTER s,
            # once the user is unlocked (from API 24 on, a HOME intent no longer resolves to
            # FallbackHome): Back. Without a focused window, a key would reach nothing.
            if [ -n "$window" ] && { [[ "$window" != */* ]] \
                    || [[ " $homes " != *" ${window%%/*} "* ]]; } && [ -n "$sdk" ] \
                    && { [ "$sdk" -lt 24 ] || { [ -n "$resolved" ] \
                    && [[ "$resolved" != *FallbackHome ]]; }; }; then
                if [ "$window" != "$other" ]; then
                    other="$window"
                    other_since=$SECONDS
                elif [ "$backs" -gt 0 ] && time_is_up "$other_since" "$BACK_AFTER"; then
                    adb_bounded -s "$serial" shell input keyevent BACK < /dev/null > /dev/null \
                        2>&1 || true
                    backs=$((backs - 1))
                    other=""
                elif [ "$OTHER_APP_TIMEOUT" -gt 0 ] \
                        && time_is_up "$other_since" "$OTHER_APP_TIMEOUT"; then
                    echo "$shown"
                    return 2
                fi
            else
                other=""
            fi
        fi
        if [ "$limit" -gt 0 ] && time_is_up "$start" "$limit"; then
            echo "$shown"
            return 1
        fi
        sleep 1
    done
}

# no_home_app <serial>: whether a device (API 24 on) has no home app to show: its user 0 is unlocked
# (`dumpsys user`'s "Started users state": {0=3} up to API 32, [0=RUNNING_UNLOCKED] from 33 on), and
# no activity but Settings' FallbackHome handles a HOME intent (`cmd package query-activities`).
# Until the user is unlocked, Android answers that query with the activities that can run before
# (direct boot aware ones, like FallbackHome) and leaves out every launcher, so the query alone
# can't tell. So it takes the user's state once fully unlocked, RUNNING_UNLOCKED, rather than an
# earlier sign (sys.user.0.ce_available is set seconds before it on a starved emulator, while the
# user is still unlocking). Any answer it doesn't understand counts as "no".
no_home_app() {
    local users
    users="$(adb_bounded -s "$1" shell dumpsys user < /dev/null 2>/dev/null | tr -d '\r')" \
        || return 1
    grep -Eq '^ *Started users state: .*[{[ ]0=(3|RUNNING_UNLOCKED)[]},]' <<< "$users" || return 1
    adb_bounded -s "$1" shell cmd package query-activities --components \
        -a android.intent.action.MAIN -c android.intent.category.HOME < /dev/null 2>/dev/null \
        | tr -d '\r' | awk '
            NF == 0 { next }
            { n++ }
            $0 == "No activities found" { next }
            !/^[[:alnum:]_.]+\/[[:alnum:]_.$]+$/ { unknown = 1; next }
            !/FallbackHome$/ { other = 1 }
            END { exit !(n && !unknown && !other) }'
}

# home_look <sdk> <home> <dumpsys window> <dumpsys activity activities>: one look at a device for
# wait_for_home, from those dumps (files) and from what a HOME intent resolves to (<home>, from API
# 24 on). Prints seven lines: 1 if the device shows its home screen as wait_for_home means it (else
# 0); the focused activity's record and window, which must stay the same; the focused activity; the
# focused window's title; the home app's packages; the package to name as the home app's; and the
# top activity, with its task, state and idle mark. The tests also ask it about another activity
# (Settings, or the focused one) as <home>, with <sdk> 24 on every API level
# (tests/support/front_look.py).
home_look() {
    awk -v sdk="$1" -v home="$2" '
        # The last focus lines: after an ANR, `dumpsys window` starts with a copy of the state at
        # that time (WINDOW MANAGER LAST ANR), focus included, and the live state comes after it.
        # mFocusedApp names an ActivityRecord{<hash> u0 <package>/<class> t<task>} (on API 33
        # ...<class>} t<task>}), alone or inside a token (before API 29), or is null.
        # mCurrentFocus=Window{<hash> u0 <title>}, or null; the title of an activity window is
        # <package>/<full class name>.
        FILENAME == ARGV[1] {
            if ($0 ~ /^ *mFocusedApp=/) {
                record = ""; app = ""
                if (split_record($0)) { record = r_hash; app = r_comp }
            } else if ($0 ~ /^ *mCurrentFocus=/) {
                focus = $0; sub(/^ *mCurrentFocus=/, "", focus)
                title = ""
                if (focus ~ /^Window\{/) {
                    title = focus; sub(/^Window\{[^ ]* [^ ]* /, "", title); sub(/\}$/, "", title)
                }
            }
            next
        }
        # The activities, from the top down: each a "* Hist #<n>: ActivityRecord{...}" line (from
        # API 34 on with two spaces after Hist), then lines of its own, with its first "state=" and
        # "idle=". Before API 24, each task is "* TaskRecord{<hash> #<task> ...", then the
        # intent={...} that started it.
        /^ *\* TaskRecord\{/ { task = $3; gsub(/[^0-9]/, "", task) }
        /^ *intent=\{/ && /android\.intent\.category\.HOME/ { started_by_home[task] = 1 }
        /^ *\* Hist +#[0-9]+: ActivityRecord\{/ {
            if (split_record($0)) { n++; hash[n] = r_hash; comp[n] = r_comp; in_task[n] = r_task }
            next
        }
        n && state[n] == "" && /^ *state=/ { state[n] = $1; sub(/^state=/, "", state[n]) }
        n && idle[n] == "" && match($0, /(^| )idle=(true|false)/) {
            idle[n] = substr($0, RSTART, RLENGTH); sub(/.*=/, "", idle[n])
        }
        # Sets r_hash, r_comp and r_task from the last ActivityRecord{...} of a line.
        function split_record(line,   f) {
            if (line !~ /ActivityRecord\{/) return 0
            sub(/.*ActivityRecord\{/, "", line)
            split(line, f, " ")
            r_hash = f[1]; r_comp = f[3]; sub(/\}.*/, "", r_comp); r_task = f[4]
            gsub(/[^0-9]/, "", r_task)
            return r_comp ~ /\//
        }
        function package_of(c) { sub(/\/.*/, "", c); return c }
        # <package>/.Class as a window names it: <package>/<package>.Class.
        function full_name(c,   p, cls) {
            p = c; sub(/\/.*/, "", p); cls = c; sub(/^[^\/]*\//, "", cls)
            return p "/" (cls ~ /^\./ ? p cls : cls)
        }
        END {
            # The tasks of the home app: from API 24 on, those of the activity HOME resolves to;
            # before, those a HOME intent started. Its packages: the one HOME resolves to, or
            # before API 24 those of the activities in these tasks.
            for (i = 1; i <= n; i++) {
                if (sdk >= 24 ? (home != "" && home !~ /FallbackHome$/ && comp[i] == home) \
                        : (in_task[i] in started_by_home)) is_home[in_task[i]] = 1
            }
            if (sdk >= 24) homes = package_of(home)
            else for (i = 1; i <= n; i++) {
                p = package_of(comp[i])
                if ((in_task[i] in is_home) && index(" " homes " ", " " p " ") == 0)
                    homes = homes (homes == "" ? "" : " ") p
            }
            settled = n > 0 && (in_task[1] in is_home) && state[1] == "RESUMED" \
                && idle[1] == "true" && record == hash[1] && app == comp[1] \
                && title == full_name(comp[1])
            print (settled ? 1 : 0)
            print record " " focus
            print app
            print title
            print homes
            print (sdk >= 24 ? package_of(home) : package_of(comp[1]))
            if (n) print comp[1] " in task " in_task[1] ", " \
                (state[1] == "" ? "no state" : state[1]) ", " \
                (idle[1] == "true" ? "idle" : "not idle")
            else print ""
        }' "$3" "$4"
}
