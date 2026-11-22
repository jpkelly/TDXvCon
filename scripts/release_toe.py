#!/usr/bin/env python3
"""Make the shipped transcoder.toe from the local dev toe, without /TDMCP.

Development happens in ``dev/TDXvCon-dev.toe``: a local, gitignored project
that keeps the /TDMCP component (TouchDesigner's MCP server on port 13315,
which lets an AI assistant drive the open project). That server executes any
code it is sent, unauthenticated, so it must not ship.

This script never opens TouchDesigner. It expands a copy of the dev toe with
TouchDesigner's ``toeexpand``, removes the top-level /TDMCP component (its
files and its entries in the toc), collapses the result with ``toecollapse``
and checks it before replacing the shipped toe:

* re-expanded, it has no /TDMCP and keeps every other top-level operator;
* the controller and panel text baked into it equals the dev toe's.

It then writes ``transcoder.toe.sources.json`` (see scripts/toe_manifest.py).
Run it after saving the dev toe in TouchDesigner (PUBLISHING.md, step 3):

    python scripts/release_toe.py
    python scripts/release_toe.py --dev path/to/dev.toe --out path/to/out.toe
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toe_manifest as tm  # noqa: E402

DEV_TOE = tm.REPO / "dev" / "TDXvCon-dev.toe"


def find_toecollapse(toeexpand: str) -> str:
    """toecollapse ships next to toeexpand."""
    exe = Path(toeexpand)
    name = "toecollapse.exe" if exe.suffix.lower() == ".exe" else "toecollapse"
    cand = exe.with_name(name)
    if cand.is_file():
        return str(cand)
    found = shutil.which("toecollapse")
    if found:
        return found
    sys.exit(f"toecollapse not found next to {toeexpand}")


def _is_component_entry(entry: str, name: str) -> bool:
    """True for ``name.<ext>`` and anything under ``name/`` in a toc."""
    return entry.startswith(name + "/") or (
        entry.startswith(name + ".") and "/" not in entry)


def strip_components(expanded: Path, names: tuple[str, ...]) -> list[str]:
    """Delete top-level components from an expanded toe, in place.

    Returns the toc entries removed. Raises if anything left in the toe
    still mentions one of them, since a dangling reference would break the
    shipped project in a way this script cannot check.
    """
    toc = expanded.with_name(expanded.name[: -len(".dir")] + ".toc")
    entries = toc.read_text(encoding="utf-8").splitlines()
    removed = [e for e in entries
               if any(_is_component_entry(e, n) for n in names)]
    kept = [e for e in entries if e not in removed]
    for name in names:
        shutil.rmtree(expanded / name, ignore_errors=True)
        for path in expanded.glob(name + ".*"):
            path.unlink()
    toc.write_text("".join(e + "\n" for e in kept), encoding="utf-8")

    leftovers = [str(p.relative_to(expanded)) for p in expanded.rglob("*")
                 if p.is_file()
                 and any(n.encode() in p.read_bytes() for n in names)]
    if leftovers:
        raise RuntimeError(
            f"the toe still refers to {'/'.join(names)} in: "
            + ", ".join(sorted(leftovers)))
    return removed


def make_release(dev: Path, out: Path, toeexpand: str) -> dict:
    toecollapse = find_toecollapse(toeexpand)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        (work / "dev").mkdir()
        dev_dir = tm.expand_into(dev, work / "dev", toeexpand)
        dev_top = tm.top_level_in(dev_dir)
        dev_hashes = tm.hashes_in(dev_dir)
        removed = strip_components(dev_dir, tm.DEV_ONLY)

        # toecollapse writes <name>.toe from <name>.toe.dir + <name>.toe.toc.
        (work / "dev" / "t.toe").unlink()
        subprocess.run([toecollapse, "t.toe.dir"], cwd=work / "dev",
                       check=True, capture_output=True)
        built = work / "dev" / "t.toe"
        if not built.is_file():
            raise RuntimeError("toecollapse did not write a toe")

        (work / "check").mkdir()
        check_dir = tm.expand_into(built, work / "check", toeexpand)
        top = tm.top_level_in(check_dir)
        want = [n for n in dev_top if n not in tm.DEV_ONLY]
        if top != want:
            raise RuntimeError(f"top-level operators {top}, expected {want}")
        hashes = tm.hashes_in(check_dir)
        if hashes != dev_hashes:
            raise RuntimeError("baked controller/panel text changed while "
                               "stripping")

        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built, out)
    return {"removed": removed, "top_level": top, "hashes": hashes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dev", type=Path, default=DEV_TOE,
                    help=f"dev toe to read (default: {DEV_TOE.relative_to(tm.REPO)})")
    ap.add_argument("--out", type=Path, default=tm.TOE,
                    help="toe to write (default: the packaged transcoder.toe)")
    ap.add_argument("--toeexpand")
    args = ap.parse_args()

    if not args.dev.is_file():
        sys.exit(f"no dev toe at {args.dev}: save the project there in "
                 f"TouchDesigner first (see CONTRIBUTING.md)")
    if args.dev.resolve() == args.out.resolve():
        sys.exit("--dev and --out are the same file")

    print(f"=== stripping {'/'.join(tm.DEV_ONLY)} from {args.dev} ===")
    result = make_release(args.dev, args.out,
                          tm.find_toeexpand(args.toeexpand))
    print(f"removed {len(result['removed'])} toc entries; top level now: "
          f"{', '.join(result['top_level'])}")
    print(f"wrote {args.out}")

    stale = [src for src, digest in result["hashes"].items()
             if tm.normalized_sha256((tm.REPO / src).read_bytes()) != digest]
    for src in tm.BAKED.values():
        print(f"{'STALE' if src in stale else 'ok   '}  {src}")
    if args.out.resolve() == tm.TOE.resolve():
        tm.write_manifest(args.out, result["hashes"], result["top_level"])
        print(f"wrote {tm.MANIFEST.relative_to(tm.REPO)}")
    if stale:
        print("warning: the dev toe does not contain the current source of: "
              + ", ".join(stale) + " — save it in TouchDesigner, then re-run")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
