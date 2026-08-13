"""
Generate the desktop shortcut icon: a small CPI-vs-Bank-Rate chart in the
dashboard's own palette. Run once; the .ico is committed.

    python scripts/make-icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "dashboard.ico"

CANVAS = "#0F1116"
PANEL = "#161A23"
GRID = "#252B38"
HEADLINE = "#3987e5"   # slot 1, as used for headline CPI
POLICY = "#d95926"     # slot 2, as used for Bank Rate

SIZE = 512
PAD = 62


def rounded_background(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=96, fill=CANVAS)
    draw.rounded_rectangle([26, 26, SIZE - 27, SIZE - 27], radius=74, fill=PANEL)


def gridlines(draw: ImageDraw.ImageDraw) -> None:
    for i in range(1, 4):
        y = PAD + (SIZE - 2 * PAD) * i / 4
        draw.line([(PAD, y), (SIZE - PAD, y)], fill=GRID, width=4)


def scaled(points, lo=0.0, hi=1.0):
    """Map (x fraction, value fraction) pairs into canvas coordinates."""
    left, right = PAD, SIZE - PAD
    top, bottom = PAD + 10, SIZE - PAD - 10
    out = []
    for x, value in points:
        px = left + (right - left) * x
        norm = (value - lo) / (hi - lo)
        py = bottom - (bottom - top) * norm
        out.append((px, py))
    return out


def main() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    rounded_background(draw)
    gridlines(draw)

    # A stylised inflation hump: low, spike, back down.
    headline = scaled([
        (0.00, 0.10), (0.14, 0.16), (0.28, 0.42), (0.42, 0.78),
        (0.55, 0.95), (0.68, 0.66), (0.82, 0.34), (1.00, 0.22),
    ])
    draw.line(headline, fill=HEADLINE, width=30, joint="curve")

    # Bank Rate as a step function that lags the hump and stays high.
    policy_points = [
        (0.00, 0.04), (0.30, 0.04), (0.30, 0.22), (0.48, 0.22),
        (0.48, 0.44), (0.66, 0.44), (0.66, 0.58), (1.00, 0.58),
    ]
    draw.line(scaled(policy_points), fill=POLICY, width=24, joint="curve")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
