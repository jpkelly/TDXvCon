# vCon

**GPU video transcoding, FFmpeg-style, powered by TouchDesigner.**

`vcon` is a cross-platform (macOS / Windows) command-line transcoder that
drives [TouchDesigner](https://derivative.ca/)'s GPU-accelerated
`Movie File Out TOP` to encode video into **every codec TouchDesigner
supports** — NotchLC, Hap, Apple ProRes, GoPro CineForm, H.264/H.265/AV1,
and more.

> **Naming:** the package installs as **`tdxvcon`** but the command is
> **`vcon`**. (The PyPI name `vcon` was already taken by an unrelated
> project.)

## Why

The NotchLC encoder is not available in FFmpeg or any open encoder — it lives
in TouchDesigner (and other licensed products). vCon wraps TouchDesigner in a
headless, self-driving pipeline and exposes it through a familiar CLI, so
converting footage becomes:

```bash
vcon -i input.mov -c notchlc out.mov
```

## Install

**Requirements:** TouchDesigner (macOS or Windows) and Python 3.10+.

```bash
pipx install tdxvcon
```

`pipx` creates an isolated environment automatically and puts `vcon` on your
PATH — **no virtualenv to create or activate, ever**. It is also the least
friction option on both macOS and Windows, and avoids app-store packaging
entirely.

Then verify:

```bash
vcon -doctor
```

You should see ✔ for the TouchDesigner binary, the transcoder toe, the toe's
freshness, and the controller probe. If no controller is running, `vcon`
launches TouchDesigner for you.

### If you don't have pipx

```bash
# macOS
brew install pipx && pipx ensurepath

# Windows (PowerShell)
py -m pip install --user pipx
py -m pipx ensurepath

# any platform, if pip is available
python3 -m pip install --user pipx && python3 -m pipx ensurepath
```

`pipx ensurepath` is the one step people miss — it adds `~/.local/bin`
(macOS/Linux) or `%USERPROFILE%\.local\bin` (Windows) to PATH so the `vcon`
command is found. Open a new terminal afterwards.

> **Windows note:** TouchDesigner must be added to the firewall allow-list, or
> the controller's TCP port will be blocked.

TouchDesigner binary resolution order: `-td-path` flag → `VCON_TDPATH`
environment variable → config file → standard install locations
(`/Applications/TouchDesigner.app/...` on macOS,
`C:\Program Files\Derivative\TouchDesigner\bin\...` on Windows).

## Usage

A codec is **required** for every output — like ffmpeg's `-c:v`, but with no
sensible default (NotchLC and H.264 are for opposite ends of a pipeline).

```bash
# NotchLC — GPU mezzanine (the usual choice)
vcon -i input.mov -c notchlc -q optimal output.mov

# ProRes 4444 XQ — for an edit suite
vcon -i input.mov -c prores -t 4444xq output.mov

# Hap Q — for a media server
vcon -i input.mov -c hap -t hapq output.mov

# H.264 delivery file
vcon -i input.mov -c h264 output.mp4

# Multiple outputs in one TouchDesigner pass
vcon -i input.mov -c notchlc a.nlc.mov -c hap -t hapq b.hapq.mov

# Force overwrite, quiet output
vcon -y -loglevel error -i input.mov -c notchlc output.mov
```

Run `vcon -h` for the full option list and the recommended codecs with their
subtypes. Run `vcon -codecs` for **every** codec TouchDesigner can encode
(including legacy ones), with quality levels, pixel formats and speed notes.

Both the help and the codec list are generated from
[`src/vcon/codec_meta.py`](src/vcon/codec_meta.py) at runtime, so they can
never drift out of sync with what actually works.

### Flags

```
-i  FILE        input file
-c  CODEC       codec — REQUIRED (see vcon -codecs)
-t  SUBTYPE     codec variant (prores: 422proxy, 422lt, 422, 422hq, 4444, 4444xq;
                hap: hap, hapq, hapr, haphdr)
-q  QUALITY     quality level (notchlc: good, very-good, excellent, optimal, best)
-f  FPS         override output frame rate
-no-alpha       force alpha off even if the source has it
-y / -n         allow / forbid overwriting existing files
-loglevel LVL   quiet | error | warning | info | debug
-nostats        disable the ffmpeg-style progress line
-codecs         list every available codec
-doctor         diagnose the TouchDesigner setup
```

### Notes

- **Subtypes and pixel formats vary by codec.** Alpha is only available where
  a format carries it — ProRes needs `-t 4444` or `4444xq`; Hap HDR has none.
  vcon tells you when a combination isn't possible rather than silently
  producing something different.
- **Outputs are much larger than the source.** NotchLC and ProRes are
  mezzanine codecs (~5:1 against *raw*, not against H.264). A 26 GB H.264
  source can become a 45 GB NotchLC or ProRes file. Check free space first.
- **vcon verifies every output.** It reads the codec back out of the finished
  file and fails the job if TouchDesigner produced something else — the
  failure mode that motivated this check was a "successful" encode that was
  silently in the wrong codec.

## Architecture

```
CLI (renderer)  ──subscribes──▶  vcon.core (headless, event-emitting)
                                        │  QueueManager · CodecRegistry · Driver
                                        ▼
                                 Driver backend (mock | touchdesigner)
                                        │ spawn + TCP JSON-lines
                                        ▼
                                 transcoder.toe (TouchDesigner, GPU encode)
```

- The core is an importable library that emits typed events and never prints —
  a future GUI or daemon is a new subscriber, not a refactor.
- The TouchDesigner project ships inside the pip package; users never open the
  TD editor.
- A `--mock` driver runs the entire pipeline without TouchDesigner (used by the
  test suite and useful for development on machines without TD).

## Development

Working on vcon itself (not just using it):

```bash
git clone … && cd vCon
python3 -m venv .venv && .venv/bin/pip install -e . pytest
.venv/bin/python -m pytest          # 134 tests, no TouchDesigner needed
```

### Rebuilding the toe

You only rebuild `transcoder.toe` when `toe/vcon_controller.py` changes. See
[toe/PROTOCOL.md](toe/PROTOCOL.md) for the wire contract it must satisfy.

```python
# Run in TouchDesigner's TEXTPORT — NOT the Python console, and never `import`
# (TD does not inject its builtins like `op` into imported modules).
exec(open('/path/to/vCon/toe/build_network.py', encoding='utf-8').read())
```

### Using a global install while developing

If `vcon` is installed with pipx but you are rebuilding the toe, the installed
command would otherwise use a *stale packaged copy*. Point it at your repo:

```bash
export VCON_TOE=/path/to/vCon/src/vcon/data/transcoder.toe
```

Or re-sync the packaged copy after a rebuild:

```bash
./scripts/sync-toe.sh      # copies toe → installed package + refreshes pipx
```

## Status

Phase 1 — core skeleton, protocol, queue, codec registry, mock driver,
FFmpeg-style CLI, and tests. TouchDesigner integration lands in phase 2+.