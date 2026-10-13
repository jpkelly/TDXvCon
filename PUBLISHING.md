# Publishing TDXvCon

The primary deliverable is `src/vcon/data/transcoder.toe`, opened directly in
TouchDesigner. Complete steps 1–3, test the panel from a clean copy, and attach
the saved project to the GitHub release. Video encoding does not require the
CLI; audio support is installed separately through Setup & Help.

Steps 4–7 publish the optional `tdxvcon` Python package to PyPI. Build it only
after saving the project, which bakes in the version and file-linked DAT text.

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

In the TD **textport**:

```python
exec(op.vcon.op('panel_build_run').text)
```

> Do **not** right-click the `panel_build_run` DAT and choose "Run Script" —
> the build sweeps and destroys that DAT while it is executing. The textport
> form reads `.text` into a string first, so it is safe.

## 3. Save the `.toe` into the package

`File → Save As…` in TD, destination:

```
<checkout>/src/vcon/data/transcoder.toe
```

Saving bakes the current text of every file-linked DAT into the `.toe`.
Editing the `.py` files alone is **not** enough to ship.

Confirm the packaged toe is newer than every source it bakes in:

```bash
ls -lt src/vcon/data/transcoder.toe toe/*.py | head -5
```

`src/vcon/data/transcoder.toe` must be at the top.

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
