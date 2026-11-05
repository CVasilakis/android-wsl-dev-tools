# docs/

The guides: what spans the whole repository rather than one folder. The root
[`README.md`](../README.md) says what these tools are, what they cover and how to start.

## Reading order

Read from the general to the specific; each document builds on the ones before it:

1. **[`SETUP.md`](SETUP.md):** installing the toolchain, and how much disk and memory it takes.
2. **[`../bin/README.md`](../bin/README.md):** the commands, and how they find your setup.
3. **The guides [below](#guides)**, as a task needs them.
4. **Comments in the code:** why a particular line is there.

How the docs are written and kept up to date: [below](#writing-the-docs). Coding agents also read
[`../AGENTS.md`](../AGENTS.md).

## Guides

| File | Contents |
|---|---|
| [`SETUP.md`](SETUP.md) | Installing the JDK, SDK and emulator on WSL2; sizes. |
| [`EMULATORS.md`](EMULATORS.md) | Emulators: creating them, booting and stopping them, what each image does on its own. |
| [`DRIVING.md`](DRIVING.md) | Using a running emulator: touch, keys, text, seeing what's on the screen, sensors, changing the device. |
| [`WSLG.md`](WSLG.md) | The emulator's window under WSLg: its side toolbar, and what doesn't work there. |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | From a symptom or a message to its cause. |
| [`CI.md`](CI.md) | Using the tools in GitHub Actions. |

## The repository

| Path | Contents |
|---|---|
| [`bin/`](../bin/README.md) | The commands, and nothing else: it's what goes on your `PATH`. |
| [`lib/`](../lib/README.md) | What the commands share. |
| [`tests/`](../tests/README.md) | The tests of the commands. |
| [`docs/`](README.md) | These guides. |
| [`AGENTS.md`](../AGENTS.md) | Rules for changing this repository. |
| `.github/workflows/` | The workflows that run the tests: the hermetic tier on every push, the emulator tier by hand ([`tests/README.md`](../tests/README.md)). |

## Writing the docs

These apply to every document in the repository, and to comments that explain code.

- **Each fact in one place.** A fact goes in the one document whose topic it is; everywhere else,
  link to it instead of repeating it.
- **A parent names its children, and doesn't repeat them.** A document that covers a topic in
  general links down to the documents with the details, and each of those can rely on what's above
  it.
- **One topic per document.** A topic too narrow for the document above it gets a document of its
  own, listed above, rather than a long section in a document about something else.
- **Every top-level folder has a `README.md`**, except `.github/`: GitHub shows a
  `.github/README.md` on the repository's front page instead of the root one.
- **The current state, not history.** No changelogs, dates or "we tried X" stories. Why something
  that looks odd is there belongs in a comment, or in [`AGENTS.md`](../AGENTS.md)'s table.
- **No machine-specific measurements.** How long a boot, build, test run or gesture takes depends
  on the host, so describe it relatively ("slower", "faster than a cold boot"). Sizes, RAM needs and
  counts are fine.
- **Paths use `~`**, never an absolute home path, so examples work on any machine.
- **Docs change with the code.** A change to something a document describes updates that document
  in the same change.
