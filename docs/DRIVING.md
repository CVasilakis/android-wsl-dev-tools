# Driving an emulator

Using a running emulator from the window, a terminal, a script or a coding agent: touching it,
typing into it, seeing what it shows. Getting one running: [`EMULATORS.md`](EMULATORS.md). The
commands' options are in their `--help`.

Everything here works the same on every [tested image](EMULATORS.md#tested-images). With several
devices connected, name one with `-s <serial>`, or set `ANDROID_SERIAL` to the serial
`start-emulator.sh` prints.

## Touch

| Gesture | In the window | From a script |
|---|---|---|
| Tap | Click | `touch.sh tap 540 1200` |
| Double tap | Double click | `touch.sh double-tap 540 1200` |
| Long press | Hold the button | `touch.sh long-press 540 1200` |
| Swipe, fling | Drag; a quick one flings | `touch.sh swipe 200 1800 200 600`, with a short time for a fling: `… 80` |
| Drag and drop | Hold, then drag | `touch.sh drag 300 500 800 1500` |
| Pinch | Hold Ctrl and drag | `touch.sh pinch 540 1200 300 800` |
| Rotate with two fingers | Hold Ctrl and drag round | `touch.sh rotate 540 1200 500 90` |

**In the window** the mouse is a finger on the emulator's own touchscreen, wherever the window is
and whatever size it has: the emulator scales the screen to fit the display, and scales the
pointer back.

**Coordinates** are the screen's pixels as it's turned now, or percentages of it, which fit every
screen: `touch.sh tap 50% 75%`. In a pinch or a rotation, a percentage of a distance is of the
screen's width. Find a place with [`ui.sh`](#seeing-the-screen) rather than by measuring a
screenshot, whose scale may differ from the screen's.

**How it works.** `touch.sh` plays each gesture with a small program of ours on the device
([`lib/Gesture.java`](../lib/Gesture.java)), one mechanism on every API level. `adb shell input`
can't do this: each of its calls is a process of its own, too slow for a double tap; it has one
finger; and on the oldest levels it can't hold a touch and then move it. The program stays in
`/data/local/tmp` after the first gesture, so later ones skip the push. Each gesture still starts a
process on the device, so it can't follow another within a fraction of a second.

A touch goes to whichever window is under it, as a finger's does: a dialog over the app gets it
instead. `touch.sh` returns once the app has handled the last touch.

## Seeing the screen

```bash
ui.sh list                     # the elements on the screen, one per line
ui.sh find "Sign in"           # the center of an element: 540 1320
ui.sh tap "Sign in"            # tap it
ui.sh tap id:login_button      # the same, by resource id
ui.sh long-press "Photo 3"     # long-press it
ui.sh wait "Welcome" 30        # until it shows; fails after 30 s
ui.sh wait-gone "Loading"      # until it's gone
ui.sh front                    # the activity in front, and the window with the focus
ui.sh shot screen.png          # a screenshot
```

A selector is text, found in an element's text or description, or one field: `text:`, `desc:`,
`id:` (the whole resource id, or the part after `:id/`), `class:` (the whole name, or its last
part). Text ignores case, because a theme can show a label in capitals; an element that holds
exactly that comes first, else one that contains it. Of several, the first in reading order wins,
and a line on stderr says how many there were.

```text
$ ui.sh list
TextView 'Touch Probe' at 190,136 size 298x71
Button 'PROBE BUTTON' id=probe_button at 540,273 size 1080x126 clickable
EditText id=probe_field at 540,399 size 1080x126 clickable focused
```

`ui.sh` reads the screen with `uiautomator dump`, which answers only once the screen has been idle
for a moment, so a look at an animating screen takes a while, and keeps trying for up to
`AWDT_UI_TIMEOUT` seconds. It can't see the inside of a `WebView` that doesn't publish its content,
a game's canvas, or a secure window: a screenshot shows those.

**Prefer `ui.sh wait` to a fixed sleep.** After a gesture or an `am start`, wait for what should
come next: it ends as soon as it's there, and on a slow host it still works.

## Typing

With the emulator's window focused, the PC's keyboard is the device's hardware keyboard, so no soft
keyboard opens by default. From a script, focus the field, then type:

```bash
ui.sh tap id:search_field
ui.sh type "two words"
```

`ui.sh type` sends ASCII only, as `adb shell input text` drops anything else. Keys that aren't
text go through adb: `adb shell input keyevent ENTER`.

## System keys

| Key | In the window | adb |
|---|---|---|
| Back | The bar on the screen, or Ctrl+Backspace | `adb shell input keyevent BACK` |
| Home | The bar on the screen, or Ctrl+H | `adb shell input keyevent HOME` |
| Recent apps | The bar on the screen, or Ctrl+O | `adb shell input keyevent KEYCODE_APP_SWITCH` |
| Menu | Ctrl+M | `adb shell input keyevent MENU` |
| Volume | Ctrl+= and Ctrl+- | `adb shell input keyevent VOLUME_UP` (`VOLUME_DOWN`) |

Esc and F1 don't reach Android: the emulator's window consumes them.

## Changing the device

CHANGING-PLACEHOLDER

## Apps and logs

```bash
./gradlew installDebug                                   # from the project
adb shell am start -n <package>/.<Activity>              # open an activity
adb shell am force-stop <package>                        # close the app
adb logcat -b crash                                      # crashes
adb logcat -d -s <TAG>:I                                 # what a tag logged so far, then return
adb logcat -c                                            # empty the log, before a step to watch
adb exec-out screencap -p > screen.png                   # what ui.sh shot does
```

`adb logcat` without `-d` never returns: a script must use `-d`, or a `timeout`.
