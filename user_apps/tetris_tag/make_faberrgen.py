#!/usr/bin/env python3
"""Render the images for Tetris Tag's Faberrgen screen.

Run this on your computer, not on the badge:

    pip install pillow fonttools
    python3 make_faberrgen.py                  # writes faberrgen_*.png here

then copy the images to the badge:

    mpremote cp faberrgen_*.png :data/graphics/

The screen is built from full-width strips that the app draws one at a time, each
with a partial refresh, so the lines "come in one at a time". The strips fill the space
between the red banner across the top and the red footer (each 25% of the screen), which
stay on the screen from the game:

    faberrgen_row0.png .. row2.png   the three definition lines (black on white)
    faberrgen_emoji1.png .. emoji5.png  the emoji row, one more emoji in each (black)
    faberrgen_emoji_red.png          the finished emoji row in red, for the full refresh
                                     that turns the black emoji red at the end
    faberrgen_footer.png             white Helvetica Bold on a red band, bottom 25%

Every strip is 960 px wide and one row tall (a quarter of the 336 px between the two
bands, 84 px), so the app only needs to know the row number. All text is Helvetica Bold from
macOS. The emoji come from Apple Color Emoji and are turned into black and white
(the fast refresh cannot make colour): dithered by default, --style threshold for solid
shapes. Only the rendered shapes end up in the PNGs.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

import make_banner

WIDTH = 960
HEIGHT = 672
FOOTER_PCT = 25
BANNER_PCT = 25  # the red banner across the top, which the Faberrgen screen shares
ROWS = 4  # three text lines and the emoji row
SUPERSAMPLE = 4

LINES = (("Fab", "fabricate"), ("err", "(make) error(s)"), ("g\u00e9n", "generate"))  # "gén"
EMOJI_GROUPS = (("\U0001F3ED",), ("\U0001F95A", "⚙️", "\U0001F423"), ("\U0001F425",))
# The emoji line is "🏭 🥚⚙️🐣 🐥": a space between groups, none inside a group.
FOOTER_TEXT = "www.faberrgen.com"
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"


def strip_size():
    footer = HEIGHT * FOOTER_PCT // 100
    banner = HEIGHT * BANNER_PCT // 100
    return WIDTH, (HEIGHT - footer - banner) // ROWS


def save_1bit(mask, path, ink=(0, 0, 0)):
    """mask: L image, 255 where there is ink. Saved as an ink on white palette PNG."""
    out = Image.new("P", mask.size, 1)
    out.putpalette(list(ink) + [255, 255, 255] + [0] * 756)  # 0 = ink, 1 = white
    out.paste(0, mask=mask)
    out.save(path, bits=1, optimize=True)


def text_strips(font_path, face, margin, size_cap, threshold=True):
    """The three definition lines, '=' signs lined up, the block centred. With threshold
    False the masks keep their anti-aliased grey levels (for the layered design file)."""
    w, h = strip_size()
    index = make_banner.face_index(font_path, face)

    def font_at(px):
        return ImageFont.truetype(font_path, px, index=index)

    def widths(px):
        f = font_at(px)
        col1 = max(f.getlength(a) for a, _ in LINES)
        eq = f.getlength("=")
        gap = f.getlength(" ")
        col2 = max(f.getlength(b) for _, b in LINES)
        return col1, eq, gap, col2

    size = size_cap
    while size > 8:
        col1, eq, gap, col2 = widths(size * SUPERSAMPLE)
        if (col1 + eq + col2 + 2 * gap) / SUPERSAMPLE <= WIDTH - 2 * margin:
            break
        size -= 1
    big = size * SUPERSAMPLE
    f = font_at(big)
    col1, eq, gap, col2 = widths(big)
    block = col1 + eq + col2 + 2 * gap
    x0 = (WIDTH * SUPERSAMPLE - block) / 2
    cap = f.getbbox("H", anchor="ls")
    base = (h * SUPERSAMPLE + (cap[3] - cap[1])) / 2  # baseline: capitals centred in the row
    strips = []
    for left, right in LINES:
        canvas = Image.new("L", (WIDTH * SUPERSAMPLE, h * SUPERSAMPLE), 0)
        d = ImageDraw.Draw(canvas)
        d.text((x0, base), left, font=f, fill=255, anchor="ls")
        d.text((x0 + col1 + gap, base), "=", font=f, fill=255, anchor="ls")
        d.text((x0 + col1 + gap + eq + gap, base), right, font=f, fill=255, anchor="ls")
        mask = canvas.resize((w, h), Image.LANCZOS)
        strips.append(mask.point(lambda v: 255 if v >= 128 else 0) if threshold else mask)
    return strips, size


def emoji_rgba(ch, height):
    """One emoji in full colour (RGBA) scaled so its longer side is `height` pixels."""
    font = ImageFont.truetype(EMOJI_FONT, 160)  # the only size the bitmap font has
    canvas = Image.new("RGBA", (260, 260), (255, 255, 255, 0))
    ImageDraw.Draw(canvas).text((30, 30), ch, font=font, embedded_color=True)
    glyph = canvas.crop(canvas.getbbox())
    scale = height / max(glyph.width, glyph.height)
    return glyph.resize((max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))), Image.LANCZOS)


def emoji_image(ch, height, style):
    """One emoji as a black and white L image (255 = ink) of the given height."""
    glyph = emoji_rgba(ch, height)
    flat = Image.new("RGBA", glyph.size, (255, 255, 255, 255))
    flat.alpha_composite(glyph)
    grey = ImageOps.autocontrast(flat.convert("L"), cutoff=1)
    alpha = glyph.split()[3].point(lambda v: 255 if v > 100 else 0)
    if style == "dither":
        tone = grey.convert("1", dither=Image.FLOYDSTEINBERG).convert("L")
    else:
        tone = grey.point(lambda v: 0 if v < 150 else 255)
    ring = ImageChops.subtract(alpha.filter(ImageFilter.MaxFilter(5)), alpha.filter(ImageFilter.MinFilter(3)))
    shape = Image.new("L", glyph.size, 255)  # 0 = ink here, to match tone
    shape.paste(tone, mask=alpha)
    shape.paste(0, mask=ring)
    return ImageOps.invert(shape)  # 255 = ink


def place_emoji(images, width, in_gap, group_gap):
    """[(x, image)] for the emoji of each group in a row `width` wide, centred: a small gap
    inside a group, a bigger one between groups."""
    total = sum(img.width for group in images for img in group)
    total += in_gap * sum(len(g) - 1 for g in images) + group_gap * (len(images) - 1)
    x = (width - total) // 2
    placed = []
    for group in images:
        for k, img in enumerate(group):
            placed.append((x, img))
            x += img.width + (in_gap if k < len(group) - 1 else group_gap)
    return placed


def emoji_strips(style, emoji_px, in_gap, group_gap):
    """Five strips; strip k has the first k emoji of the line in place."""
    w, h = strip_size()
    images = [[emoji_image(ch, emoji_px, style) for ch in group] for group in EMOJI_GROUPS]
    placed = place_emoji(images, w, in_gap, group_gap)
    strips = []
    for count in range(1, len(placed) + 1):
        canvas = Image.new("L", (w, h), 0)
        for px, img in placed[:count]:
            canvas.paste(255, (px, (h - img.height) // 2), img)
        strips.append(canvas)
    return strips


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=".", help="directory for the PNGs")
    ap.add_argument("--style", choices=("dither", "threshold"), default="dither", help="how emoji become black and white")
    ap.add_argument("--margin", type=int, default=40, help="minimum clear pixels left and right of the text")
    ap.add_argument("--text-size", type=int, default=60, help="largest text size, in pixels")
    ap.add_argument("--emoji-size", type=int, default=68)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    lines, size = text_strips(make_banner.MAIN_FONT, make_banner.MAIN_FACE, args.margin, args.text_size)
    for n, strip in enumerate(lines):
        save_1bit(strip, out / f"faberrgen_row{n}.png")
    strips = emoji_strips(args.style, args.emoji_size, 8, 40)
    for n, strip in enumerate(strips, start=1):
        save_1bit(strip, out / f"faberrgen_emoji{n}.png")
    save_1bit(strips[-1], out / "faberrgen_emoji_red.png", ink=(255, 0, 0))
    subprocess.run([sys.executable, str(Path(__file__).with_name("make_banner.py")), "--text", FOOTER_TEXT,
                    "--pct", str(FOOTER_PCT), "--out", str(out / "faberrgen_footer.png")], check=True)
    print(f"text size {size} px, strips {strip_size()}, emoji {args.style}; wrote 10 PNGs to {out.resolve()}")


if __name__ == "__main__":
    main()
