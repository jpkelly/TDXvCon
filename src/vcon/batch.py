"""Batch folder scanning — the panel/CLI seam for folder transcoding.

Walks a source folder (optionally recursive), keeps the directory structure
for outputs, and filters to the movie extensions TouchDesigner's Movie File
In TOP actually supports (docs.derivative.ca/File_Types, verified 2026-09):

    .m4v .mkv .mov .mp4 .hsp .notchlc .mpeg .mpg .avi .flv
    .m2ts .wmv .h265 .vp8 .vp9 .3gp .mxf .ts .r3d

Both the CLI and the TouchDesigner panel call the same helpers, so batch
behavior can never drift between the two front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Movie extensions TD's Movie File In TOP imports (official File Types
#: table). Lowercase, no dot. NOT a guess-list: wrong extensions produce
#: "input not found" style failures deep in the encoder.
MOVIE_EXTENSIONS = frozenset({
    "m4v", "mkv", "mov", "mp4", "hsp", "notchlc", "mpeg", "mpg", "avi",
    "flv", "m2ts", "wmv", "h265", "vp8", "vp9", "3gp", "mxf", "ts", "r3d",
})


def is_movie(path: Path) -> bool:
    """True if the path's extension is one TD can import as a movie."""
    return path.suffix.lower().lstrip(".") in MOVIE_EXTENSIONS


@dataclass(frozen=True)
class BatchItem:
    """One discovered source file and its output location."""

    input: Path
    #: Output path, or None if no destination was given (caller derives).
    output: Path | None = None
    #: Path relative to the scan root, for queue display ("sub/a.mov").
    relpath: str = ""


def scan_folder(
    folder: Path,
    destination: Path,
    *,
    recursive: bool = True,
    keep_structure: bool = True,
) -> list[BatchItem]:
    """Find movie files under ``folder``; map each to a destination output.

    - ``recursive=True``  walks subfolders too.
    - ``keep_structure=True`` mirrors the source tree under ``destination``
      (``src/sub/a.mov`` → ``dst/sub/<name>``); False flattens.

    Raises NotADirectoryError if ``folder`` is not a directory.
    """
    folder = Path(folder)
    destination = Path(destination)
    if not folder.is_dir():
        raise NotADirectoryError(f"not a folder: {folder}")

    items: list[BatchItem] = []
    pattern = folder.rglob("*") if recursive else folder.glob("*")
    for path in sorted(pattern):
        if not path.is_file() or not is_movie(path):
            continue
        rel = path.relative_to(folder)
        if keep_structure:
            out_dir = destination / rel.parent
        else:
            out_dir = destination
        items.append(
            BatchItem(
                input=path,
                output=out_dir / path.name,
                relpath=rel.as_posix(),
            )
        )
    return items


def derive_outputs(
    items: list[BatchItem],
    destination: Path,
    *,
    suffix: str | None = None,
    extension: str | None = None,
    keep_structure: bool = True,
) -> list[BatchItem]:
    """Re-map every item's output against one destination folder.

    Used when the user changes the destination after scanning: the batch
    keeps its file list but the outputs move. ``suffix``/``extension``
    decorate the output filename (``a.mov`` → ``a.nlc.mov`` style naming is
    done by the caller with the codec in hand — this helper only moves
    paths).
    """
    destination = Path(destination)
    out: list[BatchItem] = []
    for item in items:
        rel = Path(item.relpath or item.input.name)
        parent = rel.parent if keep_structure else Path(".")
        name = rel.name
        stem = Path(name).stem
        # extension REPLACES the original (mov → mp4); suffix DECORATES the
        # stem (a.mov → a.notchlc.mov). Both together: a.notchlc.mp4.
        if extension:
            name = f"{stem}{extension}"
        if suffix:
            name = f"{stem}.{suffix}{Path(name).suffix}"
        out.append(
            BatchItem(
                input=item.input,
                output=destination / parent / name,
                relpath=item.relpath,
            )
        )
    return out