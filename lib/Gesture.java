import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.MotionEvent;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * Plays a touch gesture on the screen, for touch.sh: one mechanism on every API level, as the shell
 * user (run with app_process), into the device's input, so the window under the fingers gets
 * MotionEvents as it gets a touchscreen's. `adb shell input` can't do this: each of its calls is a
 * process of its own, too slow for a double tap; it has one finger; and before API 24 it can't hold
 * a touch and then move it.
 *
 * Usage: app_process /system/bin Gesture <gesture> <arguments>, in pixels and milliseconds:
 *   tap <x> <y>                                  a short touch
 *   double-tap <x> <y>                           two of them, as quickly as a finger
 *   hold <x> <y> <ms>                            a touch that stays, for a long press
 *   swipe <x1> <y1> <x2> <y2> <ms>               a touch moving at an even speed
 *   drag <x1> <y1> <x2> <y2> <hold ms> <ms>      held first, then moved, then let go at rest
 *   pinch <x> <y> <from> <to> <ms>               two fingers level with (x, y), <from> px apart
 *                                                at first and <to> at the end
 *   rotate <x> <y> <distance> <degrees> <ms>     two fingers turning round (x, y), <distance> px
 *                                                apart, clockwise for positive degrees
 * Prints "Events injected: <n>" when it sent them, as adb's exit status can't say before API 24.
 *
 * Built into Gesture.dex by build-gesture.sh, which also says what it needs; rebuild it after
 * changing this file.
 */
public class Gesture {
    private static final int FRAME_MS = 16;
    private static final int TAP_MS = 50;
    private static final int DOUBLE_TAP_GAP_MS = 100;   // Android's limit between the two is 300
    private static final int DROP_REST_MS = 100;        // or a list scrolls on after the release

    private static final int INJECT_ASYNC = 0;
    private static final int INJECT_WAIT_FOR_FINISH = 2;

    /** Where a finger is, as a function of the time since the touch began. */
    private interface Path {
        float[] at(long ms);
    }

    /** Fingers that touch at the same moment, and leave together when it ends. */
    private static final class Touch {
        final long duration;
        final Path[] fingers;
        final long pauseAfter;

        Touch(long duration, long pauseAfter, Path... fingers) {
            this.duration = duration;
            this.pauseAfter = pauseAfter;
            this.fingers = fingers;
        }
    }

    private static Object manager;
    private static Method inject;
    private static int deviceId;
    private static int injected;

    public static void main(String[] args) throws Exception {
        List<Touch> touches = parse(args);
        findInjection();
        deviceId = touchscreen();
        for (Touch touch : touches) {
            play(touch);
            Thread.sleep(touch.pauseAfter);
        }
        System.out.println("Events injected: " + injected);
    }

    private static List<Touch> parse(String[] args) {
        List<Touch> touches = new ArrayList<>();
        String gesture = args[0];
        switch (gesture) {
            case "tap":
                touches.add(new Touch(TAP_MS, 0, still(number(args, 1), number(args, 2))));
                break;
            case "double-tap":
                Path spot = still(number(args, 1), number(args, 2));
                touches.add(new Touch(TAP_MS, DOUBLE_TAP_GAP_MS, spot));
                touches.add(new Touch(TAP_MS, 0, spot));
                break;
            case "hold":
                touches.add(new Touch((long) number(args, 3), 0,
                        still(number(args, 1), number(args, 2))));
                break;
            case "swipe":
                long swipe = (long) number(args, 5);
                touches.add(new Touch(swipe, 0, line(number(args, 1), number(args, 2),
                        number(args, 3), number(args, 4), 0, swipe)));
                break;
            case "drag":
                long hold = (long) number(args, 5);
                long move = (long) number(args, 6);
                touches.add(new Touch(hold + move + DROP_REST_MS, 0,
                        line(number(args, 1), number(args, 2), number(args, 3), number(args, 4),
                                hold, move)));
                break;
            case "pinch":
                long pinch = (long) number(args, 5);
                float x = number(args, 1), y = number(args, 2);
                float from = number(args, 3) / 2, to = number(args, 4) / 2;
                touches.add(new Touch(pinch, 0, line(x - from, y, x - to, y, 0, pinch),
                        line(x + from, y, x + to, y, 0, pinch)));
                break;
            case "rotate":
                long turn = (long) number(args, 5);
                touches.add(new Touch(turn, 0,
                        circle(number(args, 1), number(args, 2), number(args, 3) / 2, 180,
                                number(args, 4), turn),
                        circle(number(args, 1), number(args, 2), number(args, 3) / 2, 0,
                                number(args, 4), turn)));
                break;
            default:
                throw new IllegalArgumentException("unknown gesture " + gesture);
        }
        return touches;
    }

    private static float number(String[] args, int index) {
        return Float.parseFloat(args[index]);
    }

    private static Path still(final float x, final float y) {
        return ms -> new float[] {x, y};
    }

    /** From (x1, y1) to (x2, y2), starting after `wait` and taking `duration`. */
    private static Path line(final float x1, final float y1, final float x2, final float y2,
            final long wait, final long duration) {
        return ms -> {
            float part = duration == 0 ? 1 : Math.max(0, Math.min(1, (ms - wait) / (float) duration));
            return new float[] {x1 + (x2 - x1) * part, y1 + (y2 - y1) * part};
        };
    }

    private static Path circle(final float x, final float y, final float radius, final float start,
            final float degrees, final long duration) {
        return ms -> {
            float part = duration == 0 ? 1 : Math.min(1, ms / (float) duration);
            double angle = Math.toRadians(start + degrees * part);
            return new float[] {x + radius * (float) Math.cos(angle),
                    y + radius * (float) Math.sin(angle)};
        };
    }

    private static void play(Touch touch) throws Exception {
        int count = touch.fingers.length;
        long down = SystemClock.uptimeMillis();
        send(down, MotionEvent.ACTION_DOWN, 1, touch, 0, INJECT_WAIT_FOR_FINISH);
        for (int finger = 1; finger < count; finger++) {
            send(down, pointer(MotionEvent.ACTION_POINTER_DOWN, finger), finger + 1, touch, 0,
                    INJECT_ASYNC);
        }
        float[] last = positions(touch, 0);
        for (long ms = FRAME_MS; ms < touch.duration; ms += FRAME_MS) {
            sleepUntil(down + ms);
            float[] now = positions(touch, ms);
            if (!java.util.Arrays.equals(now, last)) {
                send(down, MotionEvent.ACTION_MOVE, count, touch, ms, INJECT_ASYNC);
                last = now;
            }
        }
        sleepUntil(down + touch.duration);
        if (!java.util.Arrays.equals(positions(touch, touch.duration), last)) {
            send(down, MotionEvent.ACTION_MOVE, count, touch, touch.duration, INJECT_ASYNC);
        }
        for (int finger = count - 1; finger > 0; finger--) {
            send(down, pointer(MotionEvent.ACTION_POINTER_UP, finger), finger + 1, touch,
                    touch.duration, INJECT_ASYNC);
        }
        send(down, MotionEvent.ACTION_UP, 1, touch, touch.duration, INJECT_WAIT_FOR_FINISH);
    }

    private static int pointer(int action, int finger) {
        return action | (finger << MotionEvent.ACTION_POINTER_INDEX_SHIFT);
    }

    private static float[] positions(Touch touch, long ms) {
        float[] all = new float[touch.fingers.length * 2];
        for (int finger = 0; finger < touch.fingers.length; finger++) {
            float[] position = touch.fingers[finger].at(ms);
            all[finger * 2] = position[0];
            all[finger * 2 + 1] = position[1];
        }
        return all;
    }

    /** One event, with the first `fingers` fingers of the touch where they are at `ms`. */
    private static void send(long down, int action, int fingers, Touch touch, long ms, int mode)
            throws Exception {
        MotionEvent.PointerProperties[] properties = new MotionEvent.PointerProperties[fingers];
        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[fingers];
        for (int finger = 0; finger < fingers; finger++) {
            float[] position = touch.fingers[finger].at(ms);
            properties[finger] = new MotionEvent.PointerProperties();
            properties[finger].id = finger;
            properties[finger].toolType = MotionEvent.TOOL_TYPE_FINGER;
            coords[finger] = new MotionEvent.PointerCoords();
            coords[finger].x = position[0];
            coords[finger].y = position[1];
            coords[finger].pressure = 1;
            coords[finger].size = 1;
        }
        MotionEvent event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, fingers,
                properties, coords, 0, 0, 1, 1, deviceId, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        boolean sent = (Boolean) inject.invoke(manager, event, mode);
        event.recycle();
        if (!sent) throw new IllegalStateException("Android refused event " + action);
        injected++;
    }

    private static void findInjection() throws Exception {
        try {
            // Android 14 and later keep the injection in a class of its own.
            Class<?> global = Class.forName("android.hardware.input.InputManagerGlobal");
            manager = global.getMethod("getInstance").invoke(null);
            inject = global.getMethod("injectInputEvent", InputEvent.class, int.class);
        } catch (ClassNotFoundException e) {
            Class<?> input = Class.forName("android.hardware.input.InputManager");
            manager = input.getMethod("getInstance").invoke(null);
            inject = input.getMethod("injectInputEvent", InputEvent.class, int.class);
        }
    }

    /** The device's touchscreen, as `input` looks it up; 0 for a virtual one, as `input` has it. */
    private static int touchscreen() {
        for (int id : InputDevice.getDeviceIds()) {
            InputDevice device = InputDevice.getDevice(id);
            if (device != null && device.supportsSource(InputDevice.SOURCE_TOUCHSCREEN)) return id;
        }
        return 0;
    }

    private static void sleepUntil(long uptime) throws InterruptedException {
        long wait = uptime - SystemClock.uptimeMillis();
        if (wait > 0) Thread.sleep(wait);
    }
}
