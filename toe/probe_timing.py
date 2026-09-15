"""Find which SOURCE frame each OUTPUT frame actually contains.

Diagnoses time-stretch: if the encoder samples the same source frame
repeatedly, the output plays slower than its own audio track. Compares
tiny grayscale signatures, so codec differences don't matter.

Usage:  python3 toe/probe_timing.py SOURCE OUTPUT
"""
import subprocess
import sys

FFMPEG = ("/Users/jp/Documents/GitHub/vCon/.venv/lib/python3.14/"
          "site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1")
SIG = 32  # signature is SIG x SIG grayscale


def signature(path, seconds):
    """A SIGxSIG grayscale thumbnail of the frame at `seconds`."""
    cmd = [FFMPEG, "-v", "error", "-ss", f"{seconds:.3f}", "-i", path,
           "-frames:v", "1", "-vf", f"scale={SIG}:{SIG}",
           "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True).stdout
    return out if len(out) == SIG * SIG else None


def diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def main(source, output):
    print(f"source: {source}\noutput: {output}\n")
    print(f"{'output@':>9} {'best source match':>18} {'ratio':>7}  {'diff':>6}")
    print("-" * 48)
    for t_out in (20, 40, 60, 90, 120, 150, 180):
        sig_out = signature(output, t_out)
        if sig_out is None:
            print(f"{t_out:>8}s  (no frame — past end of file)")
            continue
        best_t, best_d = None, 1e9
        # coarse sweep, then refine around the winner
        for t_src in [x * 2.0 for x in range(0, 105)]:
            sig_src = signature(source, t_src)
            if sig_src is None:
                continue
            d = diff(sig_out, sig_src)
            if d < best_d:
                best_t, best_d = t_src, d
        for t_src in [best_t + x * 0.2 for x in range(-9, 10)]:
            if t_src < 0:
                continue
            sig_src = signature(source, t_src)
            if sig_src is None:
                continue
            d = diff(sig_out, sig_src)
            if d < best_d:
                best_t, best_d = t_src, d
        ratio = (t_out / best_t) if best_t else float("nan")
        print(f"{t_out:>8}s {best_t:>17.1f}s {ratio:>7.3f}  {best_d:>6.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
