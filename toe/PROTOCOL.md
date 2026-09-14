# transcoder.toe — controller contract (v1)

This document pins the wire behavior `toe/vcon_controller.py` must satisfy.
The phase-1 fake controller (`tests/test_td_driver.py`) enforces the same
shape, so any drift between toe and tests shows up as a test failure.

## Transport

- TCP, `127.0.0.1:7999` (front-end connects; toe listens)
- UTF-8 JSON, one message per line, terminated by `\n`
- Max line: 1 MiB; max clients: 1

## Handshake

On startup, once the TCPIP DAT is listening and the controller extension is
loaded, the toe sends:

```json
{"type": "hello", "version": 1}
```

The front-end will not send jobs until it receives this. If the toe cannot
reach "ready" it should quit (non-zero) so the driver's process check fails
fast rather than timing out on connect.

## Messages — front-end → toe

### submit

```json
{"type": "submit", "id": "j1", "input": "/abs/in.mov",
 "output": "/abs/out.nlc.mov",
 "params": {"videocodec": "NotchLC", "moviepixelformat": "...",
            "moviecontainer": ".mov", "quality": "optimal", "fps": "auto"}}
```

- `id` is opaque to the toe; echo it in every reply for this job.
- `params` values are pre-resolved by the front-end codec registry — the
  toe applies them directly to Movie File Out's parameters without
  interpreting them.
- Exactly **one job at a time**: the toe replies `error/busy` if a submit
  arrives while encoding.
- Unknown `params` keys are ignored (forward compatibility).

### cancel

```json
{"type": "cancel", "id": "j1"}
```

Abort the named job (if running), discard the partial output file, reply
with `error/cancelled`.

### ping

`{"type": "ping"}` → `{"type": "pong"}` — used by `--doctor`.

## Messages — toe → front-end

| type | when | fields |
|---|---|---|
| `hello` | startup, once | `version: 1` |
| `accepted` | input loaded, encoding starting | `id`, `total_frames` |
| `progress` | every ≤10 frames and at completion of frame count | `id`, `frame`, `total_frames` |
| `done` | file finalized on disk | `id`, `path`, `total_frames`, `seconds` |
| `error` | any failure (input missing, busy, cancelled, encode error) | `id`, `message`, `code` |

Error `code` values (stable): `protocol`, `busy`, `input-missing`,
`input-error`, `output-error`, `cancelled`, `encode-error`.

## Encoding requirements

- **Frame accuracy is the contract.** `progress.frame` counts *written*
  frames (Movie File Out Info CHOP `total_frames_written`), not seeks.
- Frame-stepped, non-realtime: Movie File In `playmode = Specify Index`,
  stepping `index`; Movie File Out `pause = 1` + `addframe` pulse per frame.
- The toe **must** verify the first frame is loaded
  (`alwaysloadinitial = 1`) before `accepted`, so frame 0 is never black.
- `done` fires only after the file is closed (`record` pulse finalize) and
  exists on disk.
- After `done`, the toe stays alive — the front-end terminates the process.
  Idle self-quit after 300 s is a backstop only.

## Open verification items (phase 3, on JP's TD install)

1. `-perform` command-line flag spelling on current TD builds (mac + win).
2. `playmode = "index"` menu literal (docs say 'Specify Index'; the par
   assignment literal needs checking in the textport).
3. `addframe` pulse semantics while `pause = 1` (stop-frame movie mode).
4. `record` 1→0 pulse to finalize a stop-frame movie (vs. `closefile`).
5. TCPIP DAT `sendText(..., force=True)` for line-delimited JSON.
6. Whether `movieout.par.fps` accepts the input movie's `sample_rate`
   (Info CHOP) directly.
7. Info CHOP `length` channel name vs `true_length` when Trim is unused
   (should match; confirm).