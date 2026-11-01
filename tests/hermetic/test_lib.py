"""lib/: finding the SDK, its tools and AVDs on any setup, how the SDK names images, time limits,
waiting for the home screen, and building the gesture program."""
import textwrap
import time
import unittest

from support.front_look import front_look
from support.sandbox import ScriptTestCase
from support.screens import hierarchy, node


class SdkDiscovery(ScriptTestCase):
    def sdk(self, env=None):
        return self.sandbox.bash('echo "$SDK"', env=env).out.strip()

    def test_android_home_wins_over_every_other_source(self):
        a = self.sandbox.install_sdk(self.sandbox.root / "a")
        b = self.sandbox.install_sdk(self.sandbox.root / "b")
        self.sandbox.install_sdk()
        (self.sandbox.project / "local.properties").write_text(f"sdk.dir={b}\n")
        self.assertEqual(self.sdk({"ANDROID_HOME": str(a), "ANDROID_SDK_ROOT": str(b)}), str(a))

    def test_android_sdk_root_is_used_without_android_home(self):
        b = self.sandbox.install_sdk(self.sandbox.root / "b")
        self.assertEqual(self.sdk({"ANDROID_SDK_ROOT": str(b)}), str(b))

    def test_a_variable_pointing_nowhere_falls_through_to_the_next_source(self):
        default = self.sandbox.install_sdk()
        self.assertEqual(self.sdk({"ANDROID_HOME": "/nonexistent/sdk"}), str(default))

    def test_sdk_dir_from_local_properties_like_gradle(self):
        sdk = self.sandbox.install_sdk(self.sandbox.root / "studio:sdk")
        # Android Studio escapes ':' as '\:' in properties files.
        (self.sandbox.project / "local.properties").write_text(
            f"# written by Android Studio\nsdk.dir={str(sdk).replace(':', chr(92) + ':')}\n")
        self.assertEqual(self.sdk(), str(sdk))

    def test_local_properties_of_the_project_from_one_of_its_subfolders(self):
        sdk = self.sandbox.install_sdk(self.sandbox.root / "studio-sdk")
        self.sandbox.install_sdk()
        (self.sandbox.project / "local.properties").write_text(f"sdk.dir={sdk}\n")
        subfolder = self.sandbox.project / "app" / "src"
        subfolder.mkdir(parents=True)
        self.assertEqual(self.sandbox.bash('echo "$SDK"', cwd=subfolder).out.strip(), str(sdk))

    def test_local_properties_next_to_the_tools_is_not_used(self):
        # Only the project the user is in counts, not wherever this repository is cloned.
        other = self.sandbox.install_sdk(self.sandbox.root / "other")
        default = self.sandbox.install_sdk()
        (self.sandbox.tools / "local.properties").write_text(f"sdk.dir={other}\n")
        self.assertEqual(self.sdk(), str(default))

    def test_sdk_of_the_adb_on_path(self):
        sdk = self.sandbox.install_sdk(self.sandbox.root / "distro-sdk")
        (self.sandbox.bin / "adb").symlink_to(sdk / "platform-tools" / "adb")
        self.assertEqual(self.sdk(), str(sdk))

    def test_android_studio_default_location_last(self):
        self.assertEqual(self.sdk(), str(self.sandbox.install_sdk()))


class ToolDiscovery(ScriptTestCase):
    def tool(self, var, env=None):
        return self.sandbox.bash(f'echo "${var}"', env=env).out.strip()

    def test_tools_come_from_the_sdk(self):
        sdk = self.sandbox.install_sdk()
        self.assertEqual(self.tool("ADB"), str(sdk / "platform-tools/adb"))
        self.assertEqual(self.tool("EMULATOR"), str(sdk / "emulator/emulator"))
        self.assertEqual(self.tool("AVDMANAGER"), str(sdk / "cmdline-tools/latest/bin/avdmanager"))

    def test_newest_versioned_cmdline_tools_when_there_is_no_latest(self):
        # Version order, not text order: 19.0 is newer than 9.0.
        for version in ("9.0", "19.0", "12.0"):
            self.sandbox.install_sdk(tools=["avdmanager"],
                                     layout={"avdmanager": f"cmdline-tools/{version}/bin/avdmanager"})
        self.assertTrue(self.tool("AVDMANAGER").endswith("cmdline-tools/19.0/bin/avdmanager"))

    def test_tools_missing_from_the_sdk_are_taken_from_path(self):
        self.sandbox.install_sdk(tools=["adb"])
        elsewhere = self.sandbox.install_sdk(self.sandbox.root / "other", tools=["emulator"])
        (self.sandbox.bin / "emulator").symlink_to(elsewhere / "emulator/emulator")
        self.assertEqual(self.tool("EMULATOR"), str(self.sandbox.bin / "emulator"))

    def test_missing_tool_names_the_package_to_install(self):
        self.sandbox.install_sdk(tools=["adb", "android"])
        result = self.sandbox.bash('require "$EMULATOR" emulator')
        self.assertFailed(result, 'android sdk install --no-metrics "emulator"')

    def test_the_install_hint_falls_back_to_sdkmanager_before_cmdline_tools_22(self):
        # 'android' only ships from cmdline-tools 22.0; on older ones sdkmanager is all there is,
        # so suggesting the new command would be a command the user doesn't have.
        self.sandbox.install_sdk(tools=["adb", "sdkmanager"])
        result = self.sandbox.bash('require "$EMULATOR" emulator')
        self.assertFailed(result, 'sdkmanager "emulator"')
        self.assertNotIn("android sdk install", result.output)

    def test_the_install_hint_names_the_current_tool_when_the_sdk_has_neither(self):
        self.sandbox.install_sdk(tools=["adb"])
        result = self.sandbox.bash('require "$EMULATOR" emulator')
        self.assertFailed(result, 'android sdk install --no-metrics "emulator"')

    def test_the_install_hint_opts_out_of_telemetry(self):
        # The android CLI reports usage unless --no-metrics is passed, and it can only be turned
        # off per call, so a command we tell the user to paste must carry the flag.
        self.sandbox.install_sdk(tools=["adb", "android"])
        result = self.sandbox.bash('require "$EMULATOR" emulator')
        self.assertIn("--no-metrics", result.output)

    def test_no_sdk_at_all_points_to_setup_instead_of_an_install_command(self):
        result = self.sandbox.bash('require "$ADB" platform-tools')
        self.assertFailed(result, "no Android SDK found")
        self.assertIn(f"{self.sandbox.tools}/docs/SETUP.md", result.output, "a path that works anywhere")
        self.assertNotIn("sdkmanager", result.output)
        self.assertNotIn("android sdk install", result.output)


class CalledFromAnywhere(ScriptTestCase):
    """Users call the scripts by a relative path from any folder, or put bin/ (or symlinks to its
    scripts) on $PATH. Every way must find lib/ and the other scripts."""

    WAYS = ("absolute", "relative", "path", "symlink")

    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="OK"))])

    def test_every_script_works_whichever_way_it_is_called(self):
        elsewhere = self.sandbox.root / "somewhere" / "else"
        elsewhere.mkdir(parents=True)
        for how in self.WAYS:
            for cwd in (self.sandbox.project, elsewhere):
                with self.subTest(how=how, cwd=cwd.name):
                    result = self.sandbox.run("start-emulator.sh", how=how, cwd=cwd)
                    self.assertSucceeded(result)
                    serial = next(iter(self.sandbox.running()))
                    self.assertIn(serial, result.out)
                    self.assertSucceeded(self.sandbox.run("touch.sh", "tap", "1", "1", how=how, cwd=cwd))
                    self.assertSucceeded(self.sandbox.run("ui.sh", "tap", "OK", how=how, cwd=cwd))
                    self.assertSucceeded(self.sandbox.run("stop-emulator.sh", how=how, cwd=cwd))
                    self.assertEqual(self.sandbox.running(), {})

    def test_suggested_commands_are_bare_names_when_on_path(self):
        for script, args in (("touch.sh", ("tap", "1", "1")), ("ui.sh", ("list",))):
            for how in ("path", "symlink"):
                with self.subTest(script=script, how=how):
                    result = self.sandbox.run(script, *args, how=how)
                    self.assertFailed(result, "Start one with: start-emulator.sh\n")

    def test_suggested_commands_use_the_path_the_user_typed(self):
        result = self.sandbox.run("touch.sh", "tap", "1", "1", how="relative")
        self.assertFailed(result, "Start one with: ../tools/bin/start-emulator.sh\n")

    def test_a_different_script_of_the_same_name_on_path_is_not_suggested(self):
        # Another project's start-emulator.sh on $PATH isn't this one, so the path is suggested.
        other = self.sandbox.root / "other-tools"
        other.mkdir()
        (other / "start-emulator.sh").write_text("#!/bin/sh\n")
        (other / "start-emulator.sh").chmod(0o755)
        result = self.sandbox.run("touch.sh", "tap", "1", "1", how="relative",
                                  env={"PATH": f"{other}:{self.sandbox.bin}"})
        self.assertFailed(result, "Start one with: ../tools/bin/start-emulator.sh\n")


class SourcesOnlyWhatItNeeds(ScriptTestCase):
    """A script sources only the libraries it needs (lib/README.md): it works without the others."""

    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")

    def without(self, *libraries):
        for library in libraries:
            (self.sandbox.tools / "lib" / library).unlink()

    def test_create_avd(self):
        self.without("device.sh", "home.sh")
        self.assertSucceeded(self.sandbox.run("create-avd.sh", "my_phone"))

    def test_stop_emulator(self):
        self.without("home.sh")
        self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.sandbox.run("stop-emulator.sh"))

    def test_touch_and_ui(self):
        self.without("avd.sh", "home.sh")
        self.sandbox.set_behavior(ui_hierarchy=[hierarchy(node(text="OK"))])
        self.sandbox.start_emulator("phone_api36")
        self.assertSucceeded(self.sandbox.run("touch.sh", "tap", "1", "1"))
        self.assertSucceeded(self.sandbox.run("ui.sh", "tap", "OK"))


class AvdDiscovery(ScriptTestCase):
    def avd_dir(self, name, env=None):
        return self.sandbox.bash(f'avd_dir {name}', env=env)

    def test_default_avd_folder(self):
        folder = self.sandbox.add_avd("phone")
        self.assertEqual(self.avd_dir("phone").out.strip(), str(folder))

    def test_every_variable_that_moves_the_avd_folder(self):
        root = self.sandbox.root
        cases = {"ANDROID_AVD_HOME": root / "avd-home",
                 "ANDROID_EMULATOR_HOME": root / "emu-home" / "avd",
                 "ANDROID_USER_HOME": root / "user-home" / "avd",
                 "ANDROID_SDK_HOME": root / "sdk-home" / ".android" / "avd"}
        for var, home in cases.items():
            with self.subTest(var):
                folder = self.sandbox.add_avd(f"phone_{var.lower()}", home=home)
                base = {"ANDROID_AVD_HOME": home, "ANDROID_EMULATOR_HOME": home.parent,
                        "ANDROID_USER_HOME": home.parent,
                        "ANDROID_SDK_HOME": home.parent.parent}[var]
                result = self.avd_dir(f"phone_{var.lower()}", env={var: str(base)})
                self.assertEqual(result.out.strip(), str(folder))

    def test_follows_the_ini_path_to_an_avd_stored_elsewhere(self):
        # The AVD's folder is on another disk; only its .ini is in the AVD folder.
        folder = self.sandbox.add_avd("phone", home=self.sandbox.root / "big-disk")
        (folder.parent / "phone.ini").unlink()
        home = self.sandbox.home / ".android" / "avd"
        home.mkdir(parents=True)
        (home / "phone.ini").write_text(f"path={folder}\n")
        self.assertEqual(self.avd_dir("phone").out.strip(), str(folder))

    def test_unknown_avd_fails(self):
        self.assertNotEqual(self.avd_dir("missing").code, 0)

    def test_list_avds_ignores_emulator_log_lines(self):
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")
        self.sandbox.add_avd("tablet.big-1")
        self.assertEqual(self.sandbox.bash("list_avds").out.split(), ["phone_api36", "tablet.big-1"])

    def test_the_image_an_avd_was_made_from(self):
        # "key = value" once the emulator has rewritten config.ini, "key=value" as avdmanager wrote it.
        rewritten = self.sandbox.add_avd("rewritten", image="system-images/android-36/default/x86_64/")
        written = self.sandbox.add_avd("written")
        (written / "config.ini").write_text("image.sysdir.1=system-images/android-34/google_apis/x86_64/\r\n")
        for folder, image in ((rewritten, "system-images/android-36/default/x86_64/"),
                              (written, "system-images/android-34/google_apis/x86_64/")):
            with self.subTest(image):
                self.assertEqual(self.sandbox.bash(f"avd_image {folder}").out, f"{image}\n")

    def test_no_image_named_is_empty(self):
        folder = self.sandbox.add_avd("phone")
        self.assertEqual(self.sandbox.bash(f"avd_image {folder}").out, "")


class ImageNames(ScriptTestCase):
    """image_level and image_abi: how the SDK names an image's folder and package."""

    def setUp(self):
        super().setUp()
        self.sandbox.sdk = self.sandbox.install_sdk()

    def level(self, level, tag="default"):
        return self.sandbox.bash(f"image_level {level} {tag}").out.strip()

    def abi(self, level, tag="default"):
        return self.sandbox.bash(f"image_abi {level} {tag}").out.strip()

    def install(self, level, tag="default"):
        (self.sandbox.sdk / f"system-images/android-{level}/{tag}").mkdir(parents=True)

    def test_up_to_api_36_a_level_is_its_folder(self):
        for level in ("22", "30", "36"):
            with self.subTest(level):
                self.assertEqual(self.level(level), level)

    def test_from_api_37_on_the_first_release_of_a_level_is_x_0(self):
        for level in ("37", "38", "100"):
            with self.subTest(level):
                self.assertEqual(self.level(level), f"{level}.0")

    def test_a_level_given_with_its_minor_version_stays(self):
        for level in ("36.1", "37.0", "37.1"):
            with self.subTest(level):
                self.assertEqual(self.level(level), level)

    def test_an_installed_folder_wins(self):
        self.install("37")
        self.install("36.0")
        self.assertEqual(self.level("37"), "37")
        self.assertEqual(self.level("36"), "36.0")

    def test_only_a_folder_of_that_tag_counts(self):
        self.install("36.0", "google_apis")
        self.assertEqual(self.level("36"), "36")
        self.assertEqual(self.level("36", "google_apis"), "36.0")

    def test_x86_64_on_every_level_but_google_apis_on_27(self):
        self.assertEqual(self.abi("36"), "x86_64")
        self.assertEqual(self.abi("27"), "x86_64")
        self.assertEqual(self.abi("26", "google_apis"), "x86_64")
        self.assertEqual(self.abi("27", "google_apis"), "x86")


class TimeLimits(ScriptTestCase):
    def test_a_limit_lasts_at_least_its_seconds(self):
        # Started late in a whole second of $SECONDS, which ticks with the clock's seconds: a
        # limit counted as `$SECONDS - start >= 1` would be up at the next tick, 0.1 s later.
        result = self.sandbox.bash("""
            tick=$SECONDS; while [ "$SECONDS" = "$tick" ]; do sleep 0.01; done
            sleep 0.85
            start=$SECONDS started=$EPOCHREALTIME
            until time_is_up "$start" 1; do sleep 0.01; done
            echo "$started $EPOCHREALTIME"
        """)
        started, ended = map(float, result.out.split())
        self.assertGreaterEqual(ended - started, 1)

    def test_a_limit_of_zero_is_up_at_once(self):
        self.assertEqual(self.sandbox.bash("time_is_up $SECONDS 0").code, 0)


def dumps(window, activities):
    """A look at a device: `dumpsys window` and `dumpsys activity activities` as the fake adb
    shows them (a `front` item, fake_tools.py), here trimmed to the lines wait_for_home reads."""
    return {"window": textwrap.dedent(window).lstrip(), "activities": textwrap.dedent(activities).lstrip()}


# The fake device's home app (fake_tools.py's default), and another launcher's.
HOME = "com.android.launcher3/.uioverrides.QuickstepLauncher"
HOME_WINDOW = "com.android.launcher3/com.android.launcher3.uioverrides.QuickstepLauncher"
NEXUS = "com.google.android.apps.nexuslauncher"
NEXUS_HOME = f"{NEXUS}/.NexusLauncherActivity"
LAUNCHER3 = "com.android.launcher3"
# A launcher (API 31) after a boot starved of CPU: its trampoline in front, in a task of its own,
# its home task below.
DISPATCH = dumps("""
    mCurrentFocus=Window{b99fc88 u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.boot.DispatchActivity}
    mFocusedApp=ActivityRecord{d2732d0 u0 com.google.android.apps.nexuslauncher/.boot.DispatchActivity t4}
    """, """
    * Hist #0: ActivityRecord{d2732d0 u0 com.google.android.apps.nexuslauncher/.boot.DispatchActivity t4}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true mStartingWindowState=STARTING_WINDOW_SHOWN
    * Hist #0: ActivityRecord{97a36c0 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t3}
      state=STOPPING stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true mStartingWindowState=STARTING_WINDOW_NOT_SHOWN
    """)
# A launcher (API 33, starved), back from Settings: the home screen resumed, its main thread still
# busy, its welcome screen to come.
HOME_RESUMING = dumps("""
    mCurrentFocus=Window{667f478 u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.NexusLauncherActivity}
    mFocusedApp=ActivityRecord{af5a038 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity} t54}
    """, """
    * Hist  #0: ActivityRecord{af5a038 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity} t54}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=false
    * Hist  #0: ActivityRecord{5bce39 u0 com.android.settings/.Settings} t56}
      state=PAUSED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    * Hist  #0: ActivityRecord{adc0b13 u0 com.google.android.apps.nexuslauncher/.boot.DispatchActivity} t55}
      state=STOPPED stopped=true delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    """)
# A launcher (API 31, starved): the welcome screen already on top, the home screen's window still
# focused.
WELCOME_COMING = dumps("""
    mCurrentFocus=Window{92bd30e u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.NexusLauncherActivity}
    mFocusedApp=ActivityRecord{4c189ad u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t123}
    """, """
    * Hist #1: ActivityRecord{17486f9 u0 com.google.android.apps.nexuslauncher/.setup.WelcomeActivity t123}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=false mStartingWindowState=STARTING_WINDOW_NOT_SHOWN
    * Hist #0: ActivityRecord{4c189ad u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t123}
      state=PAUSED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=false mStartingWindowState=STARTING_WINDOW_NOT_SHOWN
    * Hist #0: ActivityRecord{5ef996 u0 com.android.settings/.Settings t127}
      state=PAUSED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true mStartingWindowState=STARTING_WINDOW_REMOVED
    """)
# A launcher (API 33): the welcome screen the home screen opened over itself, in its task.
WELCOME = dumps("""
    mCurrentFocus=Window{436542c u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.setup.WelcomeActivity}
    mFocusedApp=ActivityRecord{5e6ffcc u0 com.google.android.apps.nexuslauncher/.setup.WelcomeActivity} t88}
    """, """
    * Hist  #1: ActivityRecord{5e6ffcc u0 com.google.android.apps.nexuslauncher/.setup.WelcomeActivity} t88}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    * Hist  #0: ActivityRecord{d04d35a u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity} t88}
      state=STOPPED stopped=true delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    * Hist  #0: ActivityRecord{c1960b2 u0 com.android.settings/.Settings} t84}
      state=STOPPED stopped=true delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    """)
# A launcher (API 31, starved), after an input ANR: `dumpsys window` starts with the state at that
# time, focus included (the home screen, before its welcome screen came); the live state follows.
ANR_COPY = """
    WINDOW MANAGER LAST ANR (dumpsys window lastanr)
      ANR time: 10/1/26 14:02
      Application at fault: com.android.settings
      WINDOW MANAGER WINDOWS (dumpsys window windows)
        mCurrentFocus=Window{59570 u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.NexusLauncherActivity}
        mFocusedApp=ActivityRecord{97a36c0 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t3}

    WINDOW MANAGER WINDOWS (dumpsys window windows)
    """
WELCOME_AFTER_ANR = dumps(ANR_COPY + """
      mCurrentFocus=Window{1947a15 u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.setup.WelcomeActivity}
      mFocusedApp=ActivityRecord{8d251c4 u0 com.google.android.apps.nexuslauncher/.setup.WelcomeActivity t3}
    """, """
    * Hist #1: ActivityRecord{8d251c4 u0 com.google.android.apps.nexuslauncher/.setup.WelcomeActivity t3}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true mStartingWindowState=STARTING_WINDOW_NOT_SHOWN
    * Hist #0: ActivityRecord{97a36c0 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t3}
      state=STOPPING stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true mStartingWindowState=STARTING_WINDOW_NOT_SHOWN
    """)
# The same copy, with Settings in front now (made up from the two).
SETTINGS_AFTER_ANR = dumps(ANR_COPY + """
      mCurrentFocus=Window{af46328 u0 com.android.settings/com.android.settings.Settings}
      mFocusedApp=ActivityRecord{5ef996 u0 com.android.settings/.Settings t127}
    """, """
    * Hist #0: ActivityRecord{5ef996 u0 com.android.settings/.Settings t127}
      state=RESUMED stopped=false delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    * Hist #0: ActivityRecord{97a36c0 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t3}
      state=STOPPED stopped=true delayedResume=false finishing=false
      keysPaused=false inHistory=true idle=true
    """)
# API 22 with a second home app installed: Home asks which one to use, in a task the HOME intent
# started.
API22_CHOOSER = dumps("""
    mFocusedApp=Token{af0e5cd ActivityRecord{179a7f64 u0 android/com.android.internal.app.ResolverActivity t5}}
    mCurrentFocus=Window{25456fc u0 android/com.android.internal.app.ResolverActivity}
    mFocusedApp=AppWindowToken{18247e82 token=Token{af0e5cd ActivityRecord{179a7f64 u0 android/com.android.internal.app.ResolverActivity t5}}}
    """, """
    * TaskRecord{83f5bda #5 I=android/com.android.internal.app.ResolverActivity U=0 sz=1}
      intent={act=android.intent.action.MAIN cat=[android.intent.category.HOME] flg=0x10a00000 cmp=android/com.android.internal.app.ResolverActivity}
      * Hist #0: ActivityRecord{179a7f64 u0 android/com.android.internal.app.ResolverActivity t5}
        Intent { act=android.intent.action.MAIN cat=[android.intent.category.HOME] flg=0x10a00000 cmp=android/com.android.internal.app.ResolverActivity }
        frontOfTask=true task=TaskRecord{83f5bda #5 I=android/com.android.internal.app.ResolverActivity U=0 sz=1}
        state=RESUMED stopped=false delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=true sleeping=false idle=true
    * TaskRecord{287db0af #2 A=com.android.settings U=0 sz=1}
      intent={act=android.settings.SETTINGS flg=0x10000000 cmp=com.android.settings/.Settings}
      * Hist #0: ActivityRecord{1971a648 u0 com.android.settings/.Settings t2}
        state=STOPPED stopped=true delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=true sleeping=false idle=true
      mFocusedActivity: ActivityRecord{179a7f64 u0 android/com.android.internal.app.ResolverActivity t5}
    """)
# API 22: the stock launcher, just started by a HOME intent, its main thread still busy.
API22_LAUNCHER_STARTING = dumps("""
    mFocusedApp=Token{10d155f9 ActivityRecord{27eb24c0 u0 com.android.launcher3/.Launcher t3}}
    mCurrentFocus=Window{38c69fb4 u0 com.android.launcher3/com.android.launcher3.Launcher}
    mFocusedApp=AppWindowToken{28e9a93e token=Token{10d155f9 ActivityRecord{27eb24c0 u0 com.android.launcher3/.Launcher t3}}}
    """, """
    * TaskRecord{b796e5a #3 A=com.android.launcher3 U=0 sz=1}
      intent={act=android.intent.action.MAIN cat=[android.intent.category.HOME] flg=0x10000000 cmp=com.android.launcher3/.Launcher}
      * Hist #0: ActivityRecord{27eb24c0 u0 com.android.launcher3/.Launcher t3}
        state=RESUMED stopped=false delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=true sleeping=false idle=false
    * TaskRecord{287db0af #2 A=com.android.settings U=0 sz=1}
      intent={act=android.settings.SETTINGS flg=0x10000000 cmp=com.android.settings/.Settings}
      * Hist #0: ActivityRecord{1971a648 u0 com.android.settings/.Settings t2}
        state=PAUSED stopped=false delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=false sleeping=false idle=true
      mFocusedActivity: ActivityRecord{27eb24c0 u0 com.android.launcher3/.Launcher t3}
    """)
# API 23 after a first boot: the stock launcher, in a task a HOME intent started, over a storage
# wizard.
API23_LAUNCHER = dumps("""
    mFocusedApp=Token{4e9b05d ActivityRecord{ac49a34 u0 com.android.launcher3/.Launcher t2}}
    mCurrentFocus=Window{44b339a u0 com.android.launcher3/com.android.launcher3.Launcher}
    mFocusedApp=AppWindowToken{2a9dd2 token=Token{4e9b05d ActivityRecord{ac49a34 u0 com.android.launcher3/.Launcher t2}}}
    """, """
    * TaskRecord{78919e4 #2 A=com.android.launcher3 U=0 sz=1}
      intent={act=android.intent.action.MAIN cat=[android.intent.category.HOME] flg=0x10000000 cmp=com.android.launcher3/.Launcher}
      * Hist #0: ActivityRecord{ac49a34 u0 com.android.launcher3/.Launcher t2}
        state=RESUMED stopped=false delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=true sleeping=false idle=true
    * TaskRecord{59bae4d #1 I=com.android.settings/.deviceinfo.StorageWizardInit U=0 sz=1}
      intent={act=com.android.settings.deviceinfo.NEW_STORAGE flg=0x10008000 cmp=com.android.settings/.deviceinfo.StorageWizardInit}
      * Hist #0: ActivityRecord{6572a0 u0 com.android.settings/.deviceinfo.StorageWizardInit t1}
        state=STOPPED stopped=true delayedResume=false finishing=false
        keysPaused=false inHistory=true visible=false sleeping=false idle=true
      mFocusedActivity: ActivityRecord{ac49a34 u0 com.android.launcher3/.Launcher t2}
    """)


def idle(look):
    """The same look, once the top activity's main thread has gone idle."""
    return {**look, "activities": look["activities"].replace("idle=false", "idle=true", 1)}


class WaitForHome(ScriptTestCase):
    """wait_for_home <serial> <seconds> [<backs>] (what start-emulator.sh --wait-for-home runs) on
    dumps in the form emulators produce: the home screen is settled when the top activity is in the
    home app's task, resumed and idle, the focused activity, and its own window has the focus, at
    two looks in a row. AWDT_BACK_AFTER=1 here, so another app's screen gets Back after 1 s, not
    10."""

    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()
        self.sandbox.add_avd("phone_api36")
        self.serial = self.sandbox.start_emulator("phone_api36")

    def wait(self, limit=20, backs=0, env=None):
        return self.sandbox.bash(f"wait_for_home {self.serial} {limit} {backs}",
                                 env={"AWDT_BACK_AFTER": "1", **(env or {})})

    def nexus_launcher(self, api_level, front):
        self.sandbox.set_behavior(api_level=api_level, home_resolves=[NEXUS_HOME], front=front)

    def looks(self):
        return [call for call in self.sandbox.calls("adb") if call["argv"][-2:] == ["dumpsys", "window"]]

    def backs(self):
        return [call for call in self.sandbox.calls("adb") if call["argv"][-3:] == ["input", "keyevent", "BACK"]]

    def test_waits_past_a_launchers_boot_trampoline(self):
        # DispatchActivity is the home app's, but in a task of its own: the home task comes over it.
        self.nexus_launcher(31, [DISPATCH] * 3 + [WELCOME_AFTER_ANR])
        result = self.wait()
        self.assertSucceeded(result)
        self.assertEqual(result.out, f"{NEXUS}\n")
        self.assertEqual(len(self.looks()), 5, "took DispatchActivity for the home screen")

    def test_never_presses_back_on_a_screen_of_the_home_app(self):
        # A Back on DispatchActivity could end the launcher's decision what to show.
        self.nexus_launcher(31, [DISPATCH])
        result = self.wait(limit=3, backs=2)
        self.assertEqual(result.code, 1)
        self.assertEqual(self.backs(), [])
        self.assertIn(f"activity {NEXUS}/.boot.DispatchActivity, focused window "
                      f"{NEXUS}/{NEXUS}.boot.DispatchActivity; a HOME intent "
                      f"resolves to {NEXUS_HOME}; the top activity is "
                      f"{NEXUS}/.boot.DispatchActivity in task 4, RESUMED, idle",
                      result.out)

    def test_waits_until_the_home_app_has_finished_starting(self):
        # Resumed and focused, but its main thread still busy: it may open its welcome screen.
        self.nexus_launcher(33, [HOME_RESUMING] * 3 + [idle(HOME_RESUMING)])
        self.assertSucceeded(self.wait())
        self.assertEqual(len(self.looks()), 5)

    def test_waits_while_a_welcome_screen_comes_up(self):
        # On top, but the home screen's window still has the focus.
        self.nexus_launcher(31, [WELCOME_COMING] * 2 + [WELCOME_AFTER_ANR])
        self.assertSucceeded(self.wait())
        self.assertEqual(len(self.looks()), 4)

    def test_takes_a_screen_the_home_app_opened_in_its_task_for_the_home_screen(self):
        # A launcher's welcome screen on a first boot.
        self.nexus_launcher(33, [WELCOME])
        result = self.wait()
        self.assertSucceeded(result)
        self.assertEqual(result.out, f"{NEXUS}\n")
        self.assertEqual(len(self.looks()), 2, "two looks in a row")

    def test_reads_the_live_focus_after_an_anr(self):
        # The copy at the dump's start names the home screen, the live lines Settings.
        self.nexus_launcher(31, [SETTINGS_AFTER_ANR])
        result = self.wait(limit=2)
        self.assertEqual(result.code, 1, "took the focus at the last ANR for the current one")
        self.assertIn("activity com.android.settings/.Settings, focused window "
                      "com.android.settings/com.android.settings.Settings;", result.out)
        # And the other way around: the live lines name the welcome screen.
        self.sandbox.set_behavior(front=[WELCOME_AFTER_ANR])
        self.assertSucceeded(self.wait())

    def test_a_new_window_of_the_home_screen_needs_two_looks_again(self):
        # A launcher can restart after a boot (an update), with a new window.
        again = {**WELCOME, "window": WELCOME["window"].replace("436542c", "5d10e2f")}
        self.nexus_launcher(33, [WELCOME, again, again])
        self.assertSucceeded(self.wait())
        self.assertEqual(len(self.looks()), 3)

    def test_before_api_24_the_chooser_in_the_task_home_started_is_the_home_screen(self):
        self.sandbox.set_behavior(api_level=22, front=[API22_CHOOSER])
        result = self.wait()
        self.assertSucceeded(result)
        self.assertEqual(result.out, "android\n")

    def test_before_api_24_waits_until_the_launcher_has_finished_starting(self):
        self.sandbox.set_behavior(api_level=22, front=[API22_LAUNCHER_STARTING] * 2
                                  + [idle(API22_LAUNCHER_STARTING)])
        result = self.wait()
        self.assertSucceeded(result)
        self.assertEqual(result.out, f"{LAUNCHER3}\n")
        self.assertEqual(len(self.looks()), 4)

    def test_before_api_24_the_launcher_over_another_task_is_the_home_screen(self):
        self.sandbox.set_behavior(api_level=23, front=[API23_LAUNCHER])
        result = self.wait()
        self.assertSucceeded(result)
        self.assertEqual(result.out, f"{LAUNCHER3}\n")

    def test_presses_back_once_another_apps_screen_has_kept_the_focus_back_after_seconds(self):
        usb = ["com.android.settings/.deviceinfo.StorageWizardInit",
               "com.android.settings/com.android.settings.deviceinfo.StorageWizardInit"]
        self.sandbox.set_behavior(front=[usb, "BACK", [HOME, HOME_WINDOW]])
        self.assertSucceeded(self.wait(backs=2, env={"AWDT_BACK_AFTER": "2"}))
        [back] = self.backs()
        self.assertGreaterEqual(back["time"] - self.looks()[0]["time"], 2)

    def test_fails_soon_once_another_apps_window_has_kept_the_focus(self):
        # An app left in front (someone's device, a dialog) isn't on the way to the home screen: no
        # need to wait out the long limit for it.
        settings = ["com.android.settings/.Settings",
                    "com.android.settings/com.android.settings.Settings"]
        self.sandbox.set_behavior(front=[settings])
        started = time.monotonic()
        result = self.wait(limit=60, env={"AWDT_OTHER_APP_TIMEOUT": "2"})
        self.assertEqual(result.code, 2, result.output)
        self.assertLess(time.monotonic() - started, 30, "waited the long limit")
        self.assertEqual(result.out, f"activity {settings[0]}, focused window {settings[1]}; a HOME "
                                     f"intent resolves to {HOME}; the top activity is {settings[0]} "
                                     "in task 9, RESUMED, idle\n")
        self.assertGreaterEqual(self.looks()[-1]["time"] - self.looks()[0]["time"], 2)
        self.assertEqual(self.backs(), [], "pressed a key on another app's screen")

    def test_presses_its_backs_before_the_short_limit(self):
        usb = ["com.android.settings/.deviceinfo.StorageWizardInit",
               "com.android.settings/com.android.settings.deviceinfo.StorageWizardInit"]
        self.sandbox.set_behavior(front=[usb])
        result = self.wait(limit=60, backs=2, env={"AWDT_OTHER_APP_TIMEOUT": "3"})
        self.assertEqual(result.code, 2, result.output)
        self.assertEqual(len(self.backs()), 2)

    def test_fails_with_status_3_when_no_home_app_is_enabled(self):
        # The user unlocked, and still nothing but FallbackHome for a HOME intent, at two looks.
        fallback = "com.android.settings/.FallbackHome"
        window = "com.android.settings/com.android.settings.FallbackHome"
        self.sandbox.set_behavior(api_level=36, home_resolves=[fallback], user_unlocked=True,
                                  front=[[fallback, window]])
        result = self.wait(limit=60)
        self.assertEqual(result.code, 3, result.output)
        self.assertEqual(result.out, f"activity {fallback}, focused window {window}; a HOME intent "
                                     f"resolves to {fallback}; the top activity is {fallback} in "
                                     "task 7, RESUMED, idle\n")
        self.assertEqual(len(self.looks()), 2)

    def test_the_home_apps_own_screen_gets_the_long_limit(self):
        # A launcher's trampoline can hold the focus for minutes on a slow host.
        self.nexus_launcher(31, [DISPATCH])
        result = self.wait(limit=4, env={"AWDT_OTHER_APP_TIMEOUT": "1"})
        self.assertEqual(result.code, 1, result.output)
        self.assertGreaterEqual(self.looks()[-1]["time"] - self.looks()[0]["time"], 4)

    def test_no_focused_window_gets_the_long_limit(self):
        # Right after a boot, or while one screen hands over to the next.
        self.sandbox.set_behavior(front=[[HOME, None]])
        result = self.wait(limit=4, env={"AWDT_OTHER_APP_TIMEOUT": "1"})
        self.assertEqual(result.code, 1, result.output)
        self.assertGreaterEqual(self.looks()[-1]["time"] - self.looks()[0]["time"], 4)


SETTINGS = "com.android.settings/.Settings"


class HomeLookForAnotherActivity(unittest.TestCase):
    """front_look: home_look for another activity than the home app's, given API 24's rules on
    every API level, to wait until Settings, or whatever activity has the focus, has settled in
    front."""

    def look(self, dumps, activity=""):
        return front_look(dumps["window"], dumps["activities"], activity)

    def test_settings_settled_in_front(self):
        settled, key, app, _ = self.look(SETTINGS_AFTER_ANR, SETTINGS)
        self.assertTrue(settled)
        self.assertEqual(app, SETTINGS)
        self.assertEqual(key, "5ef996 Window{af46328 u0 com.android.settings/"
                              "com.android.settings.Settings}")

    def test_not_settings_while_another_app_is_over_it(self):
        settled, _, app, shown = self.look(WELCOME, SETTINGS)
        self.assertFalse(settled)
        self.assertEqual(app, f"{NEXUS}/.setup.WelcomeActivity")
        self.assertIn(f"top activity {NEXUS}/.setup.WelcomeActivity in task "
                      "88, RESUMED, idle", shown)

    def test_the_focused_activity_once_it_has_finished_starting(self):
        self.assertFalse(self.look(HOME_RESUMING)[0])
        self.assertTrue(self.look(idle(HOME_RESUMING))[0])

    def test_not_while_another_activity_comes_over_the_focused_one(self):
        # The welcome screen is on top; the home screen still has the focus.
        self.assertFalse(self.look(WELCOME_COMING)[0])

    def test_not_while_a_window_that_is_no_activitys_has_the_focus(self):
        dialog = {**WELCOME, "window": WELCOME["window"].replace(
            f"Window{{436542c u0 {NEXUS}/{NEXUS}.setup.WelcomeActivity}}",
            "Window{2c1b5e0 u0 Application Not Responding: com.android.settings}")}
        self.assertTrue(self.look(WELCOME)[0])
        self.assertFalse(self.look(dialog)[0])

    def test_before_api_24_too(self):
        self.assertFalse(self.look(API22_LAUNCHER_STARTING)[0])
        settled, _, app, _ = self.look(idle(API22_LAUNCHER_STARTING))
        self.assertTrue(settled)
        self.assertEqual(app, f"{LAUNCHER3}/.Launcher")
        self.assertTrue(self.look(API22_CHOOSER)[0])


class BuildsTheGestureProgram(ScriptTestCase):
    """build-gesture.sh, with a fake javac and d8: which tools it picks, and that Gesture.dex is
    replaced only by a finished build."""

    DEX = "lib/Gesture.dex"

    def setUp(self):
        super().setUp()
        self.sdk = self.sandbox.install_sdk(tools=["adb"])
        self.sandbox.host_tool("javac")
        self.script = self.sandbox.tools / "lib" / "build-gesture.sh"

    def add_d8(self, version):
        self.sandbox.write_fake(self.sdk / "build-tools" / version / "d8", "d8")

    def add_platform(self, name):
        (self.sdk / "platforms" / name).mkdir(parents=True)
        (self.sdk / "platforms" / name / "android.jar").write_text("")

    def build(self):
        return self.sandbox.run_file(self.script)

    def dex(self):
        return (self.sandbox.tools / self.DEX).read_text(errors="replace")

    def test_builds_with_the_newest_d8_and_platform(self):
        for version in ("9.0.0", "36.0.0", "10.0.0"):
            self.add_d8(version)
        for name in ("android-9", "android-36", "android-10"):
            self.add_platform(name)
        result = self.build()
        self.assertSucceeded(result)
        [d8] = [c for c in self.sandbox.calls("d8")]
        self.assertIn("--min-api", d8["argv"])
        self.assertEqual(self.dex(), "built by d8 36.0.0")
        [javac] = self.sandbox.argvs("javac")
        self.assertEqual(javac[javac.index("-cp") + 1], str(self.sdk / "platforms/android-36/android.jar"))
        self.assertEqual(javac[-1], str(self.script.parent / "Gesture.java"))
        self.assertIn(f"Built {self.sandbox.tools / self.DEX} (18 bytes)", result.out)

    def test_needs_d8(self):
        self.add_platform("android-36")
        self.assertFailed(self.build(), "no d8 under")
        self.assertEqual(self.sandbox.argvs("javac"), [])

    def test_needs_a_platform(self):
        self.add_d8("36.0.0")
        self.assertFailed(self.build(), "no android.jar under")
        self.assertEqual(self.sandbox.argvs("javac"), [])

    def test_a_failed_compile_keeps_the_program_and_leaves_nothing_behind(self):
        self.add_d8("36.0.0")
        self.add_platform("android-36")
        self.sandbox.set_behavior(javac_error="Gesture.java:1: error: class expected")
        before = self.dex()
        result = self.build()
        self.assertFailed(result, "class expected")
        self.assertEqual(self.dex(), before)
        self.assertEqual(self.sandbox.argvs("d8"), [])
        self.assertEqual(list(self.sandbox.tmp.iterdir()), [], "its work folder is removed")
