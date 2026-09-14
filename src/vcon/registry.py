"""Codec registry.

Declarative table of everything vcon can encode. The TouchDesigner controller
stays dumb: it receives resolved parameter values and sets them on the
`Movie File Out TOP` — all codec knowledge lives here, in the front-end.

Movie File Out TOP's four format-selecting parameters (verified against
docs.derivative.ca, 2026-09):

- ``videocodec``       — the codec
- ``videocodectype``   — subtype (ProRes variant, Hap variant, ...)
- ``moviepixelformat`` — pixel format; alpha-capable values enable alpha
- ``moviecontainer``   — .mov / .mp4

v1 ships one entry (notchlc); adding Hap/ProRes/H264 later is a table row +
a test.
"""

from __future__ import annotations

import platform as _stdlib_platform
import sys
from dataclasses import dataclass, field
from typing import Any

from vcon.codec_meta import CodecMeta, all_metas
from vcon.errors import CodecError

#: Quality ladder NotchLC uses (per Notch manual); optimal is the sweet spot.
NOTCHLC_QUALITY = ("good", "very-good", "excellent", "optimal", "best")


def platform_of_current_machine() -> str:
    """"darwin" → "mac", "win32" → "windows"; anything else → "other"."""
    if sys.platform.startswith("darwin"):
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "other"


@dataclass(frozen=True)
class CodecSpec:
    """Everything the pipeline needs to know about one encodable codec."""

    #: Registry key used on the CLI: ``vcon -c <name> ...``
    name: str
    #: Human label for ``-codecs`` listing.
    label: str
    #: Value for Movie File Out TOP's ``videocodec`` parameter.
    td_codec: str
    #: ``{cli_key: td_videocodectype_value}`` — empty when the codec has no
    #: subtypes (NotchLC).
    subtypes: dict[str, str] = field(default_factory=dict)
    #: CLI key of the default subtype, if any.
    default_subtype: str | None = None
    #: Acceptable ``-q`` values. Empty tuple → codec takes no quality flag.
    qualities: tuple[str, ...] = ()
    #: Default quality (None → codec's internal default).
    default_quality: str | None = None
    #: moviepixelformat value to use when alpha is required. None means this
    #: codec cannot carry alpha in the installed TD build.
    alpha_pixel_format: str | None = None
    #: moviepixelformat value when alpha is off (None → leave TD default).
    opaque_pixel_format: str | None = None
    #: Every moviepixelformat value this codec accepts, in menu order.
    #: Codec-specific — verified live.
    pixel_formats: tuple[str, ...] = ()
    #: Per-subtype overrides (keyed by TD token). The pixel-format menu
    #: changes with the subtype: ProRes 4444 offers yuva444412bit (alpha) while
    #: 422 variants offer only yuv422*; Hap's haphdr offers rgbu/rgbs.
    pixel_formats_by_subtype: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    #: Alpha-capable format per TD subtype token.
    alpha_pixel_format_by_subtype: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def pixel_formats_for(self, resolved_subtype: str | None) -> tuple[str, ...]:
        """Menu entries available for this subtype (falls back to the codec)."""
        if resolved_subtype and resolved_subtype in self.pixel_formats_by_subtype:
            return self.pixel_formats_by_subtype[resolved_subtype]
        return self.pixel_formats

    def alpha_format_for(self, resolved_subtype: str | None) -> str | None:
        """Alpha-capable pixel format for this subtype, or None."""
        if resolved_subtype and resolved_subtype in self.alpha_pixel_format_by_subtype:
            return self.alpha_pixel_format_by_subtype[resolved_subtype]
        return self.alpha_pixel_format
    #: File extension TD must write (moviecontainer). NOTE: these are the
    #: *menu* values, verified live on TD — 'mov' not '.mov'.
    #: Verified menu (TD, 2026-09-13): ['automatic','mov','mp4','mkv','webm']
    default_ext: str = "mov"
    #: Platforms where encoding is supported: subset of {"mac", "windows"}.
    platforms: frozenset[str] = frozenset({"mac", "windows"})
    #: One-line caveat printed by ``-codecs`` (e.g. NVIDIA requirement).
    caveat: str | None = None
    #: Free-form per-codec option validation, keyed by option name.
    options: dict[str, tuple[Any, ...]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def supports_platform(self, machine: str) -> bool:
        return machine in self.platforms

    def resolve_subtype(self, requested: str | None) -> str | None:
        """Validate a CLI subtype against the table; None = codec default."""
        if requested is None:
            return self.subtypes.get(self.default_subtype) if self.default_subtype else None
        if requested not in self.subtypes:
            raise CodecError(
                f"codec '{self.name}' has no subtype '{requested}' "
                f"(available: {', '.join(self.subtypes) or 'none'})"
            )
        return self.subtypes[requested]

    def resolve_quality(self, requested: str | None) -> str | None:
        """Validate a CLI quality; None falls back to the codec default."""
        if requested is None:
            return self.default_quality
        if self.qualities and requested not in self.qualities:
            raise CodecError(
                f"codec '{self.name}' accepts quality one of: "
                f"{', '.join(self.qualities)}"
            )
        return requested

    def pixel_format_for(self, alpha: bool) -> str | None:
        return self.alpha_pixel_format if alpha else self.opaque_pixel_format

    def td_params(
        self,
        subtype: str | None = None,
        quality: str | None = None,
        fps: str = "auto",
        alpha: bool | None = None,
    ) -> dict[str, Any]:
        """Build the Movie File Out TOP parameter payload for one job.

        These are the values the touchdesigner controller applies verbatim —
        the toe contains no codec knowledge, so every codec-specific decision
        (subtype menu value, pixel-format-for-alpha, quality name, fps) is
        resolved here and travels over the wire.

        IMPORTANT: menu parameters must use TD's INTERNAL menu value, not the
        human-readable label. The labels the docs use ("NotchLC") differ in
        case from the actual menu token ("notchlc"); assigning a value that is
        not in the menu silently falls back to entry 0 (which is 'rle'), so a
        wrong value here produces a valid-looking file in the WRONG codec.
        """
        params: dict[str, Any] = {
            "videocodec": self.td_codec,
            # The human label, for error messages and logs only.
            "videocodec_label": self.label,
        }
        resolved_sub = self.resolve_subtype(subtype)
        if resolved_sub is not None:
            params["videocodectype"] = resolved_sub
        resolved_q = self.resolve_quality(quality)
        if resolved_q is not None:
            params["quality"] = resolved_q
        if self.default_ext:
            params["moviecontainer"] = self.default_ext
        # Pixel format is CODEC- AND SUBTYPE-SPECIFIC. Only send a value the
        # current selection actually offers, or TD silently falls back to
        # menu index 0 (same failure mode as a wrong codec token).
        fmts = self.pixel_formats_for(resolved_sub)
        if alpha is True:
            alpha_fmt = self.alpha_format_for(resolved_sub)
            if alpha_fmt is None:
                label = f"{self.name}"
                if subtype or resolved_sub:
                    label += f" -t {subtype or resolved_sub}"
                raise CodecError(
                    f"{label} cannot encode alpha. Available pixel formats: "
                    f"{', '.join(fmts) or 'none'}"
                    + (f". Try a 4444 subtype for ProRes."
                       if self.name == "prores" else "")
                )
            params["moviepixelformat"] = alpha_fmt
        elif alpha is False and fmts:
            params["moviepixelformat"] = fmts[0]
        params["fps"] = fps or "auto"
        return params

    def output_name(self, input_path_name: str, out_ext: str | None = None) -> str:
        """Suggested output filename: ``clip.mov`` → ``clip.<name><ext>``."""
        stem = input_path_name.rsplit(".", 1)[0] if "." in input_path_name else input_path_name
        ext = out_ext if out_ext is not None else self.default_ext
        if not ext.startswith("."):
            ext = "." + ext
        return f"{stem}.{self.name}{ext}"


def spec_from_meta(meta: CodecMeta) -> CodecSpec:
    """Build a registry entry from the codec catalogue.

    This is what makes the tool cover "every codec TouchDesigner offers"
    without a code change per codec: add or correct a CodecMeta and the CLI
    flag, validation, listing and wire payload all follow.
    """
    # NotchLC is the one codec with a quality ladder rather than a subtype
    # menu; its five levels are documented by Notch.
    qualities: tuple[str, ...] = ()
    default_quality: str | None = None
    if meta.token == "notchlc":
        qualities = NOTCHLC_QUALITY
        default_quality = "optimal"

    return CodecSpec(
        name=meta.cli_name,
        label=meta.label,
        td_codec=meta.token,
        subtypes=dict(meta.subtypes),
        default_subtype=meta.default_subtype,
        qualities=qualities,
        default_quality=default_quality,
        # Per-codec, from live par.menuNames. A single hardcoded value was
        # wrong: ProRes exposes only yuv422* and would silently fall back to
        # menu index 0 when sent 'rgba'.
        alpha_pixel_format=meta.alpha_pixel_format,
        opaque_pixel_format=(meta.pixel_formats[0] if meta.pixel_formats else None),
        pixel_formats=tuple(meta.pixel_formats),
        pixel_formats_by_subtype={
            k: tuple(v) for k, v in meta.pixel_formats_by_subtype.items()
        },
        alpha_pixel_format_by_subtype=dict(meta.alpha_pixel_format_by_subtype),
        default_ext=meta.container,
        platforms=meta.platforms,
        caveat=meta.caveat,
        options={"speed": (meta.speed,), "recommend": (meta.recommend,)},
    )


#: Every codec is generated from the catalogue in codec_meta.py — the single
#: place a human edits. Tokens there are validated at runtime against TD's
#: live par.menuNames by the toe, so a wrong token fails loudly instead of
#: silently producing a file in codec index 0 ('rle').
BUILTIN_CODECS: tuple[CodecSpec, ...] = tuple(
    spec_from_meta(m) for m in sorted(all_metas(), key=lambda m: m.cli_name)
)


class Registry:
    """Lookup + validation front for the codec table."""

    def __init__(self, codecs: tuple[CodecSpec, ...] = BUILTIN_CODECS) -> None:
        self._codecs = {c.name: c for c in codecs}

    def get(self, name: str) -> CodecSpec:
        try:
            return self._codecs[name]
        except KeyError:
            known = ", ".join(sorted(self._codecs))
            raise CodecError(f"unknown codec '{name}' (known: {known})") from None

    @property
    def names(self) -> list[str]:
        return sorted(self._codecs)

    def listing(self) -> list[dict[str, Any]]:
        """Rows for ``vcon -codecs``."""
        machine = platform_of_current_machine()
        rows = []
        for name in sorted(self._codecs):
            c = self._codecs[name]
            rows.append(
                {
                    "name": c.name,
                    "label": c.label,
                    "platforms": sorted(c.platforms),
                    "available_here": c.supports_platform(machine),
                    "subtypes": sorted(c.subtypes) if c.subtypes else None,
                    "qualities": list(c.qualities) or None,
                    "caveat": c.caveat,
                    "options": dict(c.options),
                }
            )
        return rows

    def preflight(self, name: str, machine: str | None = None) -> CodecSpec:
        """Fetch a codec and confirm it can encode on this machine.

        Raises CodecError with an actionable message otherwise.
        """
        spec = self.get(name)
        machine = machine or platform_of_current_machine()
        if not spec.supports_platform(machine):
            where = "this platform" if machine == "other" else f"{machine}"
            raise CodecError(
                f"codec '{name}' cannot encode on {where} "
                f"(supported: {', '.join(sorted(spec.platforms))})"
            )
        if spec.caveat:
            # Caveat text is advisory; preflight surfaces it as an error only
            # when the platform is unsupported. Advisory text reaches users
            # via -codecs and the CLI.
            pass
        return spec