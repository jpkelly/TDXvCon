# TDXvCon

GPU video transcoding through TouchDesigner's Movie File Out TOP, with an
FFmpeg-style CLI and a TouchDesigner queue panel. Supports NotchLC, Hap,
ProRes, CineForm, and other codecs exposed by the controller's codec registry.

The Python package is `tdxvcon`; the command and import name are `vcon`.

## Requirements and installation

- Python 3.10+ and [pipx](https://pipx.pypa.io/stable/installation/).
- TouchDesigner installed and licensed for your intended use on macOS or Windows.
  Codec availability and output limits depend on the TouchDesigner build,
  platform, and license. TouchDesigner is installed separately.

```sh
pipx install tdxvcon
vcon -doctor
```

`-doctor` checks the installation and probes an existing controller; it does
not start TouchDesigner. Transcoding attaches to a running controller or
launches the packaged project. Set `VCON_TDPATH` or pass `-td-path PATH` if
TouchDesigner is not detected.

## Usage

Specify a codec for each output. Output options precede the output path.

```sh
# NotchLC
vcon -i input.mov -c notchlc -q optimal output.mov

# ProRes 4444 XQ
vcon -i input.mov -c prores -t 4444xq output.mov

# Hap Q
vcon -i input.mov -c hap -t hapq output.mov

# Multiple outputs (queued sequentially)
vcon -i input.mov -c notchlc out.nlc.mov -c hap -t hapq out.hap.mov

# Overwrite without prompting
vcon -y -i input.mov -c h264 output.mp4
```

Run `vcon -h` for options and `vcon -codecs` for registry entries, subtypes,
quality levels, and pixel formats. Alpha support depends on the codec and
subtype. Allow sufficient disk space for intermediate codecs.

The packaged [TouchDesigner project](src/vcon/data/transcoder.toe) also
provides a queue panel: add or drop files, select output settings and a
destination, then start the batch.

## Architecture and limitations

The CLI submits jobs to an event-driven Python queue. A TouchDesigner driver
communicates with the packaged controller over a TCP JSON-lines protocol;
TouchDesigner performs the video encoding. FFmpeg handles audio post-processing.
See the [protocol reference](toe/PROTOCOL.md).

This is alpha software. The Python tests exercise the core and a simulated
controller; they do not validate GPU encoding or every platform/codec combination.
The controller protocol has no authentication: use it only on a trusted machine
and keep its TCP port (default `7999`) inaccessible to untrusted clients.

## Development

```sh
git clone https://github.com/jpkelly/TDXvCon.git
cd TDXvCon
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -e . pytest
python -m pytest
```

Tests run without TouchDesigner. The `-mock` CLI flag exercises the queue and
progress flow without producing encoded video. Set `VCON_TOE` to a local
project file when testing changes to the controller.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and project rebuilds,
and [PUBLISHING.md](PUBLISHING.md) for releases.

## License

[MIT](LICENSE). TouchDesigner and other third-party components retain their
own licenses.
