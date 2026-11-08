# Tetris Nametag

Tetris-like pieces fall and stack up to spell a name along the bottom edge of
the screen. The name blinks three times, then the next name is built, and it
loops forever.

Controls:
```
User A: skip to the next name
User B: restart the current name
Menu +/-: back to the app menu (as for every app)
```

## Make it your own

Edit the top of `tetris_nametag.py`:

* `NAMES`: what to show, in order. Letters in `FONT` plus space. Add glyphs to
  `FONT` for anything else (5 wide, 7 tall, `X` is a block).
* `PIECES_AT_ONCE`, `FALL_FRAMES`, `FALL_ROWS`: how many pieces fall together,
  how many refreshes each fall takes, and how high they start.
* `HOP_PULLS`, `SETTLE_PULLS`: how hard each refresh drives the panel (below).
* `BLINK_MODE`, `BLINK_COUNT`, `BLINK_MS`: see below.
* `BANNER_PCT`, `BANNER_IMAGE`: the banner height and its image (see Banner).

## Banner

A red banner runs across the top 25% of the screen, with "ТЕТРИС ☭ TAG" in white
Helvetica Bold centred on it. Pieces fall in the space below it.

The lettering is an image, `tetris_banner.png`, not text drawn by the badge: the badge
has no Helvetica, and its built-in font has neither Cyrillic nor the hammer and sickle.
`make_banner.py` makes it on your computer:

```
pip install pillow fonttools
python3 make_banner.py                                   # rewrites tetris_banner.png
python3 make_banner.py --text "HELLO" --pct 20           # other text or height
mpremote cp tetris_banner.png :data/graphics/tetris_banner.png
```

It sets the text in the Helvetica Bold that ships with macOS, which has the Cyrillic
and Latin letters. Helvetica has no hammer and sickle, so that one glyph comes from a
fallback font (Apple Symbols by default, thickened a little to match the bold letters;
`--symbol-font` picks another). Only the rendered shapes end up in the PNG, no font file.
`BANNER_PCT` in `tetris_nametag.py` and `--pct` must agree (25% is 168 px). If the image
is not on the badge, the banner is a plain red band.

The panel can only make red with a full refresh, so the banner is drawn once, by the full
refresh at the start of each name, and the partial refreshes then hold it untouched.

## Fast partial refresh

The panel's own refresh takes about 30 s, which is no use for animation. This app
uses the fast partial refresh in `firmware/badge/lib/epd_fast.py`
(`display.update(fast=True)`), which redraws only the pixels that changed, in about
1.1 s per drive step ("pull"):

1. Each name starts with one full refresh to a blank field. That is the "clear
   screen" step, and it also wipes any ghosting.
2. Pieces then fall in batches of `PIECES_AT_ONCE`. Each batch is `FALL_FRAMES`
   partial refreshes: it appears up in the air, steps down, and lands.
3. Moving frames use `HOP_PULLS` pulls (1 by default, so a falling piece is pale),
   and the landing frame uses `SETTLE_PULLS` (3, solid black). Anything left pale
   is topped up by the next frame, so there are no grey trails.

With the defaults a name takes roughly 3 to 5 minutes, mostly because each piece
lands in about 7 s. Raise `PIECES_AT_ONCE` to go faster; raise `HOP_PULLS` if falling
pieces are too faint to see. The app prints `refresh ms:` over serial after every
frame, so you can see the real times on your badge.

The pieces are black while falling (the fast waveform cannot make red). If
the badge is not a B1 panel, or the firmware does not have `epd_fast.py`, the app
falls back to a slideshow of full refreshes, one per snapshot, with the pieces in the
air in red.

## Blinking

The paper cannot refresh in half a second, so `BLINK_MODE = "leds"` (the default)
keeps the finished name on the paper and blinks the LED bar, half a second on and
half a second off, three times. `BLINK_MODE = "screen"` blinks the paper itself
(name, blank, name...), but each step is at least one drive step, so it is much slower.

## Install

This app needs the newer display driver on the badge as well as the app itself.
Badges that shipped with older firmware are missing `rendered_luts.py`, which the
fast refresh uses, and an updated `large_png.py`, which the new `epd.py` relies on. Run these from the repo root (`mpremote ls :lib :data` shows
what is on the badge):

```
mpremote cp firmware/badge/lib/epd.py :lib/epd.py
mpremote cp firmware/badge/lib/epd_fast.py :lib/epd_fast.py
mpremote cp firmware/badge/lib/large_png.py :lib/large_png.py
mpremote cp firmware/badge/data/rendered_luts.py :data/rendered_luts.py
mpremote cp user_apps/tetris_nametag/tetris_banner.png :data/graphics/tetris_banner.png
mpremote cp user_apps/tetris_nametag/tetris_nametag.py :apps/tetris_nametag.py
mpremote reset
```

Then select "Tetris Name" from the menu.

Alternatively, `python scripts/update.py push` from `firmware/` brings the whole badge up
to date, but it deletes anything on the badge that is not in `firmware/badge/`,
including this app, so copy the app again afterwards.
