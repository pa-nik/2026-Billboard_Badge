# Tetris Nametag

Tetris-like pieces fall and stack up to spell a name along the bottom edge of
the screen. The name blinks three times, then the next name is built, and it
loops forever.

Pieces already landed are black; the next few still in the air are red.

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
* `TARGET_FRAMES`: how many e-paper refreshes it takes to build one name.
* `BLINK_MODE`, `BLINK_COUNT`, `BLINK_MS`: see below.

## Why it is not smooth

A full refresh of this e-paper panel takes many seconds and flashes the whole
screen, so the animation is a slideshow: one refresh per snapshot of the stack.
The app prints `refresh ms:` over serial so you can see the real time on your
badge, and sets the pace itself: it queues the next snapshot only when the last
refresh has finished.

The same limit applies to blinking. `BLINK_MODE = "leds"` (the default) keeps the
finished name on the paper and blinks the LED bar, half a second on and half a
second off, three times. `BLINK_MODE = "screen"` blinks the paper itself (name,
blank, name...), but each step takes a full refresh, so it is slow.

The "clear screen" between names is the first snapshot of the next name, which
is an empty field with a few pieces in the air, so it doesn't spend a refresh on
a blank page.

## Install

```
mpremote cp tetris_nametag.py :apps/
```

Then restart the badge and select "Tetris Name".
