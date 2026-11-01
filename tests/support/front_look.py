"""home_look for another activity than the home app's, for tests that wait until an activity has
settled in front."""
import os
import subprocess
import tempfile

from support.sandbox import LIB


def front_look(windows, activities, activity=""):
    """home.sh's home_look, what wait_for_home decides by, for another activity than the home
    app's: whether `activity` (as `cmd package resolve-activity --brief` names it; default: the
    focused activity) is at the top, in its task, resumed and idle (done starting), the focused
    activity, and its own window has the focus, from a `dumpsys window` and a `dumpsys activity
    activities`. home_look is given API level 24, at which it takes the task of the activity it's
    given for the home app's, on every API level. Returns (settled, key: the focused activity's
    record and window, which must stay the same, the focused activity, what to show in a
    failure)."""
    with tempfile.TemporaryDirectory() as folder:
        files = [os.path.join(folder, name) for name in ("window", "activities")]
        for name, dump in zip(files, (windows, activities)):
            with open(name, "w") as f:
                f.write(dump.replace("\r", ""))   # adb adds \r before API 24
        look = subprocess.run(
            ["bash", "-c", f'source {LIB / "home.sh"}\nhome_look 24 "${{1:-$(home_look 24 "" "$2" "$3" '
             '| sed -n 3p)}" "$2" "$3"', "bash", activity, *files],
            capture_output=True, text=True, timeout=60).stdout.split("\n")
    settled, key, app, window, _, _, top = (look + [""] * 7)[:7]
    return (settled == "1", key, app,
            f"focused activity {app or 'none'}, focused window {window or 'none'}, top activity "
            f"{top or 'none'}")
