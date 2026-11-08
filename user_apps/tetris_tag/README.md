# Tetris Tag

Tetris-like pieces fall and stack up to spell a name along the bottom edge of
the screen. The name blinks three times, then it is built again, and it loops forever.
It ships with the placeholder "YOUR NAME"; put your own in `NAMES` (see below).

Controls:
```
User A: skip to the next name (restarts it when `NAMES` has just one)
User B: restart the current name
Menu +/-: back to the app menu (as for every app)
```

## Make it your own

Edit the top of `tetris_tag.py`:

* `NAMES`: what to show, in order. It starts as `("YOUR NAME",)`: replace that with your
  own name, or list several to cycle through them. Only characters in `FONT` can be
  shown: capitals A E F H I K M N O P R S U V Y, some lowercase, and space. Add a glyph to
  `FONT` for any other letter (5 wide, 7 tall, `X` is a block).
* `PIECES_AT_ONCE`, `SPAWN_PCT`, `ROTATE_DROP_ROWS`: the most pieces that fall together in a
  wave, the screen height they all start from, and how far they drop with each turn.
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
`BANNER_PCT` in `tetris_tag.py` and `--pct` must agree (25% is 168 px). If the image
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
2. The pieces then fall in waves of up to `PIECES_AT_ONCE`. Every piece in a wave appears
   at the same height, `SPAWN_PCT` (25%) down from the top of the screen, which is the
   bottom edge of the banner, turned a random quarter turn (90, 180 or 270 degrees).
   Each refresh after that turns every piece another 90 degrees, dropping it a few rows
   (`ROTATE_DROP_ROWS`), until it is the right way up. The refresh after that drops it
   straight into place. A square, which looks the same turned, needs no turning.
3. A wave is 2 to 4 refreshes. Frames in which pieces are moving use `HOP_PULLS` pulls (1
   by default, so they are pale), and the last frame of the wave uses `SETTLE_PULLS` (3, solid
   black). Anything left pale is topped up by the next frame, so there are no grey trails.

A piece joins a wave only if it can never land on another piece of that wave in the
air, in any frame, and only once the pieces it rests on have landed. So a wave holds
fewer pieces than `PIECES_AT_ONCE` when letters are crowded.

With the defaults, falling takes about 45 s per pass for a name like "YOUR NAME" (about 6 waves, about
20 refreshes), about four times faster than falling a couple of pieces at a time, which
took about 3 minutes. Each pass also starts with the full-screen refresh, about 37 s, which
cannot be made faster. Raise `PIECES_AT_ONCE` to go faster still (past about 10 it stops
helping, since pieces wait for the ones below them); raise `HOP_PULLS` if falling pieces
are too faint to see. The app prints `refresh ms:` over serial after every frame, so you can
see the real times on your badge.

The pieces are black while falling (the fast waveform cannot make red). If
the badge is not a B1 panel, or the firmware does not have `epd_fast.py`, the app
falls back to a slideshow of full refreshes, one per snapshot, with the pieces in the
air in red. The slideshow does not turn the pieces.

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
mpremote cp user_apps/tetris_tag/tetris_banner.png :data/graphics/tetris_banner.png
mpremote cp user_apps/tetris_tag/tetris_tag.py :apps/tetris_tag.py
mpremote reset
```

Then select "Tetris Tag" from the menu.

If you installed this app under its earlier name, Tetris Nametag, remove the old file
first or the badge will list both: `mpremote rm :apps/tetris_nametag.py`.

Alternatively, `python scripts/update.py push` from `firmware/` brings the whole badge up
to date, but it deletes anything on the badge that is not in `firmware/badge/`,
including this app, so copy the app again afterwards.
