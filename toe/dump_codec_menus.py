"""dump_codec_menus.py — one-shot codec menu dump for the vcon registry.

RUN IN TOUCHDESIGNER'S TEXTPORT (with transcoder.toe open):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/dump_codec_menus.py',
              encoding='utf-8').read())

WHY: Movie File Out TOP's `videocodectype` and `quality` menus come back
EMPTY until a codec that owns subtypes is actually selected. So we cannot
learn ProRes/Hap variant names from a default TOP — we must select each codec
in turn and read its live menu.

The registry needs these EXACT tokens. Human-readable labels from the docs
("ProRes 4444 XQ") are NOT what the parameter accepts, and an unrecognised
value silently falls back to menu index 0 — which is how an earlier build
produced valid-looking files in the wrong codec (rle).

Output is a Python dict you can paste straight into vcon/registry.py.
"""


def _mfo():
    # Search the whole tree: the component sits at /project1/vcon, not
    # directly under root, and may be renamed or nested anywhere.
    mfo = None
    for cand in root.findChildren(name="movieout"):
        if cand.parent().op("vcon_controller") is not None:
            mfo = cand
            break
    if mfo is None:
        hits = root.findChildren(name="movieout")
        mfo = hits[0] if hits else None
    if mfo is None:
        raise RuntimeError(
            "could not find a vCon component with a movieout child — open "
            "transcoder.toe first (or run toe/build_network.py)"
        )
    print(f"using {mfo.path}")
    return mfo


def _menus(par):
    try:
        return list(par.menuNames or [])
    except Exception:
        return []


def dump():
    mfo = _mfo()
    original_codec = mfo.par.videocodec.eval()

    print("=" * 70)
    print("vcon codec menu dump")
    print("=" * 70)
    print(f"videocodec menu ({len(_menus(mfo.par.videocodec))} entries):")
    for c in _menus(mfo.par.videocodec):
        print(f"    {c!r}")

    print()
    print(f"moviepixelformat: {_menus(mfo.par.moviepixelformat)}")
    print(f"moviecontainer:   {_menus(mfo.par.moviecontainer)}")
    print()
    print("-" * 70)
    print("PER-CODEC SUBTYPES / QUALITY  (selecting each codec in turn)")
    print("-" * 70)

    results = {}
    for codec in _menus(mfo.par.videocodec):
        try:
            mfo.par.videocodec.val = codec
        except Exception as exc:
            print(f"  {codec:<10} !! could not select: {exc}")
            continue
        subtypes = _menus(mfo.par.videocodectype)
        qualities = _menus(mfo.par.quality)
        pixel_fmts = _menus(mfo.par.moviepixelformat)
        results[codec] = {
            "subtypes": subtypes,
            "qualities": qualities,
            "pixel_formats": pixel_fmts,
        }
        print(f"  {codec:<10} subtypes={subtypes}")
        if qualities:
            print(f"  {'':<10} qualities={qualities}")
        print(f"  {'':<10} pixel_formats={pixel_fmts}")

    # Restore the original selection so the running toe is left as we found it.
    try:
        mfo.par.videocodec.val = original_codec
    except Exception:
        pass

    print()
    print("=" * 70)
    print("PASTE-READY (for vcon/registry.py):")
    print("=" * 70)
    for codec, info in results.items():
        if not info["subtypes"] and not info["qualities"]:
            continue
        print(f"{codec}:")
        if info["subtypes"]:
            print(f"    subtypes       = {info['subtypes']}")
        if info["qualities"]:
            print(f"    qualities      = {info['qualities']}")
    print("=" * 70)
    return results


dump()
