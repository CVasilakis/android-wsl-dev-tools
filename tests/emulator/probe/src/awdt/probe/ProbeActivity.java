package awdt.probe;

import android.app.Activity;
import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * What the emulator tier looks through at a real app: it logs what reaches it, under the tag
 * AwdtProbe. Its area logs each touch (TOUCH) and what Android's own detectors made of them
 * (GESTURE), and how far two fingers moved (SPAN, in px, and TURN, in degrees); its button logs
 * CLICK, its field TEXT. While it's in front, it listens to the motion sensors the device has
 * (SENSORS, once) and logs each one's values whenever they change (SENSOR), as apps get them.
 */
public class ProbeActivity extends Activity {
    private static final String TAG = "AwdtProbe";
    @SuppressWarnings("deprecation")  // TYPE_ORIENTATION: the emulator still has one
    private static final int[] SENSORS = {
        Sensor.TYPE_ACCELEROMETER, Sensor.TYPE_GYROSCOPE, Sensor.TYPE_MAGNETIC_FIELD,
        Sensor.TYPE_ORIENTATION,
    };
    private static final String[] SENSOR_NAMES = {
        "ACCELEROMETER", "GYROSCOPE", "MAGNETIC_FIELD", "ORIENTATION",
    };

    private SensorManager sensorManager;
    private final Map<Integer, String> lastValues = new HashMap<>();
    private final SensorEventListener sensorLog = new SensorEventListener() {
        @Override public void onSensorChanged(SensorEvent event) {
            int type = event.sensor.getType();
            String values = String.format(Locale.ROOT, "x=%.2f y=%.2f z=%.2f",
                    event.values[0], event.values[1], event.values[2]);
            if (values.equals(lastValues.put(type, values))) return;
            for (int i = 0; i < SENSORS.length; i++) {
                if (SENSORS[i] == type) Log.i(TAG, "SENSOR " + SENSOR_NAMES[i] + " " + values);
            }
        }

        @Override public void onAccuracyChanged(Sensor sensor, int accuracy) { }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setFitsSystemWindows(true);

        Button button = new Button(this);
        button.setId(R.id.probe_button);
        button.setText("Probe button");
        button.setOnClickListener(view -> Log.i(TAG, "CLICK"));
        column.addView(button);

        EditText field = new EditText(this);
        field.setId(R.id.probe_field);
        field.setHint("Probe field");
        field.setSingleLine(true);
        field.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable text) {
                Log.i(TAG, "TEXT [" + text + "]");
            }
        });
        column.addView(field);

        Area area = new Area(this);
        area.setId(R.id.probe_area);
        column.addView(area, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(column);
        sensorManager = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
    }

    @Override
    protected void onResume() {
        super.onResume();
        lastValues.clear();
        StringBuilder listening = new StringBuilder("SENSORS");
        for (int i = 0; i < SENSORS.length; i++) {
            Sensor sensor = sensorManager.getDefaultSensor(SENSORS[i]);
            if (sensor != null) {
                sensorManager.registerListener(sensorLog, sensor, SensorManager.SENSOR_DELAY_GAME);
                listening.append(' ').append(SENSOR_NAMES[i]);
            }
        }
        Log.i(TAG, listening.toString());
    }

    @Override
    protected void onPause() {
        sensorManager.unregisterListener(sensorLog);
        super.onPause();
    }

    private static final class Area extends View {
        private final GestureDetector gestures;
        private final ScaleGestureDetector scales;
        private double firstSpan;
        private double firstAngle;

        Area(Context context) {
            super(context);
            setBackgroundColor(0xff141820);
            gestures = new GestureDetector(context, new GestureDetector.SimpleOnGestureListener() {
                @Override public boolean onDown(MotionEvent e) {
                    return true;
                }
                @Override public boolean onSingleTapConfirmed(MotionEvent e) {
                    Log.i(TAG, "GESTURE TAP " + at(e));
                    return true;
                }
                @Override public boolean onDoubleTap(MotionEvent e) {
                    Log.i(TAG, "GESTURE DOUBLE_TAP " + at(e));
                    return true;
                }
                @Override public void onLongPress(MotionEvent e) {
                    Log.i(TAG, "GESTURE LONG_PRESS " + at(e));
                }
                @Override public boolean onFling(MotionEvent a, MotionEvent b, float vx, float vy) {
                    Log.i(TAG, "GESTURE FLING vx=" + (int) vx + " vy=" + (int) vy);
                    return true;
                }
            });
            scales = new ScaleGestureDetector(context,
                    new ScaleGestureDetector.SimpleOnScaleGestureListener() {
                        @Override public void onScaleEnd(ScaleGestureDetector detector) {
                            Log.i(TAG, "GESTURE SCALE");
                        }
                    });
        }

        private static String at(MotionEvent e) {
            return "x=" + (int) e.getRawX() + " y=" + (int) e.getRawY();
        }

        private static double span(MotionEvent e) {
            return Math.hypot(e.getX(1) - e.getX(0), e.getY(1) - e.getY(0));
        }

        private static double angle(MotionEvent e) {
            return Math.toDegrees(Math.atan2(e.getY(1) - e.getY(0), e.getX(1) - e.getX(0)));
        }

        @Override public boolean onTouchEvent(MotionEvent event) {
            Log.i(TAG, "TOUCH " + MotionEvent.actionToString(event.getActionMasked())
                    + " pointers=" + event.getPointerCount() + " " + at(event));
            if (event.getActionMasked() == MotionEvent.ACTION_POINTER_DOWN) {
                firstSpan = span(event);
                firstAngle = angle(event);
            } else if (event.getActionMasked() == MotionEvent.ACTION_POINTER_UP) {
                double turn = (angle(event) - firstAngle + 540) % 360 - 180;
                Log.i(TAG, "SPAN from=" + Math.round(firstSpan) + " to=" + Math.round(span(event)));
                Log.i(TAG, "TURN degrees=" + Math.round(turn));
            }
            scales.onTouchEvent(event);
            gestures.onTouchEvent(event);
            return true;
        }
    }
}
