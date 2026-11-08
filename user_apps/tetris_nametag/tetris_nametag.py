"""Tetris Nametag. Tetris-like pieces fall and stack up to spell a name along the
bottom edge of the screen, the name blinks, then the next name is built.

User A: skip to the next name
User B: restart the current name

Edit NAMES and the settings below to make it your own.

A full e-paper refresh takes many seconds, so the animation is a series of
snapshots, one per refresh, not smooth motion. Each snapshot shows the pieces
that have landed (black) and the next few pieces still in the air (red).
"""

import random
import time

from apps.base_app import BaseApp
from lib.button import UserA, UserB
from lib.epd import display, display_width, display_height
from lib.led_bar import leds

NAMES = ("Nik Pashenkov", "Faberrgen")
"""Shown in turn, forever. Letters, space, and the characters in FONT below."""

TARGET_FRAMES = 8
"""Roughly how many e-paper refreshes it takes to build one name.
More frames is smoother, but each one costs a full refresh."""

MAX_CELL = 16
"""Largest block size in pixels. Names are scaled down to fit the width."""

BOTTOM_MARGIN = 8
"""Pixels left clear under the letters."""

BLINK_MODE = "leds"
"""'leds':   the finished name stays on the paper and the LED bar blinks.
This is the only way to get a real half-second on/off, since the paper cannot
refresh that quickly.
'screen': blink the paper itself, name -> blank -> name. Each step waits for a
full refresh to finish, so it is slow and flashes the whole panel."""

BLINK_COUNT = 3
BLINK_MS = 500
BLINK_COLOR = (20, 20, 20)
"""LED brightness is 0-255 and they are bright. Keep it low."""

FLIGHT_MIN_ROWS = 2
"""Pieces in the air are drawn at least this many rows above their landing spot."""

SPLIT_ATTEMPTS = 40
"""Random tries at cutting each letter into pieces. Fewer pieces is better."""

GLYPH_ROWS = 7

FONT = {
    " ": ("...",) * GLYPH_ROWS,
    "N": ("X...X", "XX..X", "XX..X", "X.X.X", "X..XX", "X..XX", "X...X"),
    "F": ("XXXXX", "X....", "XXXX.", "X....", "X....", "X....", "X...."),
    "P": ("XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."),
    "a": (".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX"),
    "b": ("X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX."),
    "e": (".....", ".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXXX"),
    # No descender, so every letter sits on the same floor.
    "g": (".....", ".....", ".XXXX", "X...X", ".XXXX", "....X", ".XXX."),
    "h": ("X....", "X....", "X.XX.", "XX..X", "X...X", "X...X", "X...X"),
    "i": (".X.", "...", "XX.", ".X.", ".X.", ".X.", "XXX"),
    "k": ("X....", "X....", "X..X.", "X.X..", "XX...", "X.X..", "X..X."),
    "n": (".....", ".....", "X.XX.", "XX..X", "X...X", "X...X", "X...X"),
    "o": (".....", ".....", ".XXX.", "X...X", "X...X", "X...X", ".XXX."),
    "r": (".....", ".....", "X.XX.", "XX..X", "X....", "X....", "X...."),
    "s": (".....", ".....", ".XXXX", "X....", ".XXX.", "....X", "XXXX."),
    "v": (".....", ".....", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
}

_BUILD = 0
_BLINK = 1


def _neighbors(c):
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _text_cells(text):
    """The cells (x, y) of each letter on a grid GLYPH_ROWS tall, and the text width."""
    glyphs = []
    x = 0
    for ch in text:
        rows = FONT[ch]
        cells = []
        for y in range(GLYPH_ROWS):
            for gx, mark in enumerate(rows[y]):
                if mark == "X":
                    cells.append((x + gx, y))
        if cells:
            glyphs.append(cells)
        x += len(rows[0]) + 1
    return glyphs, x - 1


def _greedy_split(cells):
    """Cut cells into connected pieces of up to four, hardest-to-fill cells first."""
    free = set(cells)
    pieces = []
    while free:
        best = None
        best_n = 5
        for c in free:
            n = sum(1 for nb in _neighbors(c) if nb in free)
            if n < best_n or (n == best_n and random.randrange(2)):
                best, best_n = c, n
        piece = [best]
        free.discard(best)
        while len(piece) < 4:
            options = []
            for pc in piece:
                for nb in _neighbors(pc):
                    if nb in free and nb not in options:
                        options.append(nb)
            if not options:
                break
            nxt = random.choice(options)
            piece.append(nxt)
            free.discard(nxt)
        pieces.append(piece)
    return pieces


def _land_order(pieces):
    """What has to land before what, so every piece can fall straight down.
    Returns a list of sets, [i] being the pieces that must land before piece i,
    or None if the pieces block each other."""
    columns = {}
    for i, piece in enumerate(pieces):
        for x, y in piece:
            columns.setdefault(x, []).append((y, i))
    before = [set() for _ in pieces]
    for col in columns.values():
        for y_a, a in col:
            for y_b, b in col:
                if a != b and y_a > y_b:
                    # b is above a in this column, so a lands first.
                    before[b].add(a)
    # Cycle check: peel off pieces whose requirements are all met.
    done = set()
    while len(done) < len(pieces):
        ready = [i for i in range(len(pieces)) if i not in done and before[i] <= done]
        if not ready:
            return None
        done.update(ready)
    return before


def _split_glyph(cells):
    best = None
    for _ in range(SPLIT_ATTEMPTS):
        pieces = _greedy_split(cells)
        if best is not None and len(pieces) >= len(best[0]):
            continue
        before = _land_order(pieces)
        if before is not None:
            best = (pieces, before)
    if best is None:
        # Single blocks can always be stacked bottom-up.
        pieces = [[c] for c in cells]
        best = (pieces, _land_order(pieces))
    return best


class _Plan:
    """A name cut into pieces, with the pixel layout to draw it."""

    def __init__(self, text):
        glyphs, cols = _text_cells(text)
        self.cell = max(2, min(MAX_CELL, display_width // (cols + 2)))
        self.gap = max(1, self.cell // 8)
        self.x0 = (display_width - cols * self.cell) // 2
        self.field_rows = (display_height - BOTTOM_MARGIN) // self.cell
        self.y_grid = self.field_rows - GLYPH_ROWS
        self.pieces = []
        self.before = []
        for cells in glyphs:
            pieces, before = _split_glyph(cells)
            base = len(self.pieces)
            for piece in pieces:
                self.pieces.append([(x, y + self.y_grid) for x, y in piece])
            for req in before:
                self.before.append(set(base + r for r in req))

    def land_sequence(self):
        """A random order the pieces could land in."""
        done = set()
        order = []
        while len(order) < len(self.pieces):
            ready = [i for i in range(len(self.pieces))
                     if i not in done and self.before[i] <= done]
            pick = random.choice(ready)
            done.add(pick)
            order.append(pick)
        return order

    def draw_piece(self, plane, cells, rows_up=0):
        size = self.cell - self.gap
        for x, y in cells:
            plane.fill_rect(self.x0 + x * self.cell,
                            (y - rows_up) * self.cell, size, size, 1)

    def flight_heights(self, batch):
        """How far above its landing spot each piece in the air is drawn."""
        taken = set()
        heights = {}
        for i in batch:
            top = min(y for _, y in self.pieces[i])
            start = random.randint(min(FLIGHT_MIN_ROWS, top), top)
            # Nudge up to clear other pieces in the air, or down if out of room.
            up = start
            for cand in list(range(start, top + 1)) + list(range(start - 1, 0, -1)):
                if not any((x, y - cand) in taken for x, y in self.pieces[i]):
                    up = cand
                    break
            for x, y in self.pieces[i]:
                taken.add((x, y - up))
            heights[i] = up
        return heights


class TetrisNametagApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Tetris Name"
        self.sleep_ms = 25
        self.launched = False
        self.plans = {}
        self.word = 0
        self.state = _BUILD
        self.plan = None
        self.order = []
        self.batch_size = 1
        self.frame = 0
        self.frames = 0
        self.blink_step = 0
        self.blink_ms = 0
        self.frame_ms = 0

    def _start_word(self, idx):
        self.word = idx % len(NAMES)
        plan = self.plans.get(self.word)
        if plan is None:
            plan = self.plans[self.word] = _Plan(NAMES[self.word])
        self.plan = plan
        self.order = plan.land_sequence()
        count = len(self.order)
        self.batch_size = max(1, (count + TARGET_FRAMES - 1) // TARGET_FRAMES)
        # One snapshot per batch in the air, then one with everything landed.
        self.frames = (count + self.batch_size - 1) // self.batch_size + 1
        self.frame = 0
        self.state = _BUILD
        print(f"{NAMES[self.word]}: {count} pieces, {self.frames} frames, cell {plan.cell}px")

    def _show(self, landed, in_air=()):
        """Queue a snapshot: landed pieces in black, pieces in the air in red."""
        plan = self.plan
        display.clear()
        for i in landed:
            plan.draw_piece(display.black, plan.pieces[i])
        heights = plan.flight_heights(in_air)
        for i in in_air:
            plan.draw_piece(display.red, plan.pieces[i], heights[i])
        display.update()
        self.frame_ms = time.ticks_ms()

    def _show_frame(self):
        landed = self.order[:self.frame * self.batch_size]
        in_air = self.order[len(landed):len(landed) + self.batch_size]
        self._show(landed, in_air)
        self.frame += 1

    def _start_blink(self):
        self.state = _BLINK
        self.blink_step = 0
        self.blink_ms = time.ticks_ms()
        if BLINK_MODE == "leds":
            leds.fill(BLINK_COLOR)

    def _blink_leds(self):
        if time.ticks_diff(time.ticks_ms(), self.blink_ms) < BLINK_MS:
            return
        self.blink_ms = time.ticks_add(self.blink_ms, BLINK_MS)
        self.blink_step += 1
        if self.blink_step >= 2 * BLINK_COUNT:
            leds.fill((0, 0, 0))
            self._start_word(self.word + 1)
        else:
            leds.fill(BLINK_COLOR if self.blink_step % 2 == 0 else (0, 0, 0))

    def _blink_screen(self):
        # The name is up. Alternate blank and name, once per finished refresh.
        if self.blink_step >= 2 * BLINK_COUNT:
            self._start_word(self.word + 1)
        elif self.blink_step % 2 == 0:
            self._show([])
            self.blink_step += 1
        else:
            self._show(self.order)
            self.blink_step += 1

    def run(self):
        if self.launched:
            leds.fill((0, 0, 0))
            self._start_word(0)
            return

        if UserA.pressed():
            leds.fill((0, 0, 0))
            self._start_word(self.word + 1)
        elif UserB.pressed():
            leds.fill((0, 0, 0))
            self._start_word(self.word)

        # A refresh in progress owns the LEDs and the framebuffers.
        if not display.is_done_updating():
            return

        if self.state == _BUILD:
            if self.frame_ms:
                print("refresh ms:", time.ticks_diff(time.ticks_ms(), self.frame_ms))
                self.frame_ms = 0
            if self.frame < self.frames:
                self._show_frame()
            else:
                self._start_blink()
        elif BLINK_MODE == "leds":
            self._blink_leds()
        else:
            self._blink_screen()
