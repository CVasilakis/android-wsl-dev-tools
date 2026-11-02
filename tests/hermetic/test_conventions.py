"""Rules every script in bin/ follows. New scripts are picked up automatically."""
import os
import py_compile
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from emulator import test_on_emulator as tier
from support.sandbox import BIN, LIB, TOOLS

RUNNABLE = sorted(p for p in BIN.iterdir() if p.suffix in (".sh", ".py"))
SHELL = sorted(BIN.glob("*.sh")) + sorted(LIB.glob("*.sh"))
# What the scripts source: everything in lib/ that isn't a script of its own, like the build tool.
LIBRARIES = [p for p in sorted(LIB.glob("*.sh")) if not p.read_text().startswith("#!")]
TIME_IS_UP = '[ "$2" -eq 0 ] || [ $((SECONDS - $1)) -gt "$2" ]'   # the one line that may compare it


def anchors(document):
    """The anchors of a Markdown file's headings, as GitHub makes them."""
    found = set()
    for heading in re.findall(r"^#+ +(.+)$", document.read_text(), re.M):
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "").lower()
        found.add(re.sub(r"[^\w\- ]", "", text).replace(" ", "-"))
    return found


class Conventions(unittest.TestCase):
    def test_runnable_scripts_are_executable_with_a_shebang(self):
        for script in RUNNABLE:
            with self.subTest(script.name):
                self.assertTrue(os.access(script, os.X_OK), "not executable (chmod +x)")
                self.assertTrue(script.read_text().startswith("#!/usr/bin/env "),
                                "must start with #!/usr/bin/env bash|python3")

    def test_every_command_starts_with_mobile(self):
        # So that it can share $PATH with the Android TV tools, whose commands start with tv-.
        for script in RUNNABLE:
            with self.subTest(script.name):
                self.assertTrue(script.name.startswith("mobile-"), "name it mobile-<what it does>")

    def test_only_runnable_scripts_are_in_bin(self):
        # Everything in bin/ becomes a command for users who put it on $PATH.
        for path in BIN.iterdir():
            with self.subTest(path.name):
                self.assertTrue(path in RUNNABLE or path.name == "README.md",
                                "bin/ holds only commands; helpers go in lib/")

    def test_the_libraries_are_not_executable(self):
        self.assertTrue(LIBRARIES)
        for library in LIBRARIES:
            with self.subTest(library.name):
                self.assertFalse(os.access(library, os.X_OK), "sourced, so not executable")

    def test_every_script_has_help(self):
        # --help must work on a machine with nothing installed, so it runs with an empty env.
        # It names the script without a folder: users call it by any path, or through $PATH.
        for script in RUNNABLE:
            for flag in ("--help", "-h"):
                with self.subTest(script.name, flag=flag):
                    result = subprocess.run([str(script), flag], capture_output=True, text=True,
                                            env={"PATH": "/usr/bin:/bin"}, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(result.stdout.startswith("Usage: " + script.name),
                                    f"help must start with 'Usage: {script.name}'")

    def test_every_script_is_described_in_the_readme(self):
        readme = BIN / "README.md"
        if not readme.exists():
            self.skipTest("bin/README.md doesn't exist yet")
        for script in RUNNABLE:
            with self.subTest(script.name):
                self.assertIn(f"[`{script.name}`]({script.name})", readme.read_text())

    def test_time_limits_are_checked_by_time_is_up(self):
        # $SECONDS counts whole seconds, so comparing it with a limit directly can end the limit
        # up to a second early; time_is_up (device.sh) doesn't. Scripts only take start times from
        # it, and may show one in a message.
        for script in SHELL:
            for number, line in enumerate(script.read_text().splitlines(), 1):
                code = line.strip()
                if "SECONDS" in code and not code.startswith(("#", "echo ")):
                    with self.subTest(f"{script.name}:{number}"):
                        if code != TIME_IS_UP:
                            self.assertRegex(code, r"=\$SECONDS( |$)",
                                             "check time limits with time_is_up")

    def test_the_emulator_tier_boots_with_the_developers_emulator_flags(self):
        # Where the default renderer fails, the tier's own boots need another one.
        flags = {"AWDT_TEST_EMULATOR_FLAGS": "-gpu swiftshader_indirect -cores '2'"}
        with mock.patch.object(tier, "start_script") as start_script, mock.patch.dict(os.environ, flags):
            tier.start("phone_api36", "--wait-for-home")
        start_script.assert_called_once_with("phone_api36", "-no-window", "-no-snapshot-save", "-gpu",
                                             "swiftshader_indirect", "-cores", "2",
                                             "--wait-for-home", env=None)

    def test_the_emulator_tier_copies_the_scripts_current_time_limits(self):
  # The tier's limits for mobile-start-emulator.sh and mobile-stop-emulator.sh are built from these values
        # of the scripts. With a value grown in a script only, Python could stop the script
        # halfway and leave its emulator running.
        device, start, stop = (path.read_text() for path in
                               (LIB / "device.sh", BIN / "mobile-start-emulator.sh", BIN / "mobile-stop-emulator.sh"))
        stop_emulator = re.search(r"^stop_emulator\(\) \{\n.*?^\}", start, re.M | re.S)
        scripts = {
            "ADB_TIMEOUT": (device, r'^ADB_TIMEOUT="\$\{AWDT_ADB_TIMEOUT:-(\d+)\}"'),
            "ADB_KILL_AFTER": (device, r'timeout -k (\d+) "\$ADB_TIMEOUT"'),
            "TERM_WAIT": (stop_emulator and stop_emulator.group(0), r'"\$waited" -lt (\d+) \]'),
            "KILL_WAIT": (stop, r"^KILL_WAIT=(\d+)"),
            "STOP_SAVE_WAIT": (stop, r'^SAVE_WAIT="\$\{AWDT_SAVE_WAIT:-(\d+)\}"'),
        }
        for name, (text, pattern) in scripts.items():
            with self.subTest(name):
                found = re.search(pattern, text or "", re.M)
                self.assertIsNotNone(found, f"the scripts no longer match {pattern!r}: "
                                            "update this test and the tier's copy")
                self.assertEqual(getattr(tier, name), int(found.group(1)),
                                 f"tests/emulator/test_on_emulator.py's {name} differs from the "
                                 "script's")

    def test_every_link_in_the_docs_leads_somewhere(self):
        # The docs link instead of repeating (docs/README.md), so a broken link loses a fact.
        documents = [path for path in TOOLS.rglob("*.md")
                     if not {"tmp", ".git"} & set(path.relative_to(TOOLS).parts)]
        self.assertGreater(len(documents), 5)
        for document in documents:
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", document.read_text()):
                if re.match(r"[a-z]+:", target):
                    continue
                path, _, anchor = target.partition("#")
                linked = (document.parent / path).resolve() if path else document
                with self.subTest(f"{document.relative_to(TOOLS)}: {target}"):
                    self.assertTrue(linked.exists(), "no such file")
                    if anchor:
                        self.assertIn(anchor, anchors(linked), "no such heading")

    def test_shell_syntax(self):
        for script in SHELL:
            with self.subTest(script.name):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_python_syntax(self):
        with tempfile.TemporaryDirectory() as out:
            for script in [*BIN.glob("*.py"), *LIB.glob("*.py")]:
                with self.subTest(script.name):
                    py_compile.compile(str(script), cfile=os.path.join(out, "x.pyc"), doraise=True)

    @unittest.skipUnless(shutil.which("shellcheck"),
                         "shellcheck isn't installed (apt install shellcheck / dnf install ShellCheck)")
    def test_shellcheck(self):
        result = subprocess.run(["shellcheck", "-x", "--source-path=SCRIPTDIR", *map(str, SHELL)],
                                capture_output=True, text=True, cwd=TOOLS)
        self.assertEqual(result.returncode, 0, result.stdout)
