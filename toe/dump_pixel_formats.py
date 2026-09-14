"""dump_pixel_formats.py — find out which codec+subtype combos allow ALPHA.

RUN IN TOUCHDESIGNER'S TEXTPORT (with transcoder.toe open):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/dump_pixel_formats.py',
              encoding='utf-8').read())

WHY THIS EXISTS

The first codec dump set only `videocodec` and read `moviepixelformat`, which
returned yuv422-only for ProRes. That is NOT enough to conclude "ProRes cannot
carry alpha": the pixel-format menu is likely dependent on the *subtype* too,
and ProRes 4444 is specifically the alpha-capable variant. Reading the menu
with the default subtype selected would hide that.

So this script walks every codec × every subtype and records the pixel-format
menu for each combination — and explicitly flags whether any menu entry looks
alpha-capable. That turns "cannot do alpha" from a guess into a finding.

Note: TouchDesigner may need a frame or two to recompute a dependent menu
after a parameter changes, so we cook and retry before believing a reading.
"""

import time

# Locate the movieout INSIDE whichever vCon component exists (see above).

#: Substrings that indicate an alpha-carrying pixel format.
#:
#: 'yuva' matters critically — ProRes 4444's alpha format is 'yuva444412bit',
#: which contains none of the old hints (alpha/rgba/argb/bgra/premult), so an
#: earlier run wrongly concluded ProRes could not carry alpha.
ALPHA_HINTS = (
    "alpha", "rgba", "argb", "bgra", "premult",
    "yuva", "rgba", "a444", "argb",
)


def _mfo():
    for comp in ops("*"):
        m = comp.op("movieout")
        if m is not None and comp.op("vcon_controller") is not None:
            print(f"using {m.path}")
            return m
    raise RuntimeError(
        "could not find a vCon component with a movieout child — open "
        "transcoder.toe first, or run toe/build_network.py"
    )


def _names(par):
    try:
        return list(par.menuNames or [])
    except Exception:
        return []


def _settle(mfo, ticks=3):
    """Cook a few frames so dependent menus recompute before we read them."""
    for _ in range(ticks):
        mfo.cook(force=True)
        time.sleep(0.02)


def _alpha_capable(formats):
    return [f for f in formats if any(h in f.lower() for h in ALPHA_HINTS)]


def dump():
    mfo = _mfo()
    orig_codec = mfo.par.videocodec.eval()
    orig_sub = None
    try:
        orig_sub = mfo.par.videocodectype.eval()
    except Exception:
        pass

    print("=" * 72)
    print("PIXEL FORMAT per CODEC x SUBTYPE  (alpha capability check)")
    print("=" * 72)

    findings = {}
    for codec in _names(mfo.par.videocodec):
        mfo.par.videocodec.val = codec
        _settle(mfo)

        subtypes = _names(mfo.par.videocodectype) or [None]
        per_subtype = {}

        for sub in subtypes:
            if sub is not None:
                try:
                    mfo.par.videocodectype.val = sub
                except Exception as exc:
                    per_subtype[sub] = {"error": str(exc)}
                    continue
            _settle(mfo)
            fmts = _names(mfo.par.moviepixelformat)
            per_subtype[sub] = {
                "pixel_formats": fmts,
                "alpha_capable": _alpha_capable(fmts),
            }

        findings[codec] = per_subtype

        # Report per codec, compactly.
        if len(per_subtype) == 1 and None in per_subtype:
            info = per_subtype[None]
            a = info.get("alpha_capable") or []
            flag = f"  ALPHA OK: {a}" if a else "  no alpha format"
            print(f"  {codec:<10} {info.get('pixel_formats')}{flag}")
        else:
            print(f"  {codec}:")
            for sub, info in per_subtype.items():
                if "error" in info:
                    print(f"      {sub:<18} !! {info['error']}")
                    continue
                a = info.get("alpha_capable") or []
                flag = f"  <-- ALPHA: {a}" if a else ""
                print(f"      {sub:<18} {info['pixel_formats']}{flag}")

    # Restore state.
    try:
        if orig_sub is not None:
            mfo.par.videocodectype.val = orig_sub
        mfo.par.videocodec.val = orig_codec
    except Exception:
        pass

    print()
    print("=" * 72)
    print("SUMMARY — codecs/subtypes that CAN carry alpha")
    print("=" * 72)
    any_alpha = False
    for codec, subs in findings.items():
        for sub, info in subs.items():
            if info.get("alpha_capable"):
                any_alpha = True
                label = f"{codec}" + (f" -t {sub}" if sub else "")
                print(f"  {label:<28} {info['alpha_capable']}")
    if not any_alpha:
        print("  (none found)")

    print()
    print("=" * 72)
    print("PASTE-READY (pixel formats per codec/subtype)")
    print("=" * 72)
    for codec, subs in findings.items():
        for sub, info in subs.items():
            if "pixel_formats" not in info:
                continue
            label = f"{codec}" + (f"/{sub}" if sub else "")
            print(f"  {label:<28} {info['pixel_formats']}")

    return findings


dump()
