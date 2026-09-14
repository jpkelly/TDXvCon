"""Codec metadata: the human knowledge TouchDesigner cannot tell us.

TouchDesigner exposes menu *tokens* (``prores``, ``ap4h``) but nothing about
what they mean, which containers they need, or when to choose one. This module
holds that mapping, kept deliberately separate from the registry so it can be
reviewed and corrected by a human (you) without touching logic.

Tokens are verified live against `par.menuNames` — see
``toe/dump_codec_menus.py``. NEVER guess a token: an unrecognised menu value
silently falls back to entry 0, which is how an early build produced
valid-looking files in the wrong codec (rle).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CodecMeta:
    """What we know about one TouchDesigner codec token."""

    #: CLI name (what users type) — usually the TD token, but may be clearer.
    cli_name: str
    #: TD's videocodec menu token.
    token: str
    #: Human label for -codecs.
    label: str
    #: Preferred container menu token ('mov', 'mp4', ...).
    container: str = "mov"
    #: File extension to use for outputs.
    ext: str = ".mov"
    #: Codec is appropriate for vcon's transcoding use.
    recommend: bool = True
    #: Why it is NOT recommended (shown by -codecs).
    caveat: str | None = None
    #: Rough encode speed class, for expectations.
    speed: str = "gpu-fast"   # gpu-fast | gpu | cpu | cpu-slow
    #: Default subtype token when the codec has subtypes.
    default_subtype: str | None = None
    #: ``{cli_alias: td_token}`` for codecs with variants. Aliases let users
    #: type natural names ("4444", "hapq") while the token travels intact.
    #:
    #: VERIFIED LIVE via toe/dump_codec_menus.py — these are TD's exact
    #: videocodectype tokens, which are NOT the fourcc codes (a wrong guess
    #: like 'ap4h' for ProRes silently selects menu entry 0).
    subtypes: dict[str, str] = field(default_factory=dict)
    #: ``moviepixelformat`` values THIS codec accepts, in menu order, when no
    #: subtype overrides them.
    #:
    #: CRITICAL: this menu is codec- AND subtype-specific. Verified live:
    #:   prores4444     → yuv44410bit, yuva444412bit   (alpha in 'yuva'!)
    #:   prores422hq    → yuv4228bit/10bit/12bit       (no alpha)
    #:   haphdr         → rgbu, rgbs                   (not rgb/rgba)
    #: Sending a format the selection does not offer silently falls back to
    #: menu index 0 — the same trap as a wrong codec token.
    pixel_formats: tuple[str, ...] = ("rgb", "rgba")
    #: Per-SUBTYPE overrides of ``pixel_formats`` (keyed by TD token).
    #: Verified live via toe/dump_pixel_formats.py.
    pixel_formats_by_subtype: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    #: moviepixelformat token to use when the user asks for alpha. None means
    #: no alpha format exists for this selection.
    alpha_pixel_format: str | None = None
    #: Per-SUBTYPE overrides of ``alpha_pixel_format``.
    alpha_pixel_format_by_subtype: dict[str, str] = field(default_factory=dict)
    #: Quality preset preferred when the codec exposes a quality menu.
    default_quality: str | None = None
    #: Platforms where encoding works.
    platforms: frozenset[str] = frozenset({"mac", "windows"})


#: Catalogue keyed by TD token.
#:
#: Everything in TD's videocodec menu is listed, including the entries we do
#: NOT recommend, so `-codecs` can explain *why* rather than just omitting
#: them. Tokens marked TODO still need live subtype/quality data.
CATALOG: dict[str, CodecMeta] = {
    # ---------------------------------------------------------------- GPU
    "notchlc": CodecMeta(
        cli_name="notchlc",
        token="notchlc",
        label="NotchLC — GPU mezzanine, 12-bit luma, 8-bit chroma/alpha",
        container="mov",
        ext=".mov",
        speed="gpu-fast",
        pixel_formats=("rgb", "rgba"),
        alpha_pixel_format="rgba",
        platforms=frozenset({"mac", "windows"}),
    ),
    "hap": CodecMeta(
        cli_name="hap",
        token="hap",
        label="Hap — GPU playback codec (VJ / media server)",
        container="mov",
        ext=".mov",
        speed="gpu-fast",
        default_subtype="hap",
        # VERIFIED LIVE: hap/hapq/hapr/haphdr — NOT hapa/hapqa. Alpha is a
        # PIXEL FORMAT choice for hap/hapq/hapr, not a subtype.
        subtypes={
            "hap": "hap",
            "hapq": "hapq",
            "hapr": "hapr",
            "haphdr": "haphdr",
            "q": "hapq",
            "hdr": "haphdr",
        },
        # VERIFIED LIVE per subtype — haphdr is the odd one out (rgbu/rgbs).
        pixel_formats=("rgb", "rgba"),
        pixel_formats_by_subtype={
            "hap": ("rgb", "rgba"),
            "hapq": ("rgb", "rgba"),
            "hapr": ("rgb", "rgba"),
            "haphdr": ("rgbu", "rgbs"),
        },
        alpha_pixel_format="rgba",
        alpha_pixel_format_by_subtype={
            "haphdr": None,   # HDR variant exposes no alpha format
        },
        platforms=frozenset({"mac", "windows"}),
        caveat="Playback-focused: Snappy-style block compression, very fast to "
               "decode, larger files than NotchLC at equal quality.",
    ),
    "cineform": CodecMeta(
        cli_name="cineform",
        token="cineform",
        label="GoPro CineForm — wavelet mezzanine",
        container="mov",
        ext=".mov",
        speed="gpu",
        pixel_formats=("rgba",),   # VERIFIED LIVE: CineForm offers only rgba
        alpha_pixel_format="rgba",
        platforms=frozenset({"mac", "windows"}),
    ),
    # ---------------------------------------------------------------- pro
    "prores": CodecMeta(
        cli_name="prores",
        token="prores",
        label="Apple ProRes — edit-suite mezzanine (422 / 4444 variants)",
        container="mov",
        ext=".mov",
        speed="cpu",           # hardware-accelerated on Apple Silicon only
        default_subtype="4444",
        # VERIFIED LIVE — TD's tokens are the full names, NOT the fourccs
        # (ap4h/apch/apcn). Sending a fourcc silently selects entry 0.
        subtypes={
            "422proxy": "prores422proxy",
            "proxy": "prores422proxy",
            "422lt": "prores422lt",
            "lt": "prores422lt",
            "422": "prores422",
            "422hq": "prores422hq",
            "hq": "prores422hq",
            "4444": "prores4444",
            "4444xq": "prores4444xq",
            "xq": "prores4444xq",
        },
        # VERIFIED LIVE per subtype via toe/dump_pixel_formats.py — the
        # 422 variants and the 4444 variants expose DIFFERENT menus, and only
        # 4444 carries alpha (via the 'yuva' format).
        #   prores4444   → yuv44410bit, yuva444412bit
        #   prores422hq  → yuv4228bit, yuv42210bit, yuv42212bit
        pixel_formats=("yuv4228bit", "yuv42210bit", "yuv42212bit"),
        pixel_formats_by_subtype={
            "prores422hq": ("yuv4228bit", "yuv42210bit", "yuv42212bit"),
            "prores422": ("yuv4228bit", "yuv42210bit", "yuv42212bit"),
            "prores422lt": ("yuv4228bit", "yuv42210bit", "yuv42212bit"),
            "prores422proxy": ("yuv4228bit", "yuv42210bit", "yuv42212bit"),
            "prores4444": ("yuv44410bit", "yuva444412bit"),
            "prores4444xq": ("yuv44410bit", "yuva444412bit"),
        },
        # Alpha IS available — but only on the 4444 variants, via 'yuva'.
        # (An earlier reading concluded ProRes had no alpha; that dump had not
        #  selected a subtype, so it saw the 422 menu.)
        alpha_pixel_format=None,
        alpha_pixel_format_by_subtype={
            "prores4444": "yuva444412bit",
            "prores4444xq": "yuva444412bit",
        },
        platforms=frozenset({"mac", "windows"}),
        caveat="CPU/hardware encode; much slower than NotchLC for large frames. "
               "On macOS uses the Apple hardware encoder where available. "
               "Alpha requires a 4444 subtype (4444/4444XQ).",
    ),
    # ------------------------------------------------------- delivery codecs
    "h264": CodecMeta(
        cli_name="h264",
        token="h264",
        label="H.264/AVC — delivery / web",
        container="mp4",
        ext=".mp4",
        speed="cpu",
        pixel_formats=("yuv420", "yuv444p8bit"),
        alpha_pixel_format=None,
        platforms=frozenset({"mac", "windows"}),
        caveat="Delivery codec, not a mezzanine — recompresses heavily. "
               "Needs a Commercial/Pro TD licence and NVIDIA hardware on "
               "Windows (macOS uses VideoToolbox). Audio handled separately.",
    ),
    "h265": CodecMeta(
        cli_name="h265",
        token="h265",
        label="H.265/HEVC — delivery / web",
        container="mp4",
        ext=".mp4",
        speed="cpu",
        pixel_formats=("yuv420", "yuv420p10bit", "yuv444p8bit", "yuv444p10bit"),
        alpha_pixel_format=None,
        platforms=frozenset({"mac", "windows"}),
        caveat="Delivery codec. Requires NVIDIA hardware on Windows.",
    ),
    "av1": CodecMeta(
        cli_name="av1",
        token="av1",
        label="AV1 — delivery / web",
        container="mp4",
        ext=".mp4",
        speed="cpu-slow",
        pixel_formats=("yuv420", "yuv420p10bit"),
        alpha_pixel_format=None,
        platforms=frozenset({"mac", "windows"}),
        caveat="Delivery codec; software encode is slow. NVIDIA hardware "
               "required on Windows.",
    ),
    "vvc": CodecMeta(
        cli_name="vvc",
        token="vvc",
        label="VVC/H.266 — next-gen delivery",
        container="mp4",
        ext=".mp4",
        speed="cpu-slow",
        pixel_formats=("yuv420p10bit",),
        alpha_pixel_format=None,
        recommend=False,
        caveat="Very new and poorly supported by players/editors; software "
               "encode is very slow. Listed for completeness.",
    ),
    # ------------------------------------------------------------- niche
    "mpeg4": CodecMeta(
        cli_name="mpeg4",
        token="mpeg4",
        label="MPEG-4 Part 2 (legacy)",
        container="mp4",
        ext=".mp4",
        speed="cpu",
        pixel_formats=("yuv420",),
        alpha_pixel_format=None,
        recommend=False,
        caveat="Legacy codec with poor quality-per-bitrate; H.264 is better "
               "for every practical purpose.",
    ),
    "mjpa": CodecMeta(
        cli_name="mjpa",
        token="mjpa",
        label="Motion JPEG A (legacy)",
        container="mov",
        ext=".mov",
        speed="cpu",
        pixel_formats=("yuv420", "yuv422"),
        alpha_pixel_format=None,
        recommend=False,
        caveat="Intra-frame JPEG; very large files, no inter-frame "
               "compression. Included for compatibility.",
    ),
    "rle": CodecMeta(
        cli_name="rle",
        token="rle",
        label="QuickTime Animation / RLE (legacy, lossless)",
        container="mov",
        ext=".mov",
        speed="cpu-slow",
        pixel_formats=("rgb", "rgba"),
        alpha_pixel_format="rgba",
        recommend=False,
        caveat="Run-length encoded animation codec — enormous files and the "
               "wrong choice for video. ALSO the default when TD is given an "
               "invalid codec value, so seeing 'rle' usually means a bug.",
    ),
    "gif": CodecMeta(
        cli_name="gif",
        token="gif",
        label="Animated GIF",
        container="automatic",
        ext=".gif",
        speed="cpu",
        pixel_formats=("rgbpal8",),
        alpha_pixel_format=None,
        recommend=False,
        caveat="256-colour, no audio — an image format rather than a video "
               "codec. Use only for web loops.",
    ),
    # ------------------------------------------------------ audio-only / misc
    "vp8": CodecMeta(
        cli_name="vp8",
        token="vp8",
        label="VP8 — web video (legacy)",
        container="webm",
        ext=".webm",
        speed="cpu",
        pixel_formats=("yuv420",),
        alpha_pixel_format=None,
        caveat="Superseded by VP9/AV1.",
    ),
    "vp9": CodecMeta(
        cli_name="vp9",
        token="vp9",
        label="VP9 — web video",
        container="webm",
        ext=".webm",
        speed="cpu",
        pixel_formats=("yuv420", "yuv444p8bit", "yuv420p10bit"),
        alpha_pixel_format=None,
        caveat="Good for web delivery; superseded by AV1.",
    ),
}


def recommended() -> list[CodecMeta]:
    """The catalog entries worth showing in help listings."""
    return [m for m in CATALOG.values() if m.recommend]


def all_metas() -> list[CodecMeta]:
    return list(CATALOG.values())
