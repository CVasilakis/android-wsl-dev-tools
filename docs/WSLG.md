# The emulator's window under WSLg

What's special about the emulator's window under WSLg: its side toolbar, which
[`mobile-wslg-toolbar.py`](../bin/mobile-wslg-toolbar.py) hides or shows, and what only a real mouse
and keyboard can do there. Outside WSL, `mobile-start-emulator.sh` leaves the toolbar as the
emulator shows it.

## The side toolbar

Under WSLg the emulator's side toolbar (power, volume, Back, Home, "⋯" → Extended controls) breaks
input:

1. **Its buttons ignore clicks.** WSLg draws the toolbar next to the emulator but places its X11
   window at (-32768, -32768), where the mouse pointer can never go.
2. **It steals the keyboard.** While it's shown, keys typed into the emulator window move focus
   between the toolbar buttons instead of reaching Android.

You can't have both a clickable toolbar and a working keyboard, so `mobile-wslg-toolbar.py <avd>
hide|show` picks one:

| Mode | Keyboard in emulator window | Toolbar |
|---|---|---|
| `hide` (default in `mobile-start-emulator.sh`) | works | hidden |
| `show` | goes to the toolbar (use [`mobile-ui.sh type`](DRIVING.md#typing)) | clickable, including "⋯" → Extended controls |

Switch at any time on a running emulator, as often as you like: `mobile-wslg-toolbar.py show`.
Without an AVD name it acts on the only emulator window; with several, pass the name:
`mobile-wslg-toolbar.py phone_api36 show`. `show` unmaps the toolbar, waits until the window manager
has withdrawn it, and maps it again as a normal window; if the window manager doesn't withdraw it
within 30 s, the script says so and maps it anyway. Once WSLg has shown it, the script moves it
beside the emulator window, where the emulator itself puts it when you move that window. The
emulator has a second window titled "Emulator" (a 620x21 bar, hidden once it has booted); the script
tells the toolbar apart by its shape, a column taller than wide. Restarting the emulator undoes it.
The script's docstring describes the emulator's windows and explains the mechanism, how to inspect
them (`xwininfo`, `xprop`) and which approaches don't work.

A toolbar shown as a normal window still behaves differently from the emulator's own:

- It doesn't minimize with the emulator window, and it has no taskbar button of its own.
- Bringing another window in front of the emulator can take two clicks: the first one covers
  the emulator window, the second the toolbar.
- Its own minimize button doesn't minimize: the emulator window and the toolbar show again a
  little higher and to the left. Minimize the emulator window from its title bar or the
  taskbar instead.

On boot the emulator window may open behind your Windows apps; bring it forward from the taskbar.
Windows decides which app is in front, so the scripts can't.

To have it from the boot on: `EMULATOR_TOOLBAR=show mobile-start-emulator.sh`. Touch doesn't depend
on the toolbar: the mouse on the emulator's screen acts as a finger in both modes
([`DRIVING.md`](DRIVING.md#touch)).

## What scripts can't do there

XWayland under WSLg ignores simulated input (XTest) and `XSetInputFocus`, so `xdotool` and the like
don't reach the emulator: scripts touch and type through [`mobile-touch.sh`](DRIVING.md#touch) and
[`mobile-ui.sh`](DRIVING.md#typing). The tests' mouse check runs the real window on a private X
server instead ([`tests/README.md`](../tests/README.md)).

Don't run anything that opens and closes many windows on the real display: it has crashed WSLg's
compositor, which closes every Linux GUI app ([`tests/README.md`](../tests/README.md)).
