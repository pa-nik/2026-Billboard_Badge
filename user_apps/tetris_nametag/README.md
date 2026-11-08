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

It is black and white only while falling (the fast waveform cannot make red). If
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
Badges that shipped with older firmware are missing `epd_grayscale.py`,
`rendered_luts.py` and an updated `large_png.py`, which the fast refresh and the
new `epd.py` rely on. Run these from the repo root (`mpremote ls :lib :data` shows
what is on the badge):

```
mpremote cp firmware/badge/lib/epd.py :lib/epd.py
mpremote cp firmware/badge/lib/epd_fast.py :lib/epd_fast.py
mpremote cp firmware/badge/lib/epd_grayscale.py :lib/epd_grayscale.py
mpremote cp firmware/badge/lib/large_png.py :lib/large_png.py
mpremote cp firmware/badge/data/rendered_luts.py :data/rendered_luts.py
mpremote cp user_apps/tetris_nametag/tetris_nametag.py :apps/tetris_nametag.py
mpremote reset
```

Then select "Tetris Name" from the menu.

Alternatively, `python scripts/update.py push` from `firmware/` brings the whole badge up
to date, but it deletes anything on the badge that is not in `firmware/badge/`,
including this app, so copy the app again afterwards.
