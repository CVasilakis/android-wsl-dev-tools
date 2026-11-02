"""mobile-touch.sh: what each gesture passes to the program on the device, percentages, which device it
acts on, and how it fails."""
import shutil
import unittest

from support.sandbox import LIB, ScriptTestCase

DEX_FOLDER = "/data/local/tmp"


class TouchTestCase(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")

    def touch(self, *args, env=None):
        return self.sandbox.run("mobile-touch.sh", *args, env=env)

    def gestures(self, serial):
        return self.sandbox.device_state(serial)["gestures"]

    def pushes(self):
        return [argv for argv in self.sandbox.argvs("adb") if "push" in argv]


class Gestures(TouchTestCase):
    """Each gesture reaches the program with its own arguments. The real program is for the
    emulator tier; here it's a fake that records what it was given."""

    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def played(self, *args, env=None):
        result = self.touch(*args, env=env)
        self.assertSucceeded(result)
        self.assertEqual(result.output, "", "a gesture that worked says nothing")
        return self.gestures(self.serial)[-1]

    def test_tap(self):
        self.assertEqual(self.played("tap", "100", "200"), ["tap", "100", "200"])

    def test_double_tap(self):
        self.assertEqual(self.played("double-tap", "100", "200"), ["double-tap", "100", "200"])

    def test_long_press_holds_twice_the_devices_long_press_timeout(self):
        self.sandbox.stop_emulators()
        self.sandbox.set_behavior(device_settings={"long_press_timeout": "400"})
        self.serial = self.sandbox.start_emulator("phone_api36")
        self.assertEqual(self.played("long-press", "100", "200"), ["hold", "100", "200", "800"])

    def test_long_press_holds_a_second_when_the_timeout_is_unset(self):
        # `settings get` answers "null", and the setting's default is 500 ms.
        self.assertEqual(self.played("long-press", "100", "200"), ["hold", "100", "200", "1000"])

    def test_long_press_for_the_time_given_does_not_ask_the_device(self):
        self.assertEqual(self.played("long-press", "100", "200", "3000"), ["hold", "100", "200", "3000"])
        self.assertEqual([a for a in self.sandbox.argvs("adb") if "settings" in a], [])

    def test_swipe(self):
        self.assertEqual(self.played("swipe", "10", "20", "30", "40"),
                         ["swipe", "10", "20", "30", "40", "300"])

    def test_swipe_for_the_time_given_is_a_fling_when_short(self):
        self.assertEqual(self.played("swipe", "10", "20", "30", "40", "80"),
                         ["swipe", "10", "20", "30", "40", "80"])

    def test_drag_holds_as_a_long_press_then_moves(self):
        self.sandbox.stop_emulators()
        self.sandbox.set_behavior(device_settings={"long_press_timeout": "400"})
        self.serial = self.sandbox.start_emulator("phone_api36")
        self.assertEqual(self.played("drag", "10", "20", "30", "40"),
                         ["drag", "10", "20", "30", "40", "800", "600"])

    def test_drag_holds_a_second_when_the_timeout_is_unset(self):
        self.assertEqual(self.played("drag", "10", "20", "30", "40"),
                         ["drag", "10", "20", "30", "40", "1000", "600"])

    def test_drag_with_a_time_given_moves_for_that_time(self):
        self.assertEqual(self.played("drag", "10", "20", "30", "40", "1500"),
                         ["drag", "10", "20", "30", "40", "1000", "1500"])

    def test_pinch(self):
        self.assertEqual(self.played("pinch", "500", "900", "600", "200"),
                         ["pinch", "500", "900", "600", "200", "500"])
        self.assertEqual(self.played("pinch", "500", "900", "200", "600", "1000"),
                         ["pinch", "500", "900", "200", "600", "1000"])

    def test_rotate(self):
        self.assertEqual(self.played("rotate", "500", "900", "400", "90"),
                         ["rotate", "500", "900", "400", "90", "500"])

    def test_rotate_counterclockwise_for_the_time_given(self):
        self.assertEqual(self.played("rotate", "500", "900", "400", "-45", "1000"),
                         ["rotate", "500", "900", "400", "-45", "1000"])

    def test_negative_and_fractional_coordinates_reach_the_program(self):
        self.assertEqual(self.played("tap", "-5", "20.5"), ["tap", "-5", "20.5"])

    def test_every_call_names_the_device(self):
        self.played("long-press", "50%", "50%")
        for argv in self.sandbox.argvs("adb"):
            if argv[:1] != ["devices"]:
                self.assertEqual(argv[:2], ["-s", self.serial], f"adb call without -s: {argv}")

    def test_leaves_the_stdin_of_the_calling_script_alone(self):
        # adb shell forwards its stdin, which would swallow what a loop feeds on.
        tools = self.sandbox.tools / "bin"
        result = self.sandbox.bash(f"printf '1\\n2\\n3\\n' | while read -r n; do "
                                   f"{tools}/mobile-touch.sh long-press \"$n%\" 2; done")
        self.assertSucceeded(result)
        self.assertEqual(len(self.gestures(self.serial)), 3)


class PushedOnce(TouchTestCase):
    """The program goes to the device the first time, under a name that holds its checksum."""

    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def test_the_first_gesture_pushes_it_and_later_ones_do_not(self):
        self.assertSucceeded(self.touch("tap", "1", "1"))
        self.assertSucceeded(self.touch("tap", "2", "2"))
        self.assertSucceeded(self.touch("swipe", "1", "1", "2", "2"))
        self.assertEqual(len(self.pushes()), 1)
        self.assertEqual(len(self.gestures(self.serial)), 3, "the first gesture was played too")

    def test_its_name_on_the_device_holds_its_checksum(self):
        self.assertSucceeded(self.touch("tap", "1", "1"))
        [path] = self.sandbox.device_state(self.serial)["files"]
        checksum = self.sandbox.bash(f"cksum < {self.sandbox.tools}/lib/Gesture.dex | "
                                     "awk '{ print $1 }'").out.strip()
        self.assertEqual(path, f"{DEX_FOLDER}/awdt-gesture-{checksum}.dex")

    def test_a_program_that_changed_is_pushed_again_next_to_the_old_one(self):
        self.assertSucceeded(self.touch("tap", "1", "1"))
        with (self.sandbox.tools / "lib" / "Gesture.dex").open("ab") as dex:
            dex.write(b"rebuilt")
        self.assertSucceeded(self.touch("tap", "2", "2"))
        self.assertEqual(len(self.pushes()), 2)
        self.assertEqual(len(self.sandbox.device_state(self.serial)["files"]), 2)

    def test_each_device_gets_its_own_copy(self):
        self.sandbox.add_avd("tablet")
        other = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.touch("-s", self.serial, "tap", "1", "1"))
        self.assertSucceeded(self.touch("-s", other, "tap", "1", "1"))
        self.assertEqual([argv[:2] for argv in self.pushes()], [["-s", self.serial], ["-s", other]])

    def test_says_so_when_the_push_fails(self):
        self.sandbox.set_behavior(push_error="adb: error: failed to copy: No space left on device")
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, f"couldn't push the gesture program to {self.serial}", code=1)
        self.assertEqual(self.gestures(self.serial), [])


class Percentages(TouchTestCase):
    """A percentage is of the screen as it's turned now, from `dumpsys window displays` (cur=), and
    of the width for a distance. The dump is asked for only when a percentage needs it."""

    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def played(self, *args):
        self.assertSucceeded(self.touch(*args))
        return self.gestures(self.serial)[-1]

    def size_asked(self):
        return [argv for argv in self.sandbox.argvs("adb") if argv[-2:] == ["window", "displays"]]

    def test_coordinates(self):
        self.assertEqual(self.played("tap", "50%", "25%"), ["tap", "540", "600"])

    def test_a_turned_screen(self):
        self.sandbox.set_behavior(screen_turned=True)
        self.assertEqual(self.played("tap", "50%", "25%"), ["tap", "1200", "270"])

    def test_percentages_next_to_pixels(self):
        self.assertEqual(self.played("swipe", "10%", "2000", "90%", "2000"),
                         ["swipe", "108", "2000", "972", "2000", "300"])

    def test_a_fraction_of_a_percent_ends_in_whole_pixels(self):
        self.assertEqual(self.played("tap", "33.3%", "12.5%"), ["tap", "359", "300"])

    def test_pinch_distances_are_of_the_width(self):
        self.assertEqual(self.played("pinch", "50%", "50%", "60%", "10%"),
                         ["pinch", "540", "1200", "648", "108", "500"])

    def test_rotate_distance_is_of_the_width_and_degrees_stay(self):
        self.assertEqual(self.played("rotate", "50%", "50%", "40%", "90"),
                         ["rotate", "540", "1200", "432", "90", "500"])

    def test_drag_and_long_press_too(self):
        self.assertEqual(self.played("long-press", "50%", "50%", "2000"), ["hold", "540", "1200", "2000"])
        self.assertEqual(self.played("drag", "10%", "10%", "90%", "90%", "700"),
                         ["drag", "108", "240", "972", "2160", "1000", "700"])

    def test_another_screen_size(self):
        self.sandbox.set_behavior(screen_size="2560x1600")
        self.assertEqual(self.played("tap", "100%", "100%"), ["tap", "2560", "1600"])

    def test_the_screen_is_asked_only_once(self):
        self.played("swipe", "10%", "10%", "90%", "90%")
        self.assertEqual(len(self.size_asked()), 1)

    def test_not_asked_without_a_percentage(self):
        for args in (["tap", "1", "1"], ["long-press", "1", "1"], ["swipe", "1", "2", "3", "4"],
                     ["drag", "1", "2", "3", "4"], ["pinch", "1", "2", "3", "4"], ["rotate", "1", "2", "3", "4"]):
            with self.subTest(args):
                self.played(*args)
        self.assertEqual(self.size_asked(), [])

    def test_fails_when_the_device_does_not_say_its_size(self):
        self.sandbox.set_behavior(screen_size=None)
        result = self.touch("tap", "50%", "50%")
        self.assertFailed(result, f"couldn't read the screen's size from {self.serial}", code=1)
        self.assertEqual(self.gestures(self.serial), [])


class WhichDevice(TouchTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.add_avd("tablet")

    def test_the_serial_given(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.touch("-s", second, "tap", "1", "1"))
        self.assertEqual(self.gestures(second), [["tap", "1", "1"]])
        self.assertEqual(self.gestures(first), [])

    def test_android_serial(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.touch("tap", "1", "1", env={"ANDROID_SERIAL": first}))
        self.assertEqual(self.gestures(first), [["tap", "1", "1"]])
        self.assertEqual(self.gestures(second), [])

    def test_the_serial_given_wins_over_android_serial(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.touch("-s", second, "tap", "1", "1", env={"ANDROID_SERIAL": first}))
        self.assertEqual(self.gestures(second), [["tap", "1", "1"]])
        self.assertEqual(self.gestures(first), [])

    def test_the_only_running_emulator(self):
        serial = self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.touch("tap", "1", "1"))
        self.assertEqual(self.gestures(serial), [["tap", "1", "1"]])

    def test_several_emulators_are_named_in_the_error(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, f"several emulators are running ({first} {second})", code=1)
        self.assertIn("-s <serial>", result.err)
        self.assertEqual(self.gestures(first) + self.gestures(second), [])

    def test_no_emulator_names_start_emulator(self):
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, "no running emulator. Start one with:", code=1)
        self.assertIn("mobile-start-emulator.sh", result.err)

    def test_a_physical_device_is_not_picked_for_an_emulator(self):
        self.sandbox.connect_device("R58M123ABC")
        serial = self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.touch("tap", "1", "1"))
        self.assertEqual(self.gestures(serial), [["tap", "1", "1"]])
        self.assertEqual(self.gestures("R58M123ABC"), [])

    def test_a_physical_device_alone_is_not_picked(self):
        self.sandbox.connect_device("R58M123ABC")
        self.assertFailed(self.touch("tap", "1", "1"), "no running emulator", code=1)
        self.assertEqual(self.gestures("R58M123ABC"), [])

    def test_a_physical_device_is_used_when_named(self):
        self.sandbox.connect_device("R58M123ABC")
        self.assertSucceeded(self.touch("-s", "R58M123ABC", "tap", "1", "1"))
        self.assertSucceeded(self.touch("tap", "2", "2", env={"ANDROID_SERIAL": "R58M123ABC"}))
        self.assertEqual(self.gestures("R58M123ABC"), [["tap", "1", "1"], ["tap", "2", "2"]])

    def test_percentages_and_hold_times_are_asked_of_the_device_named(self):
        first = self.sandbox.start_emulator("phone_api36")
        second = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.touch("-s", second, "long-press", "50%", "50%"))
        self.assertEqual({tuple(argv[:2]) for argv in self.sandbox.argvs("adb") if argv[:1] == ["-s"]},
                         {("-s", second)})
        self.assertEqual(self.gestures(first), [])

    def test_a_device_that_is_not_there(self):
        self.sandbox.start_emulator("phone_api36")
        result = self.touch("-s", "emulator-5999", "tap", "1", "1")
        self.assertFailed(result, "the gesture failed on emulator-5999", code=1)
        self.assertIn("device 'emulator-5999' not found", result.err)


class WrongArguments(TouchTestCase):
    """Exit 2 with the usage, before anything reaches adb."""

    def assertRefused(self, *args):
        result = self.touch(*args)
        self.assertEqual(result.code, 2, result.output)
        self.assertIn("Usage: mobile-touch.sh", result.err)
        self.assertEqual(self.sandbox.argvs("adb"), [], "adb must not be called")

    def test_no_gesture(self):
        self.assertRefused()

    def test_an_unknown_gesture(self):
        self.assertRefused("poke", "1", "1")

    def test_too_few_or_too_many_numbers(self):
        for args in (["tap"], ["tap", "1"], ["tap", "1", "2", "3"], ["double-tap", "1"],
                     ["double-tap", "1", "2", "3"], ["long-press", "1"], ["long-press", "1", "2", "3", "4"],
                     ["swipe", "1", "2", "3"], ["swipe", "1", "2", "3", "4", "5", "6"],
                     ["drag", "1", "2", "3"], ["drag", "1", "2", "3", "4", "5", "6"],
                     ["pinch", "1", "2", "3"], ["pinch", "1", "2", "3", "4", "5", "6"],
                     ["rotate", "1", "2", "3"], ["rotate", "1", "2", "3", "4", "5", "6"]):
            with self.subTest(args):
                self.assertRefused(*args)

    def test_a_coordinate_that_is_no_number(self):
        for args in (["tap", "left", "1"], ["tap", "1", "2px"], ["tap", "1", ""], ["tap", "1", "1e3"],
                     ["tap", "1", "50%%"], ["tap", "1", "5;reboot"], ["tap", "1", "$(reboot)"]):
            with self.subTest(args):
                self.assertRefused(*args)

    def test_a_time_must_be_whole_milliseconds(self):
        for args in (["long-press", "1", "1", "1.5"], ["long-press", "1", "1", "-5"],
                     ["long-press", "1", "1", "50%"], ["swipe", "1", "2", "3", "4", "soon"],
                     ["swipe", "1", "2", "3", "4", "1.5"], ["drag", "1", "2", "3", "4", "50%"],
                     ["pinch", "1", "2", "3", "4", "-1"], ["rotate", "1", "2", "3", "4", "0.5"]):
            with self.subTest(args):
                self.assertRefused(*args)

    def test_degrees_are_no_percentage(self):
        self.assertRefused("rotate", "1", "2", "3", "50%")

    def test_s_needs_a_serial(self):
        self.assertRefused("-s")

    def test_s_needs_a_gesture_too(self):
        self.assertRefused("-s", "emulator-5554")

    def test_s_comes_first(self):
        self.assertRefused("tap", "1", "1", "-s", "emulator-5554")

    def test_nothing_else_is_needed_for_the_usage(self):
        # No SDK at all: arguments come first.
        result = self.sandbox.run("mobile-touch.sh", "tap", env={"ANDROID_HOME": "/nonexistent"})
        self.assertEqual(result.code, 2, result.output)

    def test_help_goes_to_stdout(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag):
                result = self.touch(flag)
                self.assertSucceeded(result)
                self.assertIn("Usage: mobile-touch.sh", result.out)
                self.assertEqual(result.err, "")


class WhenItFails(TouchTestCase):
    def setUp(self):
        super().setUp()
        self.serial = self.sandbox.start_emulator("phone_api36")

    def test_shows_the_programs_output(self):
        self.sandbox.set_behavior(api_level=36, gesture_output=
                                  "java.lang.IllegalStateException: Android refused event 0")
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, f"the gesture failed on {self.serial}:", code=1)
        self.assertIn("java.lang.IllegalStateException: Android refused event 0", result.err)
        self.assertEqual(result.out, "")

    def test_shows_the_programs_output_without_adbs_carriage_returns(self):
        # Through grep: a test's text output doesn't show them.
        self.sandbox.set_behavior(gesture_output="Android refused event 0")
        result = self.sandbox.bash(f"{self.sandbox.tools}/bin/mobile-touch.sh tap 1 1 2>&1 | grep -c $'\\r'")
        self.assertEqual(result.out, "0\n")

    def test_reads_the_failure_from_the_output_before_api_24(self):
        # adb shell passes on no exit status there, so it's 0 for a program that crashed.
        self.sandbox.set_behavior(api_level=23, gesture_output="Exception in thread main")
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, f"the gesture failed on {self.serial}:", code=1)
        self.assertIn("Exception in thread main", result.err)

    def test_no_events_injected_is_a_failure(self):
        self.sandbox.set_behavior(api_level=23, gesture_output="Events injected: 0")
        self.assertFailed(self.touch("tap", "1", "1"), "the gesture failed", code=1)

    def test_shows_the_end_of_a_long_output(self):
        lines = [f"line {n}" for n in range(1, 21)]
        self.sandbox.set_behavior(gesture_output="\n\n".join(lines))
        result = self.touch("tap", "1", "1")
        self.assertFailed(result, "line 20", code=1)
        self.assertEqual(result.err.splitlines()[1:], lines[-5:], "the last lines, none of them blank")

    def test_fails_after_a_push_too(self):
        # The first gesture's output comes from the call after the push.
        self.sandbox.set_behavior(gesture_output="no such display")
        self.assertFailed(self.touch("tap", "1", "1"), "no such display", code=1)
        self.assertEqual(len(self.pushes()), 1)

    def test_a_gesture_that_hangs_does_not_hang_the_script(self):
        self.assertSucceeded(self.touch("tap", "1", "1"))   # pushed, so the hang is the program's
        self.sandbox.set_behavior(adb_hangs={"gesture": 99})
        result = self.touch("-s", self.serial, "tap", "2", "2", env={"AWDT_ADB_TIMEOUT": "1"})
        self.assertFailed(result, "the gesture failed", code=1)
        self.assertIn("adb gave no answer", result.err)
        self.assertEqual(len(self.gestures(self.serial)), 1)

    def test_a_gesture_gets_its_own_time_on_top_of_adbs_limit(self):
        # Measured at the limit rather than by a slow gesture, which would race it.
        calls = self.sandbox.root / "timeouts"
        wrapper = self.sandbox.bin / "timeout"
        real = wrapper.resolve()
        wrapper.unlink()
        wrapper.write_text(f'#!{shutil.which("bash")}\necho "$*" >> {calls}\nexec {real} "$@"\n')
        wrapper.chmod(0o755)
        for args in (["long-press", "1", "1", "20000"], ["swipe", "1", "2", "3", "4", "9000"],
                     ["drag", "1", "2", "3", "4", "4000"], ["pinch", "1", "2", "3", "4", "2000"]):
            self.assertSucceeded(self.touch(*args, env={"AWDT_ADB_TIMEOUT": "7"}))
        limits = [line.split()[2] for line in calls.read_text().splitlines() if "Gesture" in line]
        self.assertEqual(limits, ["28", "28", "17", "13", "10"], "the first one twice: its push")


class TheProgram(unittest.TestCase):
    """What can be told of the real program without a device: it's a dex, and it knows what mobile-touch.sh
    asks of it and what mobile-touch.sh reads from it."""

    def test_is_a_dex_that_knows_every_gesture(self):
        dex = (LIB / "Gesture.dex").read_bytes()
        self.assertTrue(dex.startswith(b"dex\n"), "not a dex: rebuild it with lib/build-gesture.sh")
        for word in ("tap", "double-tap", "hold", "swipe", "drag", "pinch", "rotate", "Events injected: "):
            with self.subTest(word):
                self.assertIn(word.encode(), dex)


class Usage(ScriptTestCase):
    def test_without_any_sdk(self):
        self.assertFailed(self.sandbox.run("mobile-touch.sh", "tap", "1", "1"), "no Android SDK found", code=1)

    def test_names_the_missing_package(self):
        self.sandbox.install_sdk(tools=["emulator"])
        self.assertFailed(self.sandbox.run("mobile-touch.sh", "tap", "1", "1"),
                          'android sdk install --no-metrics "platform-tools"', code=1)
