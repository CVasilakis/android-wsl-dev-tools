# lib/

What the commands in [`../bin/`](../bin/README.md) share. Nothing here is a command, or part of the
[versioned interface](../README.md#versions). Each file has one job, and a script sources only the
ones it needs.

| File | Job | Needs |
|---|---|---|
| [`sdk.sh`](sdk.sh) | Finds the SDK and its tools, says what's missing, knows the host (WSL, KVM) and the renderer. Every script sources it first. | |
| [`avd.sh`](avd.sh) | The AVDs on this machine, the default one, and how the SDK names images. | `sdk.sh` |
| [`device.sh`](device.sh) | Talking to a running device with time limits, and picking which one. | `sdk.sh` |
| [`home.sh`](home.sh) | Waiting for a booted device to settle on its home screen. | `sdk.sh`, `device.sh` |
| [`ui_tree.py`](ui_tree.py) | Reading what `uiautomator dump` wrote: listing elements, finding one. | Python 3 |
| [`Gesture.java`](Gesture.java), `Gesture.dex` | The program that plays touch gestures on a device. | |
| [`build-gesture.sh`](build-gesture.sh) | Builds `Gesture.dex` from `Gesture.java`: run it after changing the source, and commit both. | a JDK, the SDK's `d8` |
