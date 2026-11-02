"""mobile-create-avd.sh: creating a phone or tablet emulator with the right settings, wherever AVDs live."""
from support.sandbox import ScriptTestCase

EXPECTED_SETTINGS = {
    "hw.keyboard": "yes", "hw.ramSize": "2048", "hw.cpu.ncore": "4",
    "disk.dataPartition.size": "4G", "hw.gpu.enabled": "yes", "hw.gpu.mode": "swangle_indirect",
    "showDeviceFrame": "no", "hw.audioInput": "no",
}


API36_IMAGE = "system-images/android-36/default/x86_64/"


def read_config(folder):
    lines = (folder / "config.ini").read_text().splitlines()
    return [tuple(line.split("=", 1)) for line in lines if "=" in line]


def value(argv, flag):
    return argv[argv.index(flag) + 1]


def install_image(sandbox, level, tag="default", abi="x86_64"):
    """Installs a system image's folder in the sandbox's SDK, with its package.xml."""
    image = sandbox.sdk / f"system-images/android-{level}/{tag}/{abi}"
    image.mkdir(parents=True)
    (image / "package.xml").write_text("")


class CreatesAnAvd(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()

    def created(self):
        """The arguments of the one AVD avdmanager created last."""
        return self.sandbox.argvs("avdmanager")[-1]

    def config(self, name):
        return read_config(self.sandbox.home / ".android/avd" / f"{name}.avd")

    def test_creates_phone_api36_from_the_api36_image(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh"))
        [argv] = self.sandbox.argvs("avdmanager")
        for flag, expected in {"--name": "phone_api36",
                               "--package": "system-images;android-36;default;x86_64",
                               "--tag": "default", "--abi": "x86_64", "--device": "medium_phone"}.items():
            self.assertEqual(value(argv, flag), expected, flag)

    def test_applies_every_hardware_setting_exactly_once(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh"))
        config = self.config("phone_api36")
        keys = [key for key, _ in config]
        for key, expected in EXPECTED_SETTINGS.items():
            with self.subTest(key):
                self.assertIn((key, expected), config)
                self.assertEqual(keys.count(key), 1, "a setting must replace, not duplicate, a key")
        self.assertIn(("tag.id", "default"), config, "unrelated keys are kept")

    def test_uses_the_given_name(self):
        result = self.sandbox.run("mobile-create-avd.sh", "my_phone", how="relative")
        self.assertSucceeded(result)
        self.assertTrue((self.sandbox.home / ".android/avd/my_phone.avd/config.ini").exists())
        self.assertIn("Start it with: ../tools/bin/mobile-start-emulator.sh my_phone", result.out)

    def test_suggests_the_bare_command_when_on_path(self):
        result = self.sandbox.run("mobile-create-avd.sh", how="path")
        self.assertIn("Start it with: mobile-start-emulator.sh phone_api36", result.out)

    def test_default_name_from_awdt_avd(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", env={"AWDT_AVD": "work_phone"}))
        self.assertTrue((self.sandbox.home / ".android/avd/work_phone.avd").is_dir())

    def test_api_picks_the_image_of_that_level_and_names_the_avd_after_it(self):
        for level in ("22", "28", "30", "33", "36"):
            with self.subTest(level):
                result = self.sandbox.run("mobile-create-avd.sh", "--api", level)
                self.assertSucceeded(result)
                argv = self.created()
                self.assertEqual(value(argv, "--name"), f"phone_api{level}")
                self.assertEqual(value(argv, "--package"),
                                 f"system-images;android-{level};default;x86_64")
                self.assertIn(("hw.keyboard", "yes"), self.config(f"phone_api{level}"))
                self.assertIn(f"mobile-start-emulator.sh phone_api{level}", result.out)

    def test_a_level_with_its_minor_version_is_taken_as_it_is(self):
        result = self.sandbox.run("mobile-create-avd.sh", "--api", "36.1")
        self.assertSucceeded(result)
        argv = self.created()
        self.assertEqual(value(argv, "--name"), "phone_api36.1")
        self.assertEqual(value(argv, "--package"), "system-images;android-36.1;default;x86_64")

    def test_from_api_37_on_a_levels_folder_has_a_minor_version(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "37"))
        argv = self.created()
        self.assertEqual(value(argv, "--name"), "phone_api37")
        self.assertEqual(value(argv, "--package"), "system-images;android-37.0;default;x86_64")

    def test_an_installed_folder_wins_over_the_usual_form_of_a_level(self):
        install_image(self.sandbox, "36.0")
        install_image(self.sandbox, "38")
        for level, folder in (("36", "36.0"), ("38", "38")):
            with self.subTest(level):
                self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", level))
                self.assertEqual(value(self.created(), "--package"),
                                 f"system-images;android-{folder};default;x86_64")

    def test_the_form_of_a_level_is_looked_up_for_the_images_own_tag(self):
        # Installed for Google APIs only: the plain image of that level keeps the usual form.
        install_image(self.sandbox, "36.0", "google_apis")
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "36"))
        self.assertEqual(value(self.created(), "--package"), "system-images;android-36;default;x86_64")
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", "36"))
        self.assertEqual(value(self.created(), "--package"),
                         "system-images;android-36.0;google_apis;x86_64")

    def test_api_with_a_name(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "28", "pie_phone"))
        [argv] = self.sandbox.argvs("avdmanager")
        self.assertEqual(value(argv, "--name"), "pie_phone")
        self.assertEqual(value(argv, "--package"), "system-images;android-28;default;x86_64")

    def test_name_before_api(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "pie_phone", "--api", "28"))
        [argv] = self.sandbox.argvs("avdmanager")
        self.assertEqual(value(argv, "--name"), "pie_phone")
        self.assertEqual(value(argv, "--package"), "system-images;android-28;default;x86_64")

    def test_api_names_the_avd_after_its_level_even_with_awdt_avd_set(self):
        # AWDT_AVD usually names the everyday AVD; an AVD of another level must not take its name.
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "30", env={"AWDT_AVD": "work_phone"}))
        self.assertTrue((self.sandbox.home / ".android/avd/phone_api30.avd").is_dir())

    def test_google_apis_picks_that_image_and_names_the_avd_gapi(self):
        for level in ("30", "36"):
            with self.subTest(level):
                result = self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", level)
                self.assertSucceeded(result)
                argv = self.created()
                for flag, expected in {"--name": f"phone_gapi{level}", "--tag": "google_apis",
                                       "--abi": "x86_64",
                                       "--package": f"system-images;android-{level};google_apis;x86_64"}.items():
                    self.assertEqual(value(argv, flag), expected, flag)
                self.assertIn(("tag.id", "google_apis"), self.config(f"phone_gapi{level}"))
                self.assertIn(f"mobile-start-emulator.sh phone_gapi{level}", result.out)

    def test_google_apis_of_the_default_level(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--google-apis"))
        self.assertEqual(value(self.created(), "--name"), "phone_gapi36")

    def test_google_apis_on_api_27_is_x86(self):
        # The one image Google publishes for x86 only; the plain image of that level isn't.
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", "27"))
        argv = self.created()
        self.assertEqual(value(argv, "--abi"), "x86")
        self.assertEqual(value(argv, "--package"), "system-images;android-27;google_apis;x86")
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "27"))
        self.assertEqual(value(self.created(), "--abi"), "x86_64")

    def test_google_apis_with_a_name_in_any_order(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "work_phone", "--api", "33", "--google-apis"))
        [argv] = self.sandbox.argvs("avdmanager")
        self.assertEqual(value(argv, "--name"), "work_phone")
        self.assertEqual(value(argv, "--package"), "system-images;android-33;google_apis;x86_64")

    def test_google_apis_names_the_avd_after_its_level_even_with_awdt_avd_set(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", "34",
                                              env={"AWDT_AVD": "work_phone"}))
        self.assertTrue((self.sandbox.home / ".android/avd/phone_gapi34.avd").is_dir())

    def test_tablet_uses_the_tablet_profile_and_name(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--tablet", "--api", "34"))
        argv = self.created()
        self.assertEqual(value(argv, "--device"), "medium_tablet")
        self.assertEqual(value(argv, "--name"), "tablet_api34")

    def test_tablet_of_the_default_level(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--tablet"))
        self.assertEqual(value(self.created(), "--name"), "tablet_api36")

    def test_tablet_with_google_apis(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--tablet", "--google-apis", "--api", "34"))
        argv = self.created()
        self.assertEqual(value(argv, "--name"), "tablet_gapi34")
        self.assertEqual(value(argv, "--tag"), "google_apis")

    def test_device_names_the_profile_and_the_avd(self):
        result = self.sandbox.run("mobile-create-avd.sh", "--device", "pixel_9_pro_fold", "--api", "36")
        self.assertSucceeded(result)
        argv = self.created()
        self.assertEqual(value(argv, "--device"), "pixel_9_pro_fold")
        self.assertEqual(value(argv, "--name"), "pixel_9_pro_fold_api36")

    def test_device_with_google_apis(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--device", "pixel_8"))
        self.assertEqual(value(self.created(), "--name"), "pixel_8_gapi36")

    def test_awdt_avd_names_a_tablet_or_a_profile_too_without_api(self):
        for flags in (["--tablet"], ["--device", "pixel_8"]):
            with self.subTest(flags):
                name = "avd_of_" + flags[-1].strip("-")
                self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", *flags, env={"AWDT_AVD": name}))
                self.assertEqual(value(self.created(), "--name"), name)

    def test_keeps_the_screen_of_the_profile_by_default(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh"))
        config = self.config("phone_api36")
        for setting in (("hw.lcd.width", "1080"), ("hw.lcd.height", "2400"), ("hw.lcd.density", "420")):
            self.assertIn(setting, config)

    def test_size_and_density_replace_the_profiles_screen(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--size", "720x1280", "--density", "320",
                                              "small_phone"))
        config = self.config("small_phone")
        keys = [key for key, _ in config]
        for key, expected in {"hw.lcd.width": "720", "hw.lcd.height": "1280",
                              "hw.lcd.density": "320"}.items():
            with self.subTest(key):
                self.assertIn((key, expected), config)
                self.assertEqual(keys.count(key), 1, "a setting must replace, not duplicate, a key")

    def test_a_landscape_size_is_fine(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--size", "2560x1600", "wide"))
        self.assertIn(("hw.lcd.width", "2560"), self.config("wide"))

    def test_size_and_density_each_on_their_own(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--size", "1440x3120", "big_phone"))
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--density", "560", "dense_phone"))
        config = self.config("big_phone")
        self.assertIn(("hw.lcd.width", "1440"), config)
        self.assertIn(("hw.lcd.density", "420"), config, "the profile's density is kept")
        config = self.config("dense_phone")
        self.assertIn(("hw.lcd.density", "560"), config)
        self.assertIn(("hw.lcd.width", "1080"), config, "the profile's size is kept")

    def test_size_and_density_with_the_other_options_in_any_order(self):
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--density", "213", "--google-apis",
                                              "small_gapi", "--size", "1280x720", "--api", "36"))
        [argv] = self.sandbox.argvs("avdmanager")
        self.assertEqual(value(argv, "--package"), "system-images;android-36;google_apis;x86_64")
        config = self.config("small_gapi")
        self.assertIn(("hw.lcd.height", "720"), config)
        self.assertIn(("hw.lcd.density", "213"), config)

    def test_patches_the_avd_in_a_custom_avd_home(self):
        home = self.sandbox.root / "avds"
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", env={"ANDROID_AVD_HOME": str(home)}))
        self.assertIn(("hw.keyboard", "yes"), read_config(home / "phone_api36.avd"))
        self.assertFalse((self.sandbox.home / ".android").exists(), "nothing written to ~/.android")

    def test_creates_the_avd_where_the_emulator_looks_when_avdmanager_prefers_xdg(self):
        self.sandbox.set_behavior(avdmanager_xdg=True)
        xdg = self.sandbox.home / ".config"
        result = self.sandbox.run("mobile-create-avd.sh", env={"XDG_CONFIG_HOME": str(xdg)})
        self.assertSucceeded(result)
        self.assertIn(("hw.keyboard", "yes"), self.config("phone_api36"))
        self.assertFalse((xdg / ".android").exists(), "nothing written to $XDG_CONFIG_HOME")
        self.assertSucceeded(self.sandbox.run("mobile-start-emulator.sh"))

    def test_creates_a_missing_custom_avd_home_when_avdmanager_prefers_xdg(self):
        self.sandbox.set_behavior(avdmanager_xdg=True)
        home = self.sandbox.root / "avds"
        self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", env={
            "XDG_CONFIG_HOME": str(self.sandbox.home / ".config"), "ANDROID_AVD_HOME": str(home)}))
        self.assertIn(("hw.keyboard", "yes"), read_config(home / "phone_api36.avd"))


class RefusesOrExplains(ScriptTestCase):
    def test_never_overwrites_an_existing_avd(self):
        self.sandbox.install_sdk()
        folder = self.sandbox.add_avd("phone_api36", image=API36_IMAGE)
        before = (folder / "config.ini").read_text()
        result = self.sandbox.run("mobile-create-avd.sh")
        self.assertFailed(result, "already exists", code=1)
        self.assertIn("avdmanager delete avd -n phone_api36", result.err)
        self.assertIn("--if-missing", result.err)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [], "avdmanager must not be called")
        self.assertEqual((folder / "config.ini").read_text(), before)

    def test_explains_when_it_cannot_find_what_avdmanager_created(self):
        self.sandbox.install_sdk()
        self.sandbox.set_behavior(avd_home=str(self.sandbox.root / "somewhere-unexpected"))
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh"), "ANDROID_AVD_HOME")

    def test_stops_when_avdmanager_fails(self):
        self.sandbox.install_sdk()
        self.sandbox.set_behavior(avdmanager_error="Error: Package path is not valid.")
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh"), "Package path is not valid")

    def test_names_the_missing_package(self):
        self.sandbox.install_sdk(tools=["adb", "emulator"])
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh"),
                          'android sdk install --no-metrics "cmdline-tools;latest"')

    def test_needs_the_emulator_package_too(self):
        self.sandbox.install_sdk(tools=["adb", "avdmanager"])
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh"),
                          'android sdk install --no-metrics "emulator"')

    def test_without_any_sdk(self):
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh"), "no Android SDK found")

    def test_api_must_be_a_level_and_one_name_at_most(self):
        for args in (["--api"], ["--api", "pie"], ["--api", "-1"], ["--api", "36."], ["--api", "36.1.2"],
                     ["one_phone", "two_phone"]):
            with self.subTest(args):
                self.assertFailed(self.sandbox.run("mobile-create-avd.sh", *args), "Usage:", code=2)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def test_a_device_profile_must_be_one_word(self):
        for args in (["--device"], ["--device", "my phone"], ["--device", "a;b"], ["--device", ""]):
            with self.subTest(args):
                self.assertFailed(self.sandbox.run("mobile-create-avd.sh", *args), "Usage:", code=2)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def test_explains_a_missing_system_image(self):
        self.sandbox.install_sdk()
        self.sandbox.set_behavior(avdmanager_error="Error: Package path is not valid. Valid system image paths are:")
        result = self.sandbox.run("mobile-create-avd.sh", "--api", "30")
        self.assertFailed(result, 'android sdk install --no-metrics "system-images;android-30;default;x86_64"')

    def test_explains_a_missing_google_apis_image(self):
        self.sandbox.install_sdk()
        self.sandbox.set_behavior(avdmanager_error="Error: Package path is not valid. Valid system image paths are:")
        result = self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", "31")
        self.assertFailed(result, 'android sdk install --no-metrics "system-images;android-31;google_apis;x86_64"')

    def test_the_install_hint_names_the_image_as_it_is_published(self):
        self.sandbox.install_sdk()
        self.sandbox.set_behavior(avdmanager_error="Error: Package path is not valid.")
        for args, image in ((["--google-apis", "--api", "27"], "system-images;android-27;google_apis;x86"),
                            (["--api", "37"], "system-images;android-37.0;default;x86_64")):
            with self.subTest(args):
                self.assertFailed(self.sandbox.run("mobile-create-avd.sh", *args),
                                  f'android sdk install --no-metrics "{image}"')

    def test_points_to_the_profiles_when_the_image_is_there(self):
        # avdmanager failed for another reason than the image, most likely an unknown --device.
        self.sandbox.install_sdk()
        install_image(self.sandbox, "36")
        self.sandbox.set_behavior(avdmanager_error="Error: No device found matching --device nope.")
        result = self.sandbox.run("mobile-create-avd.sh", "--device", "nope")
        self.assertFailed(result, "A device profile must be one of: avdmanager list device -c")
        self.assertNotIn("android sdk install", result.output)

    def test_size_and_density_must_be_positive_numbers(self):
        for args in (["--size"], ["--size", "1280"], ["--size", "1280x"], ["--size", "1280*720"],
                     ["--size", "0x720"], ["--size", "1280x720p"], ["--density"], ["--density", "hdpi"],
                     ["--density", "0"], ["--density", "-213"]):
            with self.subTest(args):
                self.assertFailed(self.sandbox.run("mobile-create-avd.sh", *args), "Usage:", code=2)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def test_unknown_option_prints_usage(self):
        result = self.sandbox.run("mobile-create-avd.sh", "--force")
        self.assertFailed(result, "Usage:", code=2)


class IfMissing(ScriptTestCase):
    """--if-missing: succeed on an AVD that already exists from the same image, so a script or
    CI job (with the AVD cached) can run mobile-create-avd.sh every time."""

    def setUp(self):
        super().setUp()
        self.sandbox.install_sdk()

    def test_creates_a_missing_avd(self):
        result = self.sandbox.run("mobile-create-avd.sh", "--if-missing")
        self.assertSucceeded(result)
        self.assertIn(("hw.keyboard", "yes"), read_config(self.sandbox.home / ".android/avd/phone_api36.avd"))

    def test_accepts_an_existing_avd_of_the_same_image_and_leaves_it_alone(self):
        folder = self.sandbox.add_avd("phone_api36", image=API36_IMAGE)
        before = (folder / "config.ini").read_text()
        result = self.sandbox.run("mobile-create-avd.sh", "--if-missing")
        self.assertSucceeded(result)
        self.assertIn("already exists", result.out)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [], "avdmanager must not be called")
        self.assertEqual((folder / "config.ini").read_text(), before)

    def test_running_it_twice(self):
        # The second run finds the AVD the first one created, as avdmanager wrote it.
        for _ in range(2):
            self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--api", "30", "--if-missing"))
        self.assertEqual(len(self.sandbox.argvs("avdmanager")), 1)

    def test_running_it_twice_for_a_level_with_a_minor_version_or_x86(self):
        for args in (["--api", "37"], ["--api", "36.1"], ["--google-apis", "--api", "27"]):
            with self.subTest(args):
                before = len(self.sandbox.argvs("avdmanager"))
                for _ in range(2):
                    self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", *args, "--if-missing"))
                self.assertEqual(len(self.sandbox.argvs("avdmanager")), before + 1)

    def test_with_a_name_and_api_in_any_order(self):
        self.sandbox.add_avd("pie_phone", image="system-images/android-28/default/x86_64/")
        for args in (["--if-missing", "--api", "28", "pie_phone"], ["pie_phone", "--api", "28", "--if-missing"]):
            with self.subTest(args):
                self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", *args))
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def test_refuses_an_existing_avd_of_another_image(self):
        folder = self.sandbox.add_avd("phone_api36", image="system-images/android-28/default/x86_64/")
        before = (folder / "config.ini").read_text()
        result = self.sandbox.run("mobile-create-avd.sh", "--if-missing")
        self.assertFailed(result, "system-images/android-28/default/x86_64, not "
                                  "system-images/android-36/default/x86_64", code=1)
        self.assertIn("avdmanager delete avd -n phone_api36", result.err)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])
        self.assertEqual((folder / "config.ini").read_text(), before)

    def test_tells_the_google_apis_and_plain_images_of_a_level_apart(self):
        self.sandbox.add_avd("phone_gapi30", image="system-images/android-30/default/x86_64/")
        result = self.sandbox.run("mobile-create-avd.sh", "--google-apis", "--api", "30", "--if-missing")
        self.assertFailed(result, "system-images/android-30/default/x86_64, not "
                                  "system-images/android-30/google_apis/x86_64", code=1)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def add_small_avd(self):
        # As the emulator rewrites config.ini: "key = value".
        folder = self.sandbox.add_avd("small_phone", image=API36_IMAGE)
        with (folder / "config.ini").open("a") as config:
            config.write("hw.lcd.width = 720\nhw.lcd.height = 1280\nhw.lcd.density = 320\n")
        return folder

    def test_accepts_an_existing_avd_with_the_size_and_density_given(self):
        self.add_small_avd()
        for args in ([], ["--size", "720x1280"], ["--density", "320"], ["--size", "720x1280", "--density", "320"]):
            with self.subTest(args):
                self.assertSucceeded(self.sandbox.run("mobile-create-avd.sh", "--if-missing", "small_phone", *args))
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])

    def test_refuses_an_existing_avd_with_another_size_or_density(self):
        folder = self.add_small_avd()
        before = (folder / "config.ini").read_text()
        for args, message in ((["--size", "1080x1280"], "hw.lcd.width is 720, not\n1080"),
                              (["--size", "720x1600"], "hw.lcd.height is 1280, not\n1600"),
                              (["--density", "420"], "hw.lcd.density is 320, not\n420")):
            with self.subTest(args):
                result = self.sandbox.run("mobile-create-avd.sh", "--if-missing", "small_phone", *args)
                self.assertFailed(result, message, code=1)
                self.assertIn("avdmanager delete avd -n small_phone", result.err)
        self.assertEqual(self.sandbox.argvs("avdmanager"), [])
        self.assertEqual((folder / "config.ini").read_text(), before)

    def test_refuses_an_existing_avd_with_no_screen_setting_when_one_is_given(self):
        self.sandbox.add_avd("phone_api36", image=API36_IMAGE)
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh", "--if-missing", "--density", "320"),
                          "hw.lcd.density is not set", code=1)

    def test_refuses_an_existing_avd_whose_image_it_cannot_tell(self):
        self.sandbox.add_avd("phone_api36")
        self.assertFailed(self.sandbox.run("mobile-create-avd.sh", "--if-missing"), "an unknown system image")
