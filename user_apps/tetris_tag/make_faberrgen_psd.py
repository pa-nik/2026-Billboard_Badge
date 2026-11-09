#!/usr/bin/env python3
"""Build an editable, layered version of the Faberrgen screen: a Photoshop .psd (opens in
PhotoCraft, Photoshop, Krita, GIMP).

Run this on your computer, not on the badge:

    pip install pillow fonttools psd-tools
    python3 make_faberrgen_psd.py                # writes faberrgen/design/

The layers are the same pieces the badge screen is made of, at the same size and position
(960 x 672, the badge screen), but in full quality instead of the 1-bit versions that go on
the badge, in four sets (layer name prefixes in the PSD): Top banner, Definitions, Emoji,
Footer.

* Top banner: the red band, the title, and the two score boards and the timer exactly as the
  app draws them (the app's own drawing code is run on the computer, with a sample game in
  progress: lettering and boxes, numbers and next pieces, timer box and digits).
* Definitions, the title and the footer are live text layers in Helvetica Bold (the title's
  hammer and sickle in Apple Symbols), as well as pixels, so an editor that reads text layers
  shows editable text and any other shows the same picture. The score boards use the
  badge's own block letters, which are not a font, so they are pixel layers; the emoji are
  pixel layers too (colour bitmaps from Apple Color Emoji).

These files are a design reference and are NOT read back by anything: the images the badge
loads are made by make_faberrgen.py from the text and the emoji list in that script, so an
edit made only in the PSD does not reach the badge by itself.
"""

import argparse
import types
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from psd_tools.constants import Compression

import make_banner
import make_faberrgen as mf
import psd_text

W, H = mf.WIDTH, mf.HEIGHT
HERE = Path(__file__).resolve().parent
EMOJI_NAMES = ("factory", "egg", "gear", "hatching chick", "chick")
# How the two banners were made (see the README): the top one is smaller than the largest that
# fits, between the score boards, and a little lower.
TITLE = dict(margin=190, height_fraction=0.42, drop=18)
FOOTER = dict(margin=48, height_fraction=0.62, drop=0, size=mf.FOOTER_FONT_SIZE)


def white_on_red(png_path):
    """(red band RGBA, white lettering RGBA) from a 1-bit palette PNG (0 = red, 1 = white)."""
    src = Image.open(png_path)
    if src.mode != "P":
        raise SystemExit(f"{png_path} is not a palette PNG")
    keep = bytes([0, 255]) + bytes(254)  # palette index 1 (white) is the lettering
    mask = Image.frombytes("L", src.size, src.tobytes().translate(keep))
    red = Image.new("RGBA", src.size, (255, 0, 0, 255))
    white = Image.merge("RGBA", (mask, mask, mask, mask))  # white where there is lettering
    return red, white


def black_on_clear(mask):
    """Black pixels whose opacity is the anti-aliased mask."""
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.putalpha(mask)
    return out


def ps_name(path, face=""):
    """The PostScript name of a font (what a text layer calls it), e.g. Helvetica-Bold."""
    if path.lower().endswith(".ttc"):
        font = TTCollection(path).fonts[make_banner.face_index(path, face)]
    else:
        font = TTFont(path)
    return font["name"].getDebugName(6)


def banner_args():
    return types.SimpleNamespace(font=make_banner.MAIN_FONT, face=make_banner.MAIN_FACE, symbol_font=symbol_font(),
                                 symbol_face="", symbol_bold=make_banner.SYMBOL_BOLD)


def symbol_font():
    import glob
    return next((hit for pat in make_banner.SYMBOL_FONTS for hit in sorted(glob.glob(pat))), None)


def text_runs(text, size, args):
    """[(text, font name, pixel size, faux bold)] for a line set the way make_banner sets it:
    characters the main font lacks come from the symbol font, scaled to the capitals."""
    main = ImageFont.truetype(args.font, size, index=make_banner.face_index(args.font, args.face))
    cap = main.getbbox("H", anchor="ls")
    cap_h = cap[3] - cap[1]
    has = make_banner.covered(args.font, args.face, text)
    out = []
    for use_main, chunk in make_banner.runs(text, has):
        if use_main:
            out.append((chunk, ps_name(args.font, args.face), size, False))
            continue
        probe = ImageFont.truetype(args.symbol_font, size)
        top, bottom = probe.getbbox(chunk, anchor="ls")[1], probe.getbbox(chunk, anchor="ls")[3]
        stroke = round(size * args.symbol_bold)
        scale = max(1, cap_h - 2 * stroke) / max(1, bottom - top)
        out.append((chunk, ps_name(args.symbol_font), max(2, round(size * scale)), True))
    return out


def banner_text_layer(text, band_h, top_of_band, png, margin, height_fraction, drop, size=0):
    """A text layer for a banner line: (image, left, top, spec). The pixels are the banner
    image's white lettering; the text starts where make_banner would have put it."""
    args = banner_args()
    size = size or make_banner.fit_size(text, W - 2 * margin, int(band_h * height_fraction), args)
    _canvas, box, _cap = make_banner.layout(text, size, args.font, args.face, args.symbol_font,
                                            args.symbol_face, args.symbol_bold)
    left = (W - (box[2] - box[0])) // 2
    top = (band_h - (box[3] - box[1])) // 2 + drop
    x = left - (box[0] - size)  # where the first baseline starts
    y = top_of_band + top + (2 * size - box[1])
    red, white = white_on_red(png)
    runs = text_runs(text, size, args)
    fonts = list(dict.fromkeys(r[1] for r in runs))
    spec = dict(paragraphs=[[r + (None,) for r in runs]], fonts=fonts, colour=(1, 1, 1), x=x, y=y)
    return red, white, spec, size


def definition_layers(args):
    """The three definition lines as three text layers (words, '=', meanings), three lines
    each, one row apart. Returns [(name, image, left, top, spec)]."""
    banner_h = H * mf.BANNER_PCT // 100
    row_w, row_h = mf.strip_size()
    lay = mf.definition_layout(make_banner.MAIN_FONT, make_banner.MAIN_FACE, args.margin, args.text_size)
    size, ss = lay["size"], mf.SUPERSAMPLE
    font = ImageFont.truetype(make_banner.MAIN_FONT, size * ss,
                              index=make_banner.face_index(make_banner.MAIN_FONT, make_banner.MAIN_FACE))
    name = ps_name(make_banner.MAIN_FONT, make_banner.MAIN_FACE)
    out = []
    for col, label in enumerate(("words", "equals signs", "meanings")):
        texts = [("Fab", "err", "gén"), ("=", "=", "="), ("fabricate", "(make) error(s)", "generate")][col]
        canvas = Image.new("L", (W * ss, 3 * row_h * ss), 0)
        draw = ImageDraw.Draw(canvas)
        for n, t in enumerate(texts):
            draw.text((lay["x"][col] * ss, (n * row_h + lay["base"]) * ss), t, font=font, fill=255, anchor="ls")
        mask = canvas.resize((W, 3 * row_h), Image.LANCZOS)
        spec = dict(paragraphs=[[(t, name, size, False, row_h)] for t in texts], fonts=[name],
                    colour=(0, 0, 0), x=lay["x"][col], y=banner_h + lay["base"])
        out.append((f"Definitions: {label}", black_on_clear(mask), 0, banner_h, spec))
    return out


def layer_spec(args):
    """[(group, name, RGBA image, left, top, text spec or None)], bottom to top in each group."""
    banner_h = H * mf.BANNER_PCT // 100
    foot_h = H * mf.FOOTER_PCT // 100
    row_w, row_h = mf.strip_size()
    layers = []

    red, white, spec, size = banner_text_layer(make_banner.DEFAULT_TEXT, banner_h, 0, HERE / "tetris_banner.png", **TITLE)
    layers += [("Top banner", "Banner red", red, 0, 0, None),
               ("Top banner", f"Title ({size} px, white)", white, 0, 0, spec)]
    for name, img in mf.scoreboard_layers().items():
        layers.append(("Top banner", name, img, 0, 0, None))

    for name, img, left, top, spec in definition_layers(args):
        layers.append(("Definitions", name, img, left, top, spec))

    images = [[mf.emoji_rgba(ch, args.emoji_size) for ch in group] for group in mf.EMOJI_GROUPS]
    placed = mf.place_emoji(images, row_w, 8, 40)
    emoji_top = banner_h + 3 * row_h
    for n, ((x, img), name) in enumerate(zip(placed, EMOJI_NAMES), start=1):
        layers.append(("Emoji", f"Emoji {n}: {name}", img, x, emoji_top + (row_h - img.height) // 2, None))

    foot_red, foot_white, spec, size = banner_text_layer(
        mf.FOOTER_TEXT, foot_h, H - foot_h, HERE / "faberrgen" / "faberrgen_footer.png", **FOOTER)
    layers += [("Footer", "Footer red", foot_red, 0, H - foot_h, None),
               ("Footer", f"Footer text ({size} px, white)", foot_white, 0, H - foot_h, spec)]
    return layers


def trim(img, left, top):
    """Crop a layer to its visible pixels, keeping its place on the canvas."""
    box = img.getchannel("A").getbbox()
    if not box:
        return img, left, top
    return img.crop(box), left + box[0], top + box[1]


def add_layer(parent, img, name, left, top):
    """A pixel layer that keeps its transparency. (PSDImage.create_pixel_layer converts the
    image to the document's RGB mode first, which throws the alpha channel away.)"""
    record, channels = PixelLayer._build_layer_record_and_channels(
        img.convert("RGBA"), name, left, top, Compression.RLE)
    layer = PixelLayer(parent, record, channels)
    parent.append(layer)
    return layer


def write_psd(layers, path):
    psd = PSDImage.new("RGB", (W, H), color=(255, 255, 255))
    add_layer(psd, Image.new("RGBA", (W, H), (255, 255, 255, 255)), "Background", 0, 0)
    # Flat list, named "Group / layer". (Layer groups made with psd-tools came out with an
    # empty composite when read back, so the PSD has none.)
    for group, name, img, left, top, spec in layers:
        img, left, top = trim(img, left, top)
        if spec:
            psd_text.add_text_layer(psd, img, f"{group} / {name}", left, top, **spec)
        else:
            add_layer(psd, img, f"{group} / {name}", left, top)
    # The flattened picture stored in the file, for viewers that do not read layers.
    r, g, b = flatten(layers).split()
    psd._record.image_data.set_data([r.tobytes(), g.tobytes(), b.tobytes()], psd._record.header)
    psd.save(str(path))


def flatten(layers):
    out = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    for _, _, img, left, top, _spec in layers:
        out.alpha_composite(img, (left, top))
    return out.convert("RGB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "faberrgen" / "design"), help="directory for the files")
    ap.add_argument("--margin", type=int, default=40)
    ap.add_argument("--text-size", type=int, default=60)
    ap.add_argument("--emoji-size", type=int, default=68)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    layers = layer_spec(args)
    write_psd(layers, out / "faberrgen_screen.psd")
    flatten(layers).save(out / "faberrgen_screen_preview.png")
    live = sum(1 for l in layers if l[5])
    print(f"{len(layers)} layers ({live} of them live text) + background in 4 groups; wrote "
          f"faberrgen_screen.psd and faberrgen_screen_preview.png to {out.resolve()}")


if __name__ == "__main__":
    main()
