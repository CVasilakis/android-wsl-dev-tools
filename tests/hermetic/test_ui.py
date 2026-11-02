"""ui.sh and lib/ui_tree.py: reading the screen, finding elements on it, acting on them, waiting."""
import os
import signal
import subprocess
import time

from support.sandbox import ScriptTestCase
from support.screens import hierarchy, node

HOME = "com.android.launcher3/.uioverrides.QuickstepLauncher"
HOME_WINDOW = "com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher"
BUTTON = "android.widget.Button"
LAYOUT = "android.widget.FrameLayout"
FIELD = "android.widget.EditText"
TAG = "com.example.app:id/"

# A login screen: rows from the top down, with a parent that's named by nothing.
LOGIN = hierarchy(node(
    node(text="Welcome back", id=TAG + "title", bounds="[100,200][980,300]"),
    node(text="", desc="Your name", id=TAG + "name", cls=FIELD, bounds="[100,400][980,500]",
         focused="true", clickable="true"),
    node(text="Sign in", id=TAG + "sign_in", cls=BUTTON, bounds="[100,600][500,700]", clickable="true"),
    node(text="Sign in later", id=TAG + "later", cls=BUTTON, bounds="[580,600][980,700]",
         clickable="true", long_clickable="true"),
    node(desc="Help", id="android:id/button1", cls="android.widget.ImageButton",
         bounds="[0,2200][100,2300]", clickable="true"),
    node(text="Off screen", bounds="[0,0][0,0]"),
    node(text="Disabled", cls=BUTTON, bounds="[0,2300][100,2400]", enabled="false"),
    cls=LAYOUT, bounds="[0,0][1080,2400]"))


class UiTestCase(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")
        self.sandbox.set_behavior(ui_hierarchy=[LOGIN])
        self.serial = self.sandbox.start_emulator("phone_api36")

    def ui(self, *args, env=None):
        return self.sandbox.run("ui.sh", *args, env=env)

    def gestures(self, serial=None):
        return self.sandbox.device_state(serial or self.serial)["gestures"]

    def dumps(self):
        return [argv for argv in self.sandbox.argvs("adb") if any("uiautomator" in a for a in argv)]

    def assertNoTemporaryFiles(self):
        left = [path.name for path in self.sandbox.tmp.iterdir()]
        self.assertEqual(left, [], "temporary files left behind")


class Lists(UiTestCase):
    def test_every_element_worth_naming_one_per_line(self):
        result = self.ui("list")
        self.assertSucceeded(result)
        self.assertEqual(result.out.splitlines(), [
            "TextView 'Welcome back' id=title at 540,250 size 880x100",
            "EditText desc='Your name' id=name at 540,450 size 880x100 clickable focused",
            "Button 'Sign in' id=sign_in at 300,650 size 400x100 clickable",
            "Button 'Sign in later' id=later at 780,650 size 400x100 clickable long-clickable",
            "ImageButton desc='Help' id=button1 at 50,2250 size 100x100 clickable",
            "Button 'Disabled' at 50,2350 size 100x100 disabled",
        ])

    def test_says_nothing_of_a_screen_with_nothing_on_it(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy()])
        result = self.ui("list")
        self.assertSucceeded(result)
        self.assertEqual(result.out, "")

    def test_shows_each_flag_a_screen_can_have(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(
            scrollable="true", checkable="true", checked="true", selected="true"))])
        self.assertIn("size 100x100 scrollable checkable checked selected\n", self.ui("list").out)

    def test_text_that_is_not_ascii(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Καλημέρα"))])
        result = self.ui("list")
        self.assertSucceeded(result)
        self.assertIn("'Καλημέρα'", result.out)

    def test_text_with_xml_in_it(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text='a < b & "c"'))])
        self.assertIn('a < b & "c"', self.ui("list").out)

    def test_an_element_without_bounds_is_left_out(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Odd", bounds="nowhere"))])
        self.assertEqual(self.ui("list").out, "")

    def test_takes_no_arguments(self):
        result = self.ui("list", "all")
        self.assertEqual(result.code, 2, result.output)
        self.assertIn("Usage: ui.sh", result.err)


class Selectors(UiTestCase):
    def find(self, selector):
        result = self.ui("find", selector)
        self.assertSucceeded(result)
        return result.out.strip()

    def test_plain_text_in_an_elements_text(self):
        self.assertEqual(self.find("Welcome back"), "540 250")

    def test_plain_text_in_an_elements_description(self):
        self.assertEqual(self.find("Your name"), "540 450")

    def test_an_exact_match_comes_before_a_partial_one(self):
        # "Sign in" is in both buttons; a partial match higher up doesn't win either.
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(
            node(text="Sign in to go on", bounds="[0,0][100,100]"),
            node(text="Sign in", bounds="[0,500][100,600]"))])
        self.assertEqual(self.find("Sign in"), "50 550")

    def test_a_partial_match_when_there_is_no_exact_one(self):
        self.assertEqual(self.find("later"), "780 650")

    def test_case_does_not_matter(self):
        self.assertEqual(self.find("WELCOME BACK"), "540 250")
        self.assertEqual(self.find("your NAME"), "540 450")
        self.assertEqual(self.find("text:welcome back"), "540 250")
        self.assertEqual(self.find("desc:HELP"), "50 2250")

    def test_case_does_not_matter_in_other_alphabets_either(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="ΣΥΝΔΕΣΗ"))])
        self.assertEqual(self.find("συνδεση"), "50 50")

    def test_text_only_looks_in_the_text(self):
        self.assertEqual(self.ui("find", "text:Your name").code, 1)
        self.assertEqual(self.find("text:Sign in"), "300 650")

    def test_desc_only_looks_in_the_description(self):
        self.assertEqual(self.ui("find", "desc:Welcome back").code, 1)
        self.assertEqual(self.find("desc:Help"), "50 2250")

    def test_text_and_desc_prefer_an_exact_match_too(self):
        self.assertEqual(self.find("text:Sign in"), "300 650")
        self.assertEqual(self.find("text:Sign"), "300 650")

    def test_id_whole_or_short(self):
        self.assertEqual(self.find("id:com.example.app:id/later"), "780 650")
        self.assertEqual(self.find("id:later"), "780 650")
        self.assertEqual(self.find("id:android:id/button1"), "50 2250")

    def test_id_is_never_partial(self):
        self.assertEqual(self.ui("find", "id:late").code, 1)
        self.assertEqual(self.ui("find", "id:example").code, 1)

    def test_class_whole_or_short(self):
        self.assertEqual(self.find("class:android.widget.EditText"), "540 450")
        self.assertEqual(self.find("class:EditText"), "540 450")

    def test_class_is_never_partial(self):
        self.assertEqual(self.ui("find", "class:Edit").code, 1)
        self.assertEqual(self.ui("find", "class:widget").code, 1)

    def test_a_selector_with_a_colon_that_is_no_field_is_text(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Time: 5 min"))])
        self.assertEqual(self.find("Time: 5"), "50 50")

    def test_a_field_with_nothing_after_it_is_text(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="text:"), node(text="id:"))])
        self.assertEqual(self.find("text:"), "50 50")

    def test_a_field_name_alone_is_text(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Show text"))])
        self.assertEqual(self.find("text"), "50 50")


class SeveralMatches(UiTestCase):
    """Of several, the first in reading order, and a line on stderr says so."""

    def test_a_higher_row_comes_first_wherever_it_is_across(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(
            node(text="Item", bounds="[0,900][100,1000]"),
            node(text="Item", bounds="[500,100][600,200]"))])
        result = self.ui("find", "Item")
        self.assertSucceeded(result)
        self.assertEqual(result.out, "550 150\n")
        self.assertEqual(result.err, "2 elements match 'Item'; using the first\n")

    def test_in_a_row_the_leftmost_comes_first(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(
            node(text="Item", bounds="[500,100][600,200]"),
            node(text="Item", bounds="[0,100][100,200]"),
            node(text="Item", bounds="[250,100][350,200]"))])
        result = self.ui("find", "Item")
        self.assertSucceeded(result)
        self.assertEqual(result.out, "50 150\n")
        self.assertEqual(result.err, "3 elements match 'Item'; using the first\n")

    def test_one_match_says_nothing_more(self):
        result = self.ui("find", "Help")
        self.assertSucceeded(result)
        self.assertEqual(result.err, "")

    def test_a_partial_match_does_not_count_next_to_an_exact_one(self):
        self.assertEqual(self.ui("find", "Sign in").err, "")

    def test_several_partial_matches(self):
        self.assertEqual(self.ui("find", "Sign").err, "2 elements match 'Sign'; using the first\n")

    def test_tap_says_so_too(self):
        result = self.ui("tap", "Sign")
        self.assertSucceeded(result)
        self.assertEqual(self.gestures(), [["tap", "300", "650"]])
        self.assertIn("2 elements match 'Sign'", result.err)


class Finds(UiTestCase):
    def test_prints_the_center_alone_on_stdout(self):
        self.assertEqual(self.ui("find", "Sign in later").out, "780 650\n")

    def test_the_center_of_bounds_that_are_odd(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Odd", bounds="[10,21][20,30]"))])
        self.assertEqual(self.ui("find", "Odd").out, "15 25\n")

    def test_an_element_partly_off_the_screen(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Edge", bounds="[-100,0][100,50]"))])
        self.assertEqual(self.ui("find", "Edge").out, "0 25\n")

    def test_zero_size_elements_are_ignored(self):
        self.assertEqual(self.ui("find", "Off screen").code, 1)
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(
            node(text="Flat", bounds="[0,500][100,500]"), node(text="Thin", bounds="[50,0][50,100]"))])
        self.assertEqual(self.ui("find", "Flat").code, 1)
        self.assertEqual(self.ui("find", "Thin").code, 1)

    def test_exit_1_when_there_is_none(self):
        result = self.ui("find", "Nothing like it")
        self.assertEqual(result.code, 1, result.output)
        self.assertEqual(result.out, "")

    def test_an_element_nested_deep_in_the_hierarchy(self):
        deep = node(text="Deep", bounds="[10,10][30,30]")
        for _ in range(5):
            deep = node(deep, cls=LAYOUT)
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(deep)])
        self.assertEqual(self.ui("find", "Deep").out, "20 20\n")

    def test_a_disabled_element_is_found_too(self):
        self.assertEqual(self.ui("find", "Disabled").out, "50 2350\n")


class TouchesElements(UiTestCase):
    def test_tap_goes_through_touch_sh_on_the_elements_center(self):
        result = self.ui("tap", "Sign in")
        self.assertSucceeded(result)
        self.assertEqual(self.gestures(), [["tap", "300", "650"]])
        self.assertEqual(result.out, "")

    def test_long_press_too(self):
        self.assertSucceeded(self.ui("long-press", "Sign in later"))
        self.assertEqual(self.gestures(), [["hold", "780", "650", "1000"]])

    def test_a_selector_field(self):
        self.assertSucceeded(self.ui("tap", "id:button1"))
        self.assertEqual(self.gestures(), [["tap", "50", "2250"]])

    def test_a_missing_element_names_ui_sh_list(self):
        for command in ("tap", "long-press"):
            with self.subTest(command):
                result = self.ui(command, "Nothing like it")
                self.assertFailed(result, f"no element matches 'Nothing like it' on {self.serial}", code=1)
                self.assertIn("ui.sh list", result.err)
        self.assertEqual(self.gestures(), [])

    def test_says_how_to_call_list_the_way_it_was_called(self):
        result = self.sandbox.run("ui.sh", "tap", "Nothing like it", how="path")
        self.assertIn("See what's there: ui.sh list\n", result.err)
        result = self.sandbox.run("ui.sh", "tap", "Nothing like it", how="relative")
        self.assertIn("See what's there: ../tools/bin/ui.sh list\n", result.err)

    def test_a_failed_gesture_fails_the_command(self):
        self.sandbox.set_behavior(gesture_output="Android refused event 0")
        result = self.ui("tap", "Sign in")
        self.assertFailed(result, "Android refused event 0", code=1)

    def test_touches_the_device_it_read(self):
        self.sandbox.add_avd("tablet")
        other = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.ui("-s", other, "tap", "Sign in"))
        self.assertEqual(self.gestures(other), [["tap", "300", "650"]])
        self.assertEqual(self.gestures(), [])


class Looks(UiTestCase):
    """`uiautomator dump` fails while the screen animates: a look tries again, for up to
    AWDT_UI_TIMEOUT seconds."""

    def test_tries_again_while_the_screen_animates(self):
        self.sandbox.set_behavior(ui_idle_failures=2)
        result = self.ui("find", "Sign in", env={"AWDT_UI_TIMEOUT": "25"})
        self.assertSucceeded(result)
        self.assertEqual(result.out, "300 650\n")
        self.assertEqual(len(self.dumps()), 3)

    def test_reads_a_new_dump_each_time(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="First")), hierarchy(node(text="Second"))])
        self.assertIn("First", self.ui("list").out)
        self.assertIn("Second", self.ui("list").out)

    def test_gives_up_when_it_keeps_animating(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        started = time.time()   # the clock $SECONDS follows
        result = self.ui("list", env={"AWDT_UI_TIMEOUT": "1"})
        self.assertFailed(result, f"couldn't read the screen of {self.serial}: it kept animating, or "
                                  "the device is gone.", code=1)
        self.assertGreaterEqual(time.time() - started, 1, "it gave up before its limit")

    def test_a_timeout_of_zero_is_one_try(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        self.assertFailed(self.ui("list", env={"AWDT_UI_TIMEOUT": "0"}), "couldn't read the screen", code=1)
        self.assertEqual(len(self.dumps()), 1)

    def test_the_timeout_must_be_a_number_of_seconds(self):
        for value in ("soon", "-1", "1.5", "1s"):
            with self.subTest(value):
                result = self.ui("list", env={"AWDT_UI_TIMEOUT": value})
                self.assertFailed(result, f"AWDT_UI_TIMEOUT must be a number of seconds, not '{value}'", code=1)
        self.assertEqual(self.dumps(), [])

    def test_find_gives_up_the_same_way(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        self.assertFailed(self.ui("find", "Sign in", env={"AWDT_UI_TIMEOUT": "0"}),
                          "couldn't read the screen", code=1)

    def test_tap_says_it_could_not_read_the_screen_not_that_nothing_matches(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        result = self.ui("tap", "Sign in", env={"AWDT_UI_TIMEOUT": "0"})
        self.assertFailed(result, "couldn't read the screen", code=1)
        self.assertNotIn("no element matches", result.err)
        self.assertEqual(self.gestures(), [])

    def test_a_dump_that_cannot_be_fetched_is_a_failed_look(self):
        # The dump says it was written, but what comes back isn't one.
        self.sandbox.set_behavior(ui_hierarchy=["cat: no such file"])
        self.assertFailed(self.ui("list", env={"AWDT_UI_TIMEOUT": "0"}), "couldn't read the screen", code=1)

    def test_a_dump_cut_short_is_a_failed_look_too(self):
        self.sandbox.set_behavior(ui_hierarchy=['<hierarchy rotation="0"><node text="A"'])
        result = self.ui("list", env={"AWDT_UI_TIMEOUT": "0"})
        self.assertFailed(result, "couldn't read the screen", code=1)
        self.assertNotIn("Traceback", result.err)


class Waits(UiTestCase):
    """wait and wait-gone look until the screen shows what they wait for, or the limit is up."""

    EMPTY = hierarchy(node(text="Loading"))
    READY = hierarchy(node(text="Ready"))

    def test_wait_until_it_appears(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY, self.EMPTY, self.READY])
        result = self.ui("wait", "Ready")
        self.assertSucceeded(result)
        self.assertEqual(result.output, "")
        self.assertEqual(len(self.dumps()), 3)

    def test_wait_ends_at_once_when_it_is_there(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.READY])
        self.assertSucceeded(self.ui("wait", "Ready"))
        self.assertEqual(len(self.dumps()), 1)

    def test_wait_fails_at_the_limit(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY])
        result = self.ui("wait", "Ready", "1")
        self.assertFailed(result, f"no element matched 'Ready' on {self.serial} within 1 s.", code=1)

    def test_wait_gone_until_it_disappears(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY, self.EMPTY, self.READY])
        result = self.ui("wait-gone", "Loading")
        self.assertSucceeded(result)
        self.assertEqual(result.output, "")
        self.assertEqual(len(self.dumps()), 3)

    def test_wait_gone_ends_at_once_when_it_is_not_there(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.READY])
        self.assertSucceeded(self.ui("wait-gone", "Loading"))
        self.assertEqual(len(self.dumps()), 1)

    def test_wait_gone_fails_at_the_limit(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY])
        result = self.ui("wait-gone", "Loading", "1")
        self.assertFailed(result, f"an element still matches 'Loading' on {self.serial} after 1 s.", code=1)

    def test_a_dump_that_fails_counts_as_not_yet(self):
        self.sandbox.set_behavior(ui_idle_failures=2, ui_hierarchy=[self.READY])
        self.assertSucceeded(self.ui("wait", "Ready"))
        self.assertEqual(len(self.dumps()), 3)

    def test_a_dump_that_fails_does_not_mean_gone(self):
        self.sandbox.set_behavior(ui_idle_failures=2, ui_hierarchy=[self.EMPTY, self.READY])
        self.assertSucceeded(self.ui("wait-gone", "Loading"))
        self.assertEqual(len(self.dumps()), 4, "two failed looks, Loading, then Ready")

    def test_a_screen_that_never_settles_fails_wait_gone(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        self.assertFailed(self.ui("wait-gone", "Loading", "1"), "still matches", code=1)

    def test_a_dump_cut_short_does_not_mean_gone(self):
        self.sandbox.set_behavior(ui_hierarchy=['<hierarchy><node text="Loading"'])
        self.assertFailed(self.ui("wait-gone", "Loading", "0"), "still matches", code=1)

    def test_a_limit_of_zero_is_one_look(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY])
        self.assertFailed(self.ui("wait", "Ready", "0"), "within 0 s", code=1)
        self.assertEqual(len(self.dumps()), 1)

    def test_a_limit_lasts_at_least_its_seconds(self):
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY])
        started = time.time()   # the clock $SECONDS follows
        self.assertFailed(self.ui("wait", "Ready", "1"), "within 1 s", code=1)
        self.assertGreaterEqual(time.time() - started, 1)

    def test_selectors_work_here_too(self):
        self.assertSucceeded(self.ui("wait", "id:sign_in"))
        self.assertSucceeded(self.ui("wait-gone", "class:RadioButton"))

    def test_the_limit_must_be_whole_seconds(self):
        for value in ("soon", "1.5", "-1"):
            with self.subTest(value):
                result = self.ui("wait", "Ready", value)
                self.assertEqual(result.code, 2, result.output)
                self.assertIn("Usage: ui.sh", result.err)
        self.assertEqual(self.dumps(), [])

    def test_without_a_limit_given_it_goes_on_looking(self):
        # Ended by the test: the default is too long to wait out here.
        self.sandbox.set_behavior(ui_hierarchy=[self.EMPTY])
        script = subprocess.Popen([str(self.sandbox.tools / "bin" / "ui.sh"), "wait", "Ready"],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env=self.sandbox.env(),
                                  cwd=self.sandbox.project)
        self.addCleanup(script.wait)
        self.addCleanup(script.kill)
        self.wait_until(lambda: len(self.dumps()) >= 3 or script.poll() is not None)
        self.assertIsNone(script.poll(), "it stopped waiting")


class Shots(UiTestCase):
    def test_writes_the_png_bytes_and_names_the_file(self):
        path = self.sandbox.project / "screen.png"
        result = self.ui("shot", str(path))
        self.assertSucceeded(result)
        self.assertEqual(result.out, f"{path}\n")
        self.assertEqual(path.read_bytes(), b"\x89PNG\r\n\x1a\nfake")

    def test_a_path_relative_to_where_it_runs(self):
        self.assertSucceeded(self.ui("shot", "screen.png"))
        self.assertTrue((self.sandbox.project / "screen.png").exists())

    def test_fails_when_the_device_does(self):
        self.sandbox.set_behavior(screenshot=None)
        self.assertFailed(self.ui("shot", "screen.png"), f"couldn't take a screenshot of {self.serial}", code=1)

    def test_a_shot_needs_a_file(self):
        for args in (["shot"], ["shot", ""], ["shot", "a.png", "b.png"]):
            with self.subTest(args):
                self.assertEqual(self.ui(*args).code, 2)


class Front(UiTestCase):
    def test_prints_the_focus_lines_of_any_api_level(self):
        for level, focused_app in ((36, "ActivityRecord{"), (25, "AppWindowToken{")):
            with self.subTest(level):
                self.sandbox.set_behavior(api_level=level)
                result = self.ui("front")
                self.assertSucceeded(result)
                window, activity = result.out.splitlines()
                self.assertIn(f"mCurrentFocus=Window{{299ed2cc u0 {HOME_WINDOW}}}", window)
                self.assertTrue(activity.startswith(f"mFocusedApp={focused_app}"), activity)
                self.assertIn(HOME, activity)

    def test_prints_the_last_ones_after_an_anr(self):
        # The dump starts with a copy of the state at the last ANR.
        window = ("WINDOW MANAGER LAST ANR\n  mCurrentFocus=Window{1 u0 old/old.Activity}\n"
                  "  mFocusedApp=ActivityRecord{1 u0 old/.Activity t1}\n\n"
                  "WINDOW MANAGER WINDOWS\n  mCurrentFocus=Window{2 u0 new/new.Activity}\n"
                  "  mFocusedApp=ActivityRecord{2 u0 new/.Activity t2}\n")
        self.sandbox.set_behavior(front=[{"window": window, "activities": ""}])
        result = self.ui("front")
        self.assertEqual(result.out, "mCurrentFocus=Window{2 u0 new/new.Activity}\n"
                                     "mFocusedApp=ActivityRecord{2 u0 new/.Activity t2}\n")

    def test_front_shows_one_line_of_each_where_a_dump_repeats_the_focused_app(self):
        # API 29's dump names the focused app again, further down, as Token{...}.
        window = ("  mCurrentFocus=Window{12ccf4c u0 app/app.Main}\n"
                  "  mFocusedApp=AppWindowToken{7af9ca7 token=Token{3cc166 ActivityRecord{ae u0 app/.Main t19}}}\n"
                  "    mFocusedApp=Token{3cc166 ActivityRecord{ae u0 app/.Main t19}}\n")
        self.sandbox.set_behavior(front=[{"window": window, "activities": ""}])
        result = self.ui("front")
        self.assertSucceeded(result)
        self.assertEqual(result.out.splitlines(), [
            "mCurrentFocus=Window{12ccf4c u0 app/app.Main}",
            "mFocusedApp=Token{3cc166 ActivityRecord{ae u0 app/.Main t19}}"])

    def test_takes_no_arguments(self):
        self.assertEqual(self.ui("front", "now").code, 2)

    def test_fails_on_a_device_that_is_not_there(self):
        result = self.ui("-s", "emulator-5999", "front")
        self.assertNotEqual(result.code, 0)
        self.assertEqual(result.out, "")


class Types(UiTestCase):
    def typed(self, text):
        self.assertSucceeded(self.ui("type", text))
        return self.sandbox.device_state(self.serial)["typed"][-1]

    def test_plain_text(self):
        self.assertEqual(self.typed("hello"), "hello")

    def test_spaces_become_percent_s(self):
        self.assertEqual(self.typed("two words  here"), "two%swords%s%shere")

    def test_single_quotes_reach_the_device_as_they_are(self):
        self.assertEqual(self.typed("it's"), "it's")
        self.assertEqual(self.typed("''"), "''")
        self.assertEqual(self.typed("don't can't"), "don't%scan't")

    def test_nothing_is_special_to_the_devices_shell(self):
        for text in ('a"b', "$(reboot)", "`reboot`", "a;b", "a&b", "a|b", "a>b", "*", "a\\b", "#x", "~"):
            with self.subTest(text):
                self.assertEqual(self.typed(text), text)

    def test_non_ascii_is_refused_without_calling_adb(self):
        for text in ("καλημέρα", "café", "emoji 🙂", "tab\there"):
            with self.subTest(text):
                result = self.ui("-s", self.serial, "type", text)
                self.assertFailed(result, "ui.sh type sends ASCII only", code=1)
        self.assertEqual(self.sandbox.argvs("adb"), [])
        self.assertEqual(self.sandbox.device_state(self.serial)["typed"], [])

    def test_type_needs_text(self):
        for args in (["type"], ["type", ""], ["type", "a", "b"]):
            with self.subTest(args):
                self.assertEqual(self.ui(*args).code, 2)
        self.assertEqual(self.sandbox.argvs("adb"), [])

    def test_fails_when_the_device_does(self):
        result = self.ui("-s", "emulator-5999", "type", "hello")
        self.assertNotEqual(result.code, 0)


class WhichDevice(UiTestCase):
    """As touch.sh: the serial given, $ANDROID_SERIAL, the only running emulator."""

    def setUp(self):
        super().setUp()
        self.sandbox.add_avd("tablet")

    def dump_serials(self):
        return [argv[1] for argv in self.dumps()]

    def test_the_only_running_emulator(self):
        self.assertSucceeded(self.ui("list"))
        self.assertEqual(self.dump_serials(), [self.serial])

    def test_the_serial_given(self):
        other = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.ui("-s", other, "list"))
        self.assertEqual(self.dump_serials(), [other])

    def test_android_serial(self):
        other = self.sandbox.start_emulator("tablet")
        self.assertSucceeded(self.ui("list", env={"ANDROID_SERIAL": other}))
        self.assertEqual(self.dump_serials(), [other])

    def test_several_emulators_are_named_in_the_error(self):
        other = self.sandbox.start_emulator("tablet")
        result = self.ui("list")
        self.assertFailed(result, f"several emulators are running ({self.serial} {other})", code=1)
        self.assertEqual(self.dumps(), [])

    def test_no_emulator_names_start_emulator(self):
        self.sandbox.stop_emulators()
        self.assertFailed(self.ui("list"), "no running emulator. Start one with:", code=1)

    def test_a_physical_device_only_when_named(self):
        self.sandbox.connect_device("R58M123ABC")
        self.assertSucceeded(self.ui("list"))
        self.assertEqual(self.dump_serials(), [self.serial])
        self.assertSucceeded(self.ui("-s", "R58M123ABC", "list"))
        self.assertEqual(self.dump_serials(), [self.serial, "R58M123ABC"])

    def test_a_tap_on_a_physical_device_named_by_android_serial(self):
        self.sandbox.connect_device("R58M123ABC")
        self.assertSucceeded(self.ui("tap", "Sign in", env={"ANDROID_SERIAL": "R58M123ABC"}))
        self.assertEqual(self.gestures("R58M123ABC"), [["tap", "300", "650"]])


class WrongArguments(UiTestCase):
    def assertRefused(self, *args):
        result = self.ui(*args)
        self.assertEqual(result.code, 2, result.output)
        self.assertIn("Usage: ui.sh", result.err)
        self.assertEqual(self.sandbox.argvs("adb"), [], "adb must not be called")

    def test_no_command(self):
        self.assertRefused()

    def test_an_unknown_command(self):
        self.assertRefused("press", "OK")

    def test_a_selector_is_needed(self):
        for command in ("find", "tap", "long-press", "wait", "wait-gone"):
            with self.subTest(command):
                self.assertRefused(command)
                self.assertRefused(command, "")

    def test_one_selector_at_most(self):
        for command in ("find", "tap", "long-press"):
            with self.subTest(command):
                self.assertRefused(command, "a", "b")
        self.assertRefused("wait", "a", "1", "2")

    def test_s_needs_a_serial_and_a_command(self):
        self.assertRefused("-s")
        self.assertRefused("-s", "emulator-5554")

    def test_nothing_else_is_needed_for_the_usage(self):
        result = self.sandbox.run("ui.sh", "tap", env={"ANDROID_HOME": "/nonexistent"})
        self.assertEqual(result.code, 2, result.output)

    def test_help_goes_to_stdout(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag):
                result = self.ui(flag)
                self.assertSucceeded(result)
                self.assertIn("Usage: ui.sh", result.out)
                self.assertEqual(result.err, "")

    def test_no_sdk(self):
        self.sandbox.stop_emulators()
        (self.sandbox.home / "Android").rename(self.sandbox.root / "elsewhere")
        self.assertFailed(self.ui("list"), "no Android SDK found", code=1)


class TemporaryFiles(UiTestCase):
    """The local copy of a dump goes away however the command ends."""

    def test_after_a_look_that_worked(self):
        self.assertSucceeded(self.ui("list"))
        self.assertNoTemporaryFiles()

    def test_after_a_tap(self):
        self.assertSucceeded(self.ui("tap", "Sign in"))
        self.assertNoTemporaryFiles()

    def test_after_finding_nothing(self):
        self.assertEqual(self.ui("find", "Nothing like it").code, 1)
        self.assertNoTemporaryFiles()

    def test_after_a_tap_on_nothing(self):
        self.assertEqual(self.ui("tap", "Nothing like it").code, 1)
        self.assertNoTemporaryFiles()

    def test_after_giving_up_on_a_look(self):
        self.sandbox.set_behavior(ui_idle_failures=10**6)
        self.assertEqual(self.ui("list", env={"AWDT_UI_TIMEOUT": "0"}).code, 1)
        self.assertNoTemporaryFiles()

    def test_after_a_wait_that_failed(self):
        self.assertEqual(self.ui("wait", "Nothing like it", "0").code, 1)
        self.assertNoTemporaryFiles()

    def test_after_commands_that_do_not_look(self):
        self.assertSucceeded(self.ui("front"))
        self.assertSucceeded(self.ui("type", "hello"))
        self.assertSucceeded(self.ui("shot", "screen.png"))
        self.assertNoTemporaryFiles()

    def test_after_being_stopped(self):
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="Loading"))])
        script = subprocess.Popen([str(self.sandbox.tools / "bin" / "ui.sh"), "wait", "Ready"],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env=self.sandbox.env(),
                                  cwd=self.sandbox.project)
        self.addCleanup(script.wait)
        self.addCleanup(script.kill)
        self.wait_until(lambda: self.dumps() or script.poll() is not None)
        self.assertTrue(any(self.sandbox.tmp.iterdir()), "it keeps a local copy while it waits")
        os.kill(script.pid, signal.SIGTERM)
        script.wait(timeout=20)
        self.assertNoTemporaryFiles()
