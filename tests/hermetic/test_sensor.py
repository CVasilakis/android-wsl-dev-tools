"""mobile-sensor.sh: what reaches the emulator's console for each command, the attitudes tilt works
out, how a smooth tilt moves over time, which device it acts on, and how it fails."""
import json
import math

from support.sandbox import ScriptTestCase

G = 9.81
MOTION = ["acceleration", "acceleration-uncalibrated", "gyroscope", "gyroscope-uncalibrated",
          "magnetic-field", "magnetic-field-uncalibrated", "orientation"]
FAST = {"AWDT_SENSOR_STEP_MS": "50"}


class SensorTestCase(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")

    def sensor(self, *args, env=None):
        return self.sandbox.run("mobile-sensor.sh", *args, env=env)

    def emu_calls(self):
        """The `adb emu` calls, in order: {"lines": [console command, ...], "time": ...}."""
        return [{"lines": " ".join(c["argv"][c["argv"].index("emu") + 1:]).splitlines(),
                 "time": c["time"]}
                for c in self.sandbox.calls("adb") if "emu" in c["argv"]]

    def set_calls(self):
        """Each `adb emu` call that set sensors, as {sensor: [values]}, with its "time"."""
        steps = []
        for call in self.emu_calls():
            sets = [line.split() for line in call["lines"] if line.startswith("sensor set ")]
            if sets:
                steps.append({**{words[2]: [float(v) for v in words[3].split(":")] for words in sets},
                              "time": call["time"]})
        return steps

    def console_state(self, serial):
        """The values the fake console holds now for the sensors set so far."""
        info = json.loads((self.sandbox.state / "running" / f"{serial}.json").read_text())
        return info.get("sensors", {})

    def assertClose(self, actual, expected, places=3, msg=None):
        self.assertEqual(len(actual), len(expected), msg)
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places, msg=f"{actual} != {expected} {msg or ''}")


class StatusGetSet(SensorTestCase):
    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def test_status_lists_each_enabled_sensor_with_its_values(self):
        result = self.sensor("status")
        self.assertSucceeded(result)
        lines = result.out.splitlines()
        self.assertEqual(lines[0], "acceleration 0 9.77631 0.812349")
        self.assertIn("proximity 1", lines)
        self.assertIn("pressure 1013.25", lines)
        self.assertEqual(len(lines), 12, "the disabled ones are left out")
        self.assertNotIn("heart-rate", result.out)
        self.assertEqual(len(self.emu_calls()), 2, "the status, then every value in one call")

    def test_get_prints_the_values_alone(self):
        result = self.sensor("get", "acceleration")
        self.assertSucceeded(result)
        self.assertEqual(result.out, "0 9.77631 0.812349\n")
        self.assertEqual(self.sensor("get", "proximity").out, "1\n")

    def test_set_then_get_reads_it_back(self):
        self.assertSucceeded(self.sensor("set", "acceleration", "1", "2.5", "-3"))
        self.assertIn(["sensor set acceleration 1:2.5:-3"], [c["lines"] for c in self.emu_calls()])
        self.assertEqual(self.sensor("get", "acceleration").out, "1 2.5 -3\n")

    def test_set_is_quiet(self):
        result = self.sensor("set", "light", "300")
        self.assertSucceeded(result)
        self.assertEqual(result.output, "")

    def test_set_takes_any_decimal(self):
        self.assertSucceeded(self.sensor("set", "acceleration", "+1", ".5", "-2.5e-3"))
        self.assertIn(["sensor set acceleration +1:.5:-2.5e-3"], [c["lines"] for c in self.emu_calls()])

    def test_what_get_prints_can_be_set_again(self):
        # The console shows tiny values with an exponent.
        self.assertSucceeded(self.sensor("set", "gyroscope", "0.00001", "-2e-7", "1500000"))
        shown = self.sensor("get", "gyroscope").out.split()
        self.assertEqual(shown, ["1e-05", "-2e-07", "1.5e+06"])
        self.assertSucceeded(self.sensor("set", "gyroscope", *shown))

    def test_set_needs_as_many_values_as_the_sensor_has(self):
        # The console would keep the third value as it was, and drop a fourth.
        for args in (["acceleration", "1", "2"], ["acceleration", "1", "2", "3", "4"]):
            with self.subTest(args):
                result = self.sensor("set", *args)
                self.assertFailed(result, f"acceleration takes 3 values, not {len(args) - 1}", code=1)
                self.assertIn("mobile-sensor.sh get acceleration", result.err)
        self.assertFailed(self.sensor("set", "proximity", "1", "2"), "proximity takes 1 values, not 2",
                          code=1)
        self.assertEqual(self.set_calls(), [])

    def test_an_unknown_sensor(self):
        result = self.sensor("get", "nosuch")
        self.assertFailed(result, f"the console of {self.serial} refused 'sensor get nosuch':", code=1)
        self.assertIn("KO: unknown sensor name: nosuch", result.err)
        self.assertEqual(result.out, "")
        self.assertFailed(self.sensor("set", "nosuch", "1"), "unknown sensor name", code=1)

    def test_a_disabled_sensor(self):
        result = self.sensor("get", "heart-rate")
        self.assertFailed(result, "KO: 'heart-rate' sensor is disabled.", code=1)

    def test_a_set_the_console_refuses(self):
        self.sandbox.set_behavior(sensor_sets_refused_after=0)
        result = self.sensor("set", "acceleration", "1", "2", "3")
        self.assertFailed(result, "refused 'sensor set acceleration 1:2:3':", code=1)
        self.assertIn("KO: the fake console refuses", result.err)

    def test_status_of_an_emulator_without_sensors(self):
        self.sandbox.set_behavior(sensors={name: None for name in (
            "acceleration", "gyroscope", "magnetic-field", "orientation", "temperature", "proximity",
            "light", "pressure", "humidity", "magnetic-field-uncalibrated", "gyroscope-uncalibrated",
            "acceleration-uncalibrated")})
        result = self.sensor("status")
        self.assertSucceeded(result)
        self.assertEqual(result.out, "")


class Tilt(SensorTestCase):
    """The attitude's sensors, set together. Angles from lying face up: pitch raises the top edge,
    roll lowers the right one; the accelerometer reads +9.81 m/s² along the axis that points up."""

    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def tilted(self, *args, env=None):
        result = self.sensor(*args, env=env)
        self.assertSucceeded(result)
        self.assertEqual(result.output, "", "a tilt that worked says nothing")
        return self.set_calls()[-1]

    def test_flat_is_gravity_out_of_the_screen(self):
        step = self.tilted("flat")
        self.assertClose(step["acceleration"], [0, 0, G])
        self.assertClose(step["gyroscope"], [0, 0, 0])
        self.assertClose(step["magnetic-field"], [0, 48.4, 5.9], msg="the top edge points north")
        self.assertClose(step["orientation"], [0, 0, 0])

    def test_known_angles_give_known_vectors(self):
        c30, s30, s45 = G * math.cos(math.radians(30)), G / 2, G * math.sqrt(0.5)
        for (pitch, roll), acceleration, orientation in (
                (("90", "0"), [0, G, 0], [0, -90, 0]),         # upright, facing you
                (("30", "0"), [0, s30, c30], [0, -30, 0]),     # top edge raised
                (("-45", "0"), [0, -s45, s45], [0, 45, 0]),    # top edge lowered
                (("0", "30"), [-s30, 0, c30], [0, 0, -30]),    # right edge lowered
                (("0", "-90"), [G, 0, 0], [0, 0, 90]),         # standing on its left edge
                (("90", "90"), [0, G, 0], [0, -90, 0])):       # upright: roll turns it about up
            with self.subTest(pitch=pitch, roll=roll):
                step = self.tilted("tilt", pitch, roll)
                self.assertClose(step["acceleration"], acceleration)
                self.assertClose(step["orientation"], orientation)
                self.assertClose(step["gyroscope"], [0, 0, 0], msg="at rest")

    def test_the_magnetic_field_turns_with_the_device(self):
        step = self.tilted("tilt", "90", "0")
        self.assertClose(step["magnetic-field"], [0, 5.9, -48.4], msg="north is behind the screen")
        step = self.tilted("tilt", "0", "90")
        self.assertClose(step["magnetic-field"], [-5.9, 48.4, 0])

    def test_the_emulators_resting_attitude_gives_its_own_resting_values(self):
        # The emulator boots upright and leaning back a little; its magnetic field is the one tilt
        # uses, which keeps a tilt back to that attitude as the emulator left it.
        pitch = math.degrees(math.atan2(9.77631, 0.812349))
        step = self.tilted("tilt", f"{pitch:.6f}", "0")
        self.assertClose(step["acceleration"], [0, 9.77631, 0.812349], places=4)
        self.assertClose(step["magnetic-field"], [0, 9.88766, -47.7452], places=3)

    def test_sets_every_motion_sensor_in_one_call(self):
        self.tilted("tilt", "30", "20")
        sets = [c for c in self.emu_calls() if any(line.startswith("sensor set") for line in c["lines"])]
        self.assertEqual(len(sets), 1)
        self.assertEqual([line.split()[2] for line in sets[0]["lines"]], MOTION)
        step = self.set_calls()[0]
        for name in ("acceleration", "gyroscope", "magnetic-field"):
            self.assertEqual(step[f"{name}-uncalibrated"], step[name], "no bias")
        self.assertClose(self.console_state(self.serial)["acceleration"], step["acceleration"])

    def test_sets_only_the_motion_sensors_the_emulator_has(self):
        self.sandbox.set_behavior(sensors={"gyroscope": None, "gyroscope-uncalibrated": None,
                                           "orientation": None})
        step = self.tilted("tilt", "30", "0")
        self.assertEqual(sorted(k for k in step if k != "time"),
                         sorted(["acceleration", "acceleration-uncalibrated", "magnetic-field",
                                 "magnetic-field-uncalibrated"]))

    def test_needs_an_accelerometer(self):
        self.sandbox.set_behavior(sensors={"acceleration": None})
        self.assertFailed(self.sensor("tilt", "30", "0"), f"{self.serial} has no acceleration sensor",
                          code=1)
        self.assertEqual(self.set_calls(), [])

    def test_a_time_is_in_decimal_even_with_a_leading_zero(self):
        self.sandbox.stop_emulators()
        self.serial = self.sandbox.start_emulator("phone_api36")
        result = self.sensor("tilt", "30", "0", "080", env={"AWDT_SENSOR_STEP_MS": "20"})
        self.assertSucceeded(result)
        self.assertGreater(len(self.set_calls()), 1)

    def test_a_console_that_fails_before_the_tilt_says_so(self):
        self.sandbox.set_behavior(sensors={"acceleration": None})
        result = self.sensor("-s", "emulator-5999", "tilt", "30", "0")
        self.assertFailed(result, "the console of emulator-5999 refused 'sensor status'", code=1)
        self.assertNotIn("no acceleration sensor", result.err)

    def test_a_time_of_zero_is_a_jump(self):
        self.tilted("tilt", "30", "0", "0")
        self.assertEqual(len(self.set_calls()), 1)

    def test_fractional_and_signed_angles(self):
        step = self.tilted("tilt", "-12.5", "+7.25")
        u = [v / G for v in step["acceleration"]]
        self.assertAlmostEqual(math.degrees(math.asin(u[1])), -12.5, places=3)
        self.assertAlmostEqual(math.degrees(math.atan2(-u[0], u[2])), 7.25, places=3)


class SmoothTilt(SensorTestCase):
    """With a time, from the attitude the accelerometer shows now to the one asked, in steps that
    follow the clock, the gyroscope turning at the move's rate."""

    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def moved(self, *args, env=FAST):
        before = len(self.set_calls())
        result = self.sensor(*args, env=env)
        self.assertSucceeded(result)
        self.assertEqual(result.output, "")
        return self.set_calls()[before:]

    @staticmethod
    def pitch_of(step):
        ax, ay, az = step["acceleration"]
        return math.degrees(math.atan2(ay, math.hypot(ax, az)))

    def test_moves_from_where_it_is_to_the_attitude_asked(self):
        self.moved("flat")
        steps = self.moved("tilt", "30", "0", "400")
        self.assertGreater(len(steps), 2)
        pitches = [self.pitch_of(s) for s in steps]
        self.assertLess(pitches[0], 10, "the first step is near the start")
        self.assertEqual(pitches, sorted(pitches), "it only turns one way")
        self.assertClose(steps[-1]["acceleration"], [0, G / 2, G * math.cos(math.radians(30))])
        for step in steps:
            self.assertAlmostEqual(math.hypot(*step["acceleration"]), G, places=3,
                                   msg="gravity keeps its strength on the way")

    def test_the_gyroscope_turns_while_it_moves_and_stops_at_the_end(self):
        self.moved("flat")
        steps = self.moved("tilt", "30", "0", "400")
        rate = math.radians(30) / 0.4
        for step in steps[:-1]:
            self.assertClose(step["gyroscope"], [rate, 0, 0], msg="about x, top edge up")
            self.assertEqual(step["gyroscope-uncalibrated"], step["gyroscope"])
        self.assertClose(steps[-1]["gyroscope"], [0, 0, 0])

    def test_rolling_turns_about_y(self):
        self.moved("flat")
        steps = self.moved("tilt", "0", "-40", "200")
        self.assertClose(steps[0]["gyroscope"], [0, math.radians(-40) / 0.2, 0])

    def test_the_move_takes_the_time_asked(self):
        self.moved("flat")
        self.moved("tilt", "30", "0", "500")
        calls = self.emu_calls()
        start = [c for c in calls if c["lines"] == ["sensor get acceleration"]][-1]["time"]
        self.assertGreaterEqual(calls[-1]["time"] - start, 0.5)

    def test_no_more_than_a_step_each_period(self):
        self.moved("flat")
        steps = self.moved("tilt", "30", "0", "500", env={"AWDT_SENSOR_STEP_MS": "100"})
        self.assertLessEqual(len(steps), 500 // 100 + 1 + 1, "the steps, and the end at rest")
        for earlier, later in zip(steps[:-2], steps[1:-1]):
            self.assertGreaterEqual(later["time"] - earlier["time"], 0.09)

    def test_a_step_longer_than_the_move_does_not_make_it_longer(self):
        self.moved("flat")
        steps = self.moved("tilt", "30", "0", "300", env={"AWDT_SENSOR_STEP_MS": "5000"})
        self.assertEqual(len(steps), 2, "the start, then the end")
        self.assertLess(steps[1]["time"] - steps[0]["time"], 4)

    def test_flat_with_a_time_moves_too(self):
        self.moved("tilt", "40", "0")
        steps = self.moved("flat", "300")
        self.assertGreater(len(steps), 1)
        self.assertClose(steps[-1]["acceleration"], [0, 0, G])

    def test_starts_from_the_emulators_own_resting_values(self):
        # Booted, the emulator is upright and leaning back: about tilt 85 0.
        steps = self.moved("tilt", "90", "0", "200")
        self.assertAlmostEqual(self.pitch_of(steps[0]), 85.25, places=1)
        self.assertClose(steps[0]["acceleration"][:1], [0])

    def test_rolls_the_short_way_round(self):
        self.moved("tilt", "0", "170")
        steps = self.moved("tilt", "0", "-170", "300")
        for step in steps:
            self.assertLess(step["acceleration"][2], -9, "through face down, not face up")

    def test_from_past_upright_it_goes_on_turning_the_same_way(self):
        # Gravity alone doesn't tell pitch 120 from pitch 60 with the device turned round: the
        # move takes the reading that needs the shorter turn.
        self.moved("tilt", "120", "0")
        steps = self.moved("tilt", "150", "0", "300")
        for step in steps:
            self.assertAlmostEqual(step["acceleration"][0], 0, places=3, msg="no roll on the way")
        self.assertClose(steps[-1]["acceleration"], [0, G / 2, -G * math.cos(math.radians(30))])

    def test_a_step_the_console_refuses_stops_the_move(self):
        self.sandbox.set_behavior(sensor_sets_refused_after=2)
        result = self.sensor("tilt", "30", "0", "2000", env=FAST)
        self.assertFailed(result, f"the console of {self.serial} refused one of 7 commands:", code=1)
        self.assertEqual(len(self.set_calls()), 3, "two steps, then the one refused")

    def test_the_step_must_be_whole_milliseconds(self):
        for step in ("0", "fast", "1.5", "-20"):
            with self.subTest(step):
                self.assertFailed(self.sensor("flat", env={"AWDT_SENSOR_STEP_MS": step}),
                                  "AWDT_SENSOR_STEP_MS must be a number of milliseconds", code=1)


class WhichDevice(SensorTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.add_avd("tablet")

    def sets_of(self, serial):
        return [c for c in self.sandbox.calls("adb")
                if "emu" in c["argv"] and c["argv"][:2] == ["-s", serial]]

    def test_the_only_running_emulator(self):
        serial = self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.sensor("flat"))
        self.assertTrue(self.sets_of(serial))

    def test_every_call_names_the_device(self):
        serial = self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.sensor("tilt", "20", "0", "100", env=FAST))
        for argv in self.sandbox.argvs("adb"):
            if argv[:1] != ["devices"]:
                self.assertEqual(argv[:2], ["-s", serial], f"adb call without -s: {argv}")

    def test_several_emulators_are_named_in_the_error(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        result = self.sensor("flat")
        self.assertFailed(result, f"several emulators are running ({first} {second})", code=1)
        self.assertEqual(self.sets_of(first) + self.sets_of(second), [])

    def test_the_one_named(self):
        self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.sensor("-s", second, "flat"))
        self.assertTrue(self.sets_of(second))
        self.assertSucceeded(self.sensor("get", "acceleration", env={"ANDROID_SERIAL": second}))

    def test_no_emulator_names_start_emulator(self):
        result = self.sensor("flat")
        self.assertFailed(result, "no running emulator. Start one with:", code=1)
        self.assertIn("mobile-start-emulator.sh", result.err)

    def test_a_physical_device_is_refused_even_when_named(self):
        # Its sensors are its own: there's no console to set them through.
        self.sandbox.connect_device("R58M123ABC")
        for args, env in ((["-s", "R58M123ABC", "flat"], None),
                          (["get", "acceleration"], {"ANDROID_SERIAL": "R58M123ABC"})):
            with self.subTest(args):
                result = self.sensor(*args, env=env)
                self.assertFailed(result, "R58M123ABC is not an emulator", code=1)
        self.assertEqual([a for a in self.sandbox.argvs("adb") if "emu" in a], [])

    def test_a_physical_device_is_not_picked(self):
        self.sandbox.connect_device("R58M123ABC")
        serial = self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.sensor("flat"))
        self.assertTrue(self.sets_of(serial))

    def test_an_emulator_that_is_not_there(self):
        self.sandbox.start_emulator("phone_api36")
        result = self.sensor("-s", "emulator-5999", "get", "acceleration")
        self.assertFailed(result, "the console of emulator-5999 refused", code=1)
        self.assertIn("device 'emulator-5999' not found", result.err)

    def test_a_console_that_hangs_does_not_hang_the_script(self):
        self.sandbox.set_behavior(emulator_console_hangs=True)
        self.sandbox.start_emulator("phone_api36")
        result = self.sensor("tilt", "30", "0", "1000", env={"AWDT_ADB_TIMEOUT": "1"})
        self.assertFailed(result, "refused 'sensor status'", code=1)
        self.assertIn("adb gave no answer", result.err)

    def test_leaves_the_stdin_of_the_calling_script_alone(self):
        # As mobile-touch.sh does: `adb shell` would swallow what a loop feeds on.
        serial = self.sandbox.start_emulator("phone_api36")
        tools = self.sandbox.tools / "bin"
        result = self.sandbox.bash(f"printf '10\\n20\\n30\\n' | while read -r n; do "
                                   f"{tools}/mobile-sensor.sh tilt \"$n\" 0; done")
        self.assertSucceeded(result)
        self.assertEqual(len(self.set_calls()), 3)
        self.assertTrue(self.sets_of(serial))


class WrongArguments(SensorTestCase):
    """Exit 2 with the usage, before anything reaches adb."""

    def assertRefused(self, *args):
        result = self.sensor(*args)
        self.assertEqual(result.code, 2, result.output)
        self.assertIn("Usage: mobile-sensor.sh", result.err)
        self.assertEqual(self.sandbox.argvs("adb"), [], "adb must not be called")

    def test_no_command(self):
        self.assertRefused()

    def test_an_unknown_command(self):
        self.assertRefused("shake")

    def test_too_few_or_too_many_arguments(self):
        for args in (["status", "acceleration"], ["get"], ["get", "acceleration", "proximity"],
                     ["set"], ["set", "acceleration"], ["tilt"], ["tilt", "30"],
                     ["tilt", "30", "0", "100", "5"], ["flat", "100", "5"]):
            with self.subTest(args):
                self.assertRefused(*args)

    def test_a_sensor_name_is_the_consoles(self):
        for name in ("Acceleration", "accel eration", "", "-s", "$(reboot)", "light;reboot"):
            with self.subTest(name):
                self.assertRefused("get", name)

    def test_a_value_that_is_no_plain_number(self):
        # The console would read "1,5" as 1.
        for value in ("1,5", "1e", "e3", "x", "", "--1", "1.2.3", "5%", "$(reboot)", "1;reboot"):
            with self.subTest(value):
                self.assertRefused("set", "light", value)
                self.assertRefused("tilt", value, "0")
                self.assertRefused("tilt", "0", value)

    def test_a_time_must_be_whole_milliseconds(self):
        for ms in ("1.5", "-5", "soon", "50%"):
            with self.subTest(ms):
                self.assertRefused("tilt", "30", "0", ms)
                self.assertRefused("flat", ms)

    def test_s_needs_a_serial_and_a_command(self):
        self.assertRefused("-s")
        self.assertRefused("-s", "emulator-5554")

    def test_s_comes_first(self):
        self.assertRefused("flat", "-s", "emulator-5554")

    def test_nothing_else_is_needed_for_the_usage(self):
        result = self.sandbox.run("mobile-sensor.sh", "tilt", env={"ANDROID_HOME": "/nonexistent"})
        self.assertEqual(result.code, 2, result.output)

    def test_help_goes_to_stdout(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag):
                result = self.sensor(flag)
                self.assertSucceeded(result)
                self.assertIn("Usage: mobile-sensor.sh", result.out)
                self.assertEqual(result.err, "")


class Usage(ScriptTestCase):
    def test_without_any_sdk(self):
        self.assertFailed(self.sandbox.run("mobile-sensor.sh", "flat"), "no Android SDK found", code=1)

    def test_names_the_missing_package(self):
        self.sandbox.install_sdk(tools=["emulator"])
        self.assertFailed(self.sandbox.run("mobile-sensor.sh", "flat"),
                          'android sdk install --no-metrics "platform-tools"', code=1)
