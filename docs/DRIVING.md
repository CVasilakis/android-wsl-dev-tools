# Driving an emulator

Using a running emulator from the window, a terminal, a script or a coding agent: touching it,
typing into it, seeing what it shows, tilting it. Getting one running:
[`EMULATORS.md`](EMULATORS.md). The commands' options are in their `--help`.

Everything here works the same on every [tested image](EMULATORS.md#tested-images). With several
devices connected, name one with `-s <serial>`, or set `ANDROID_SERIAL` to the serial
`mobile-start-emulator.sh` prints.

## Touch

| Gesture | In the window | From a script |
|---|---|---|
| Tap | Click | `mobile-touch.sh tap 540 1200` |
| Double tap | Double click | `mobile-touch.sh double-tap 540 1200` |
| Long press | Hold the button | `mobile-touch.sh long-press 540 1200` |
| Swipe, fling | Drag; a quick one flings | `mobile-touch.sh swipe 200 1800 200 600`, with a short time for a fling: `… 80` |
| Drag and drop | Hold, then drag | `mobile-touch.sh drag 300 500 800 1500` |
| Pinch | Not under WSLg (below) | `mobile-touch.sh pinch 540 1200 300 800` |
| Rotate with two fingers | Not under WSLg (below) | `mobile-touch.sh rotate 540 1200 500 90` |

**In the window** the mouse is a finger on the emulator's own touchscreen, wherever the window is
and whatever size it has: the emulator scales the screen to fit the display, and scales the
pointer back.

**Two fingers need `mobile-touch.sh` under WSLg.** Holding Ctrl over the window shows the emulator's
two circles, but a drag then reaches Android as one finger.

**Coordinates** are the screen's pixels as it's turned now, or percentages of it, which fit every
screen: `mobile-touch.sh tap 50% 75%`. In a pinch or a rotation, a percentage of a distance is of
the screen's width. Find a place with [`mobile-ui.sh`](#seeing-the-screen) rather than by measuring
a screenshot, whose scale may differ from the screen's.

**How it works.** `mobile-touch.sh` plays each gesture with a small program of ours on the device
([`lib/Gesture.java`](../lib/Gesture.java)), one mechanism on every API level. `adb shell input`
can't do this: each of its calls is a process of its own, too slow for a double tap; it has one
finger; and before API 26 it can't hold a touch and then move it. The program stays in
`/data/local/tmp` after the first gesture, so later ones skip the push. Each gesture still starts a
process on the device, so it can't follow another within a fraction of a second.

A touch goes to whichever window is under it, as a finger's does: a dialog over the app gets it
instead. `mobile-touch.sh` returns once the app has handled the last touch.

## Seeing the screen

```bash
mobile-ui.sh list              # the elements on the screen, one per line
mobile-ui.sh find "Sign in"    # the center of an element: 540 1320
mobile-ui.sh tap "Sign in"     # tap it
mobile-ui.sh tap id:login_button  # the same, by resource id
mobile-ui.sh long-press "Photo 3"  # long-press it
mobile-ui.sh wait "Welcome" 30  # until it shows; fails after 30 s
mobile-ui.sh wait-gone "Loading"  # until it's gone
mobile-ui.sh front             # the activity in front, and the window with the focus
mobile-ui.sh shot screen.png   # a screenshot
```

A selector is text, found in an element's text or description, or one field: `text:`, `desc:`,
`id:` (the whole resource id, or the part after `:id/`), `class:` (the whole name, or its last
part). Text ignores case, because a theme can show a label in capitals; an element that holds
exactly that comes first, else one that contains it. Of several, the first in reading order wins,
and a line on stderr says how many there were.

```text
$ mobile-ui.sh list
TextView 'Touch Probe' at 190,136 size 298x71
Button 'PROBE BUTTON' id=probe_button at 540,273 size 1080x126 clickable
EditText id=probe_field at 540,399 size 1080x126 clickable focused
```

`mobile-ui.sh` reads the screen with `uiautomator dump`, which answers only once the screen has been
idle for a moment, so a look at an animating screen takes a while, and keeps trying for up to
`AWDT_UI_TIMEOUT` seconds. It can't see the inside of a `WebView` that doesn't publish its content,
a game's canvas, or a secure window: a screenshot shows those.

**Prefer `mobile-ui.sh wait` to a fixed sleep.** After a gesture or an `am start`, wait for what
should come next: it ends as soon as it's there, and on a slow host it still works.

## Typing

With the emulator's window focused, the PC's keyboard is the device's hardware keyboard, so no soft
keyboard opens by default. From a script, focus the field, then type:

```bash
mobile-ui.sh tap id:search_field
mobile-ui.sh type "two words"
```

`mobile-ui.sh type` sends ASCII only, as `adb shell input text` drops anything else. Keys that
aren't text go through adb: `adb shell input keyevent ENTER`.

## System keys

| Key | In the window | adb |
|---|---|---|
| Back | The bar on the screen, or Ctrl+Backspace | `adb shell input keyevent BACK` |
| Home | The bar on the screen, or Ctrl+H | `adb shell input keyevent HOME` |
| Recent apps | The bar on the screen, or Ctrl+O | `adb shell input keyevent KEYCODE_APP_SWITCH` |
| Menu | Ctrl+M | `adb shell input keyevent MENU` |
| Volume | Ctrl+= and Ctrl+- | `adb shell input keyevent VOLUME_UP` (`VOLUME_DOWN`) |

Esc and F1 don't reach Android: the emulator's window consumes them. With a text field focused,
Ctrl+= can also type a character into it.

## Sensors

`mobile-sensor.sh` sets an emulator's sensors, as if the device were held or moved:

```bash
mobile-sensor.sh tilt 30 0           # lying face up, its top edge raised by 30°
mobile-sensor.sh tilt 60 0 1000      # from there to 60°, turning smoothly for a second
mobile-sensor.sh tilt 0 -20          # lying flat, its left edge lowered by 20°
mobile-sensor.sh flat                # lying face up: tilt 0 0
mobile-sensor.sh status              # the sensors the emulator has, with their values
mobile-sensor.sh get acceleration    # 0 9.77631 0.812349
mobile-sensor.sh set light 300       # any sensor, values of your own
```

**The attitude.** `tilt <pitch> <roll>` starts from lying face up, screen to the sky. Pitch raises
the top edge: 90 holds the device upright, facing you, and past 90 it leans away. Roll then lowers
the right edge, or the left one for a negative roll. The emulator boots upright and leaning back a
little, at about `tilt 85 0`. Values are in Android's axes: x to the right of the screen, y up it, z
out of it. The accelerometer reads 9.81 m/s² along the axis that points up, so lying flat it reads
`0 0 9.81`, upright `0 9.81 0`, and at any attitude 9.81 × (−sin roll × cos pitch, sin pitch,
cos pitch × cos roll).

**The motion sensors agree.** The console sets one sensor at a time and leaves the others as they
were, so `tilt` sets all of them from the one attitude:

- the accelerometer;
- the magnetic field: the emulator's own, 48.4 µT north and 5.9 µT up, with the device's top edge
  towards magnetic north;
- the gyroscope: the rate of turn while it moves, 0 at the end;
- the deprecated orientation sensor;
- and the uncalibrated ones, with no bias.

`set` changes only the sensor named.

**Smooth moves.** With a time in ms, `tilt` and `flat` start from the attitude the accelerometer
shows now, and turn at an even rate, each angle the short way round. They set the sensors every
20 ms, or every `AWDT_SENSOR_STEP_MS`. The steps follow the clock: on a busy host there are fewer
of them, and the move still takes the time asked. Without a time, the sensors jump to the new
attitude at once. An app gets a new value with its next sensor event on API 36; on API 21 and 30
the emulator passes new values on only every 0.8 s, and the events in between repeat the last one,
so there a smooth move reaches apps in steps of 0.8 s.

| Sensor | Values | Unit |
|---|---|---|
| `acceleration` (and `-uncalibrated`) | x y z | m/s² |
| `gyroscope` (and `-uncalibrated`) | x y z | rad/s |
| `magnetic-field` (and `-uncalibrated`) | x y z | µT |
| `orientation` | azimuth pitch roll | degrees |

The others take Android's unit for their kind: °C, cm, lux, hPa, %. `set` takes as many values as
`get` shows.

**What apps get.** On the plain images of API 21, 30 and 36, the console has the same sensors, the
ones above plus temperature, proximity, light, pressure and humidity; the rest, such as the hinge
angles and heart rate, are disabled. What reaches an app differs:

| An app's sensor | API 21 | API 30 | API 36 |
|---|---|---|---|
| Accelerometer, magnetic field, orientation (`TYPE_ORIENTATION`) | as set | as set | as set |
| Gyroscope | none: the image has no gyroscope | as set | as set |
| Gravity, linear acceleration, rotation vectors | none | Android's own | Android's own |
| New values reach it | every 0.8 s | every 0.8 s | with each event |

Android works its own sensors out from the others. On API 30 and 36 they follow a change of the
accelerometer with a lag, and ignore the gyroscope the console sets, so check a tilt through the
accelerometer.

**How it works.** Each step is one `adb emu` call that carries every sensor's command on a line of
its own, which costs about as much as one command. A phone's sensors are its own, with no console
to set them through, so `mobile-sensor.sh` only acts on an emulator.

## Changing the device

| Change | Command | Where it was seen to work |
|---|---|---|
| Turn the screen | `adb shell settings put system accelerometer_rotation 0`, then `adb shell settings put system user_rotation 1` (`0`: back) | every tested level, as long as the app in front can turn: a phone's launcher doesn't |
| Dark mode | `adb shell cmd uimode night yes` (`no`) | API 30 and 36; not on 21 or 24 |
| Font size | `adb shell settings put system font_scale 1.3`; `… settings delete system font_scale` to undo | API 21, 24, 30 and 36 |
| Screen size and density | `adb shell wm size 720x1280`, `adb shell wm density 320`; `… reset` to undo | every tested level |
| Battery level | `adb shell dumpsys battery set level 15`; `adb shell dumpsys battery reset` to undo | API 21, 24, 30 and 36 |
| Wi-Fi off | `adb shell svc wifi disable` (`enable`) | API 30 and 36 |
| Mobile data off | `adb shell svc data disable` (`enable`) | accepted on API 21, 24, 30 and 36 |
| Airplane mode | `adb shell cmd connectivity airplane-mode enable` (`disable`) | API 30 and 36; not on 21 or 24 |
| Location | `adb emu geo fix <longitude> <latitude>` | accepted on API 21, 24, 30 and 36 |

The images' `adbd` restarts as root on `adb root`, for what needs it.

To check a second screen, as a `Presentation` shows on one, Android can draw one over the first:
`adb shell settings put global overlay_display_devices 1280x720/240`, and `… delete global
overlay_display_devices` to undo.

## Apps and logs

```bash
./gradlew installDebug                                   # from the project
adb shell am start -n <package>/.<Activity>              # open an activity
adb shell am force-stop <package>                        # close the app
adb logcat -b crash                                      # crashes
adb logcat -d -s <TAG>:I                                 # what a tag logged so far, then return
adb exec-out screencap -p > screen.png            # what mobile-ui.sh shot does
```

`adb logcat` without `-d` never returns: a script must use `-d`, or a `timeout`. Don't rely on
`adb logcat -c` to start from an empty log: on API 21 and 30 it leaves lines behind. To watch one
step, write a mark of your own, `adb shell log -t MyTag mark-1`, and read what comes after it. Pass
`-v threadtime` when a script reads the lines: before API 23 the default format is another one.
