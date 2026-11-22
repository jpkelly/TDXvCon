# Publishing TDXvCon

The primary deliverable is `src/vcon/data/transcoder.toe`, opened directly in
TouchDesigner. Complete steps 1–3, test the panel from a clean copy, and attach
the shipped project to the GitHub release.

Development happens in a separate local project, `dev/TDXvCon-dev.toe`. It is
gitignored and is never committed or shipped, because it keeps `/TDMCP`, the
TouchDesigner MCP server (port 13315) that lets an AI assistant drive the open
project. The shipped toe is always made from the dev toe by
`scripts/release_toe.py`, which removes `/TDMCP`. Never save the dev project
over `transcoder.toe`. Video encoding does not require the
CLI; audio support is installed separately through Setup & Help.

Steps 4–7 publish the optional `tdxvcon` Python package to PyPI. Build it only
after saving the project, which bakes in the version and file-linked DAT text.

The first major release uses Git tag `v1.0.0`, package/controller version `1.0.0`,
and release asset name `TDXvCon-1.0.0.toe`.

## 1. Bump the version (3 files, must match)

| File | Line |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `src/vcon/__init__.py` | `__version__ = "X.Y.Z"` |
| `toe/vcon_controller.py` | `CONTROLLER_VERSION = "X.Y.Z"` |

Verify:

```bash
grep -h -E 'version = "|__version__ = "|CONTROLLER_VERSION = "' \
  pyproject.toml src/vcon/__init__.py toe/vcon_controller.py
```

## 2. Rebuild the panel in TouchDesigner

Open `dev/TDXvCon-dev.toe` in the current TouchDesigner release, not a beta
build: the shipped toe keeps the build that saved it. In the TD **textport**:

```python
exec(op.vcon.op('panel_build_run').text)
```

> Do **not** right-click the `panel_build_run` DAT and choose "Run Script" —
> the build sweeps and destroys that DAT while it is executing. The textport
> form reads `.text` into a string first, so it is safe.

## 3. Make the shipped `.toe` from the dev toe

The panel build saves `dev/TDXvCon-dev.toe`. Saving bakes the current text of
every file-linked DAT into the `.toe`; editing the `.py` files alone is
**not** enough to ship. Before that save, verify that the read-only
**vCon version** parameter and **? → Setup & Help → Versions** both report
the intended controller version (the custom parameter should use the
expression `me.op('vcon_controller').module.CONTROLLER_VERSION`). Clear the
panel queue and undo any test settings too: the shipped toe inherits the dev
toe's saved state.

Then, with TouchDesigner's `toeexpand` and `toecollapse` (no TD window needed):

```bash
python scripts/release_toe.py
VCON_RELEASE_CHECK=1 python -m pytest tests/test_toe_manifest.py
```

Pulse the `tcpip` DAT's **Clear** parameter before that save: it keeps the
protocol messages it received, and saving bakes their job paths into the
toe. `release_toe.py` refuses a toe that still holds them. It also refuses
when TouchDesigner's incremental save has written a newer
`TDXvCon-dev.N.toe` beside the dev toe: pass that file with `--dev`, or save
over `TDXvCon-dev.toe`.

`release_toe.py` copies the dev toe without `/TDMCP` to
`src/vcon/data/transcoder.toe`, checks that the copy kept every other
operator and the same controller and panel text, and records what it contains
in `transcoder.toe.sources.json`. The release check confirms that the toe
holds the current source (file dates cannot show this: a git checkout
scrambles them) and no `/TDMCP`.

Open the shipped toe once to confirm it works without the dev server: run a
short encode with `vcon`, which launches TouchDesigner with it. Don't save
the dev project over it.

Commit `src/vcon/data/transcoder.toe` and `transcoder.toe.sources.json`
together. CI repeats this check on every tag push.

## 4. Build

Run the packaging tools in isolated environments with pipx. Remove old release
artifacts from `dist/` first so they cannot be uploaded accidentally.

```bash
pipx run build
pipx run twine check dist/*
```

Success looks like: `Successfully built tdxvcon-X.Y.Z.tar.gz and
tdxvcon-X.Y.Z-py3-none-any.whl`.

## 5. Verify the toe inside the wheel

The most common shipping mistake is a stale `.toe` under a fresh version
number. These two hashes must be identical:

```bash
unzip -p dist/tdxvcon-*-py3-none-any.whl vcon/data/transcoder.toe | shasum -a 256
shasum -a 256 src/vcon/data/transcoder.toe
```

## 6. Upload

```bash
pipx run twine upload dist/*
```

Uses your PyPI API token. If it is not in `~/.pypirc`, twine prompts —
type the token directly into the terminal.

## 7. Install and confirm

```bash
pipx install --force --pip-args="--no-cache-dir" tdxvcon
vcon --version
```

If the version still looks stale, confirm the release is visible in the package
index:

```bash
curl -s https://pypi.org/simple/tdxvcon/ | grep -o 'tdxvcon-[0-9.]*\.whl' | tail -3
```

## Gotchas

- **The `.toe` bakes in DAT text at save time.** Rebuild the toe *after*
  the last source edit and *before* building the wheel.
- **Ship only what `release_toe.py` writes.** A toe saved from TouchDesigner
  into `src/vcon/data/` would ship the `/TDMCP` server; the release check
  fails on it.
- **Bump `CONTROLLER_VERSION` before saving the toe** — that version is
  baked in, and the CLI refuses to drive a controller whose version does
  not match (`src/vcon/__main__.py`).
- **The panel runs directly in TouchDesigner.** The CLI package is optional.
  FFmpeg is required for audio muxing/export and is not bundled in the `.toe`;
  users can install it through the panel's Setup & Help dialog.
- **Panel layout** lives in `toe/panel_layout_captured.py` (canonical,
  SCALE ON) and `toe/panel_layout_variant.py` (SCALE OFF row deltas).
  Capture before rebuilding and synchronize the runtime `_ROW_LAYOUTS` in
  `toe/vcon_panel_callbacks.py` with the captured arrangements.

## Before making the repository public

- Run `python -m pytest` and review the package contents.
- Review all published branches and tags for credentials and private material.
  Removing a tracked file does not remove its previous versions from Git history.
- Review the binary `.toe` projects in TouchDesigner for embedded media, paths,
  linked DATs, and third-party assets. Text-based secret scans cannot fully inspect
  compressed project contents. Confirm redistribution rights for bundled assets.
- Test the packaged project on a clean machine without the maintainer's checkout.
  The current authoring scripts still use local paths; see [CONTRIBUTING.md](CONTRIBUTING.md).
- Confirm the intended GitHub visibility separately from publishing to PyPI.
