# Contributing

For bug reports, include the vCon version, OS, TouchDesigner build,
`vcon -doctor` output, command or panel steps, and the observed error. Remove
private media paths and credentials from logs. Use a small redistributable
sample when reproduction requires media.

Install the project in a virtual environment with `python -m pip install -e . pytest`.
Run `python -m pytest` before submitting a pull request. Core tests do not
require TouchDesigner; describe any manual encoding checks separately.

## Source layout

- `src/vcon/`: CLI, job queue, codec registry, drivers, and packaged project.
- `toe/`: TouchDesigner controller, panel builders, captures, and diagnostic scripts.
- `tests/`: core tests and simulated controller integration tests.

## Rebuilding the TouchDesigner project

The current authoring scripts contain maintainer-specific repository paths;
`build_panel.py` also uses macOS palette paths. They are not yet a portable
build system. Update their path constants for your checkout and TouchDesigner
installation before running them. Users opening the saved project or running
the installed CLI do not need these scripts.

Run builders in TouchDesigner's **Textport**, using `exec` rather than importing
modules (TouchDesigner injects operator globals into the Textport namespace):

```python
exec(open('/path/to/TDXvCon/toe/build_network.py', encoding='utf-8').read())
exec(open('/path/to/TDXvCon/toe/build_panel.py', encoding='utf-8').read())
```

Builders replace network components and save the project. Work in a development
copy and retain any unsaved edits before rebuilding. The panel build reads
`panel_layout_captured.py`; `panel_layout_variant.py` records SCALE-OFF deltas
used when maintaining the runtime row layouts.

Changes to controller or panel source must be baked into
`src/vcon/data/transcoder.toe` before release. Test the saved project without
access to the author's source paths: linked DATs must retain usable embedded
source. Check a representative encode, output codec, frame count, audio, and
panel interactions on each supported platform.

Keep local settings, cache files, media, and TouchDesigner backups out of commits.
See [PUBLISHING.md](PUBLISHING.md) for the release procedure.
