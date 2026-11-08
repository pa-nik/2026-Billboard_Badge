"""Tetris Tag. Tetris-like pieces fall and stack up to spell a name along the
bottom edge of the screen, the name blinks, then it is built again (or the next
name, if NAMES lists more than one).

User A: skip to the next name (restarts it when NAMES has just one)
User B: restart the current name

A red banner with white Helvetica Bold lettering runs across the top of the screen.
The lettering is an image made on a computer by make_banner.py. Edit NAMES and the
settings below to make it your own.

The panel's own refresh takes about 30 s, far too slow to animate. On B1 panels
with current firmware (display.supports_fast) the pieces fall one at a time, like the
real game, in a few partial refreshes each (see lib/epd_fast.py): the screen is cleared
with one full refresh, then only the pixels that change are redrawn. A piece appears at
25% of the screen height turned a random quarter turn, turns 90 degrees per
refresh until it is the right way up, then drops into place. (An LED bar fill that
follows the fall is built in but switched off, see FILL_ENABLED.) Elsewhere it falls
back to a slideshow, one full refresh per snapshot, showing the pieces landed (black)
and the next few still in the air (red).
"""

import random
import time

from apps.base_app import BaseApp
from lib.button import UserA, UserB
from lib.epd import display, display_width, display_height
from lib.led_bar import NUM_LEDS, leds

NAMES = ("YOUR NAME",)
"""Shown in turn, forever. Replace "YOUR NAME" with your own, using only the characters
in FONT below (capitals A E F H I K M N O P R S U V Y, some lowercase, and space), or
add more names to the tuple to cycle through them. Other letters need a 5 x 7 glyph."""

BANNER_IMAGE = "/data/graphics/tetris_banner.png"
"""White lettering on red, 960 px wide, made on a computer by make_banner.py and
copied to the badge (the badge has no Helvetica, and its built-in font has neither
Cyrillic nor the hammer and sickle). If the file is missing, the banner is a plain
red band."""

BANNER_PCT = 25
"""Banner height as a percent of the screen height. 0 for no banner. Must match the
image (make_banner.py --pct). The banner is red, so it is drawn by the full refresh
at the start of each name, and the fast partial refreshes hold it untouched."""

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

FAST = True
"""Use partial refreshes where the panel and firmware support them. False forces
the slideshow."""

PIECES_AT_ONCE = 1
"""Pieces falling at the same time. 1 is like the real game: one piece falls, turns
and lands, then the next. Higher is much faster, because a refresh then moves several
pieces at once (9 is about seven times faster), but pieces fall in crowds. A piece only
joins a wave if it cannot land on another piece in the air."""

FILL_ENABLED = False
"""The LED bar filling while a piece falls. Off on this branch for now; the finished-name
blink (BLINK_MODE) is separate and still runs."""

FILL_COLOR = (20, 20, 20)
"""Colour the LEDs fill with while a piece falls. They are bright, so keep it low."""

FILL_HOLD_MS = 400
"""How long every LED stays lit after a piece lands, before they empty for the next."""

FILL_REVERSE = False
"""Fill from the other end, if the LED bar fills right to left on your badge."""

SPAWN_PCT = 25
"""Every piece appears at this percent of the screen height, measured from the top.
25 is the bottom edge of the banner. It is never put inside the banner."""

ROTATE_DROP_ROWS = 3
"""Rows a piece drops during each 90 degree turn on its way down. Once it is turned
the right way up it falls the rest of the way into place in one refresh."""

HOP_PULLS = 1
"""Drive steps (about 1.1 s each) for frames while a piece is moving. 1 is
quickest but pale. Raise to 2 or 3 if falling pieces are too faint to see."""

SETTLE_PULLS = 3
"""Drive steps for the frame where a piece lands. 3 is solid black."""

BLINK_PULLS = 3
"""Drive steps for each flash when BLINK_MODE is 'screen' and fast refresh is on."""

FLIGHT_MIN_ROWS = 2
"""Slideshow only: pieces in the air are drawn at least this many rows above
their landing spot."""

SPLIT_ATTEMPTS = 40
"""Random tries at cutting each letter into pieces. Fewer pieces is better."""

GLYPH_ROWS = 7

FONT = {
    " ": ("...",) * GLYPH_ROWS,
    "A": (".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "E": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"),
    "F": ("XXXXX", "X....", "XXXX.", "X....", "X....", "X....", "X...."),
    "H": ("X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "I": ("XXX", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"),
    "K": ("X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"),
    "M": ("X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"),
    "N": ("X.....X", "XX....X", "XX....X", "X..X..X", "X....XX", "X....XX", "X.....X"),
    "O": (".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "P": ("XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."),
    "R": ("XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"),
    "S": (".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."),
    "U": ("X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "V": ("X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "Y": ("X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."),
    "a": (".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX"),
    "b": ("X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX."),
    "e": (".....", ".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXXX"),
    # Acute accent in the two rows above the x-height.
    "é": ("...X.", "..X..", ".XXX.", "X...X", "XXXXX", "X....", ".XXXX"),
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

# Rough time of one partial refresh, used only to pace the LED fill: about 1.17 s a
# drive step plus the data transfer. Measured on a badge; the real times print as
# "refresh ms:".
_PULL_MS = 1170
_FRAME_MS = 220

_BUILD = 0
_BLINK = 1
_CLEAR = 2
_DROP = 3


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
    return _absorb_singles(pieces)


def _connected(cells):
    """True if the cells touch edge to edge as one group."""
    rest = set(cells)
    stack = [rest.pop()]
    while stack:
        for nb in _neighbors(stack.pop()):
            if nb in rest:
                rest.discard(nb)
                stack.append(nb)
    return not rest


def _absorb_singles(pieces):
    """Fold lone cells into a neighbouring piece: join one that has room, or take a cell
    off a bigger one that stays whole without it. A cell touching no other cell by an edge
    (a diagonal stroke) stays alone, since no piece can hold it."""
    changed = True
    while changed:
        changed = False
        for single in [p for p in pieces if len(p) == 1]:
            cell = single[0]
            for nb in _neighbors(cell):
                other = None
                for q in pieces:
                    if nb in q and q is not single:
                        other = q
                        break
                if other is None:
                    continue
                if len(other) < 4:
                    other.append(cell)
                    pieces.remove(single)
                elif len(other) > 2 and _connected([c for c in other if c != nb]):
                    other.remove(nb)
                    single.append(nb)
                else:
                    continue
                changed = True
                break
            if changed:
                break
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
    best_score = None
    for _ in range(SPLIT_ATTEMPTS):
        pieces = _greedy_split(cells)
        # Fewest single blocks first, then fewest pieces.
        score = (sum(1 for p in pieces if len(p) == 1), len(pieces))
        if best is not None and score >= best_score:
            continue
        before = _land_order(pieces)
        if before is not None:
            best = (pieces, before)
            best_score = score
    if best is None:
        # Single blocks can always be stacked bottom-up.
        pieces = [[c] for c in cells]
        best = (pieces, _land_order(pieces))
    return best


def _turn(shape):
    """A list of (x, y) cells turned a quarter turn clockwise, moved back to the origin."""
    turned = [(-y, x) for x, y in shape]
    left = min(x for x, _ in turned)
    top = min(y for _, y in turned)
    return sorted((x - left, y - top) for x, y in turned)


def _clash(a, b):
    """Do two falls ever put a block on the same cell in the same frame? A fall
    that has landed stays where it is for the rest of the wave."""
    for frame in range(max(len(a), len(b))):
        if set(a[min(frame, len(a) - 1)]) & set(b[min(frame, len(b) - 1)]):
            return True
    return False


def _fall_pulls(frame, landing):
    """Drive steps for frame `frame` of a fall whose landing frame is `landing`."""
    return SETTLE_PULLS if frame == landing else HOP_PULLS


class _Banner:
    """A red band across the top, with the lettering image drawn over it."""

    def __init__(self):
        self.height = display_height * BANNER_PCT // 100

    def draw(self):
        """Red band in the red plane, then the white lettering on top of it. If the
        image cannot be drawn the band stays plain red."""
        if not self.height:
            return
        display.red.fill_rect(0, 0, display_width, self.height, 1)
        try:
            display.draw_png(BANNER_IMAGE, 0, 0)
        except Exception as ex:  # missing file, not a palette PNG, ...
            print("Banner image not drawn:", ex)


class _Plan:
    """A name cut into pieces, with the pixel layout to draw it."""

    def __init__(self, text):
        glyphs, cols = _text_cells(text)
        self.cell = max(2, min(MAX_CELL, display_width // (cols + 2)))
        self.gap = max(1, self.cell // 8)
        self.x0 = (display_width - cols * self.cell) // 2
        self.field_rows = (display_height - BOTTOM_MARGIN) // self.cell
        self.y_grid = self.field_rows - GLYPH_ROWS
        # First grid row below the banner; pieces in the air stay under it.
        self.top_row = (display_height * BANNER_PCT // 100 + self.cell - 1) // self.cell
        # Row where every piece appears, and how far sideways a turned piece may reach.
        self.spawn_row = max(self.top_row,
                             (display_height * SPAWN_PCT // 100 + self.cell - 1) // self.cell)
        self.min_x = -(self.x0 // self.cell)
        self.max_x = (display_width - self.x0) // self.cell
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

    def make_fall(self, i):
        """Where piece i is drawn in each frame of its fall, as a list of cell lists.

        It appears at the spawn height turned a random quarter turn, then turns 90
        degrees per frame (the shorter way round, dropping ROTATE_DROP_ROWS each time)
        until its shape matches its final orientation. The last entry is where it
        lands, so the frame after it is turned the right way up it drops into place. A
        piece that looks the same turned, like a square, needs fewer turns or none."""
        cells = self.pieces[i]
        left = min(x for x, _ in cells)
        top = min(y for _, y in cells)
        final = sorted((x - left, y - top) for x, y in cells)
        width = max(x for x, _ in final) + 1
        shapes = [final]  # shapes[n]: the final shape turned n quarter turns clockwise
        for _ in range(3):
            shapes.append(_turn(shapes[-1]))
        turns = random.randint(1, 3)
        step = 1 if turns == 3 else (-1 if turns == 1 else random.choice((1, -1)))
        path = [turns]
        while shapes[path[-1]] != final:
            path.append((path[-1] + step) % 4)
        frames = []
        for n, turned in enumerate(path):
            shape = shapes[turned]
            w = max(x for x, _ in shape) + 1
            x = max(self.min_x, min(left + (width - w) // 2, self.max_x - w))
            y = min(self.spawn_row + ROTATE_DROP_ROWS * n, top)
            frames.append([(x + sx, y + sy) for sx, sy in shape])
        frames.append(list(cells))
        return frames

    def land_waves(self, at_most):
        """The pieces grouped into waves that fall together, each a list of
        (piece, frames). A wave only takes pieces whose supports have already landed,
        so none waits on another, and a piece joins only if it never lands on one
        already in the wave, in any frame."""
        done = set()
        waves = []
        while len(done) < len(self.pieces):
            ready = [i for i in range(len(self.pieces))
                     if i not in done and self.before[i] <= done]
            wave = []
            while ready and len(wave) < at_most:
                pick = random.choice(ready)
                ready.remove(pick)
                frames = self.make_fall(pick)
                if any(_clash(frames, other) for _, other in wave):
                    continue
                wave.append((pick, frames))
            done.update(i for i, _ in wave)
            waves.append(wave)
        return waves

    def draw_cells(self, plane, cells):
        size = self.cell - self.gap
        for x, y in cells:
            plane.fill_rect(self.x0 + x * self.cell, y * self.cell, size, size, 1)

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
            top = min(y for _, y in self.pieces[i]) - self.top_row
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


class TetrisTagApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Tetris Tag"
        self.sleep_ms = 25
        self.launched = False
        self.plans = {}
        self.word = 0
        self.state = _BUILD
        self.fast = False
        self.plan = None
        self.banner = None
        self.screen_ready = False
        self.order = []
        self.batch_size = 1
        self.frame = 0
        self.frames = 0
        self.waves = []
        self.batch = 0
        self.landed = []
        self.blink_step = 0
        self.blink_ms = 0
        self.frame_ms = 0
        self.led_n = -1  # LEDs lit now; -1 means unknown, so the next write goes out
        self.led_ramp = None  # (start ms, duration ms, from, to) of the fill in progress
        self.led_last = False  # the frame in progress is the one that lands the piece
        self.led_hold = None  # ticks_ms until which the full bar stays lit, if any

    def _start_word(self, idx):
        self.word = idx % len(NAMES)
        plan = self.plans.get(self.word)
        if plan is None:
            plan = self.plans[self.word] = _Plan(NAMES[self.word])
        self.plan = plan
        if self.banner is None:
            self.banner = _Banner()
        self.screen_ready = False  # the next frame starts from a full clear and banner
        self.led_n, self.led_ramp, self.led_last = -1, None, False
        self.fast = FAST and getattr(display, "supports_fast", False)
        self.frame_ms = 0
        if self.fast:
            self.waves = plan.land_waves(max(1, PIECES_AT_ONCE))
            self.order = [i for wave in self.waves for i, _ in wave]
            self.batch = 0
            self.frame = 0
            self.landed = []
            self.state = _CLEAR
            refreshes = sum(max(len(frames) for _, frames in wave)
                            for wave in self.waves)
            print(f"{NAMES[self.word]}: {len(self.order)} pieces in {len(self.waves)} waves, "
                  f"{refreshes} partial refreshes, cell {plan.cell}px")
            return
        self.order = plan.land_sequence()
        count = len(self.order)
        self.batch_size = max(1, (count + TARGET_FRAMES - 1) // TARGET_FRAMES)
        # One snapshot per batch in the air, then one with everything landed.
        self.frames = (count + self.batch_size - 1) // self.batch_size + 1
        self.frame = 0
        self.state = _BUILD
        print(f"{NAMES[self.word]}: {count} pieces, {self.frames} frames, cell {plan.cell}px")

    def _new_frame(self):
        """Blank canvas for the next frame. The banner is drawn once per name and then
        left where it is: redrawing it would decode the image for every frame."""
        if not self.screen_ready:
            display.clear()
            self.banner.draw()
            self.screen_ready = True
            return
        top = self.banner.height
        display.black.fill_rect(0, top, display_width, display_height - top, 0)
        display.red.fill_rect(0, top, display_width, display_height - top, 0)

    def _show(self, landed, in_air=()):
        """Slideshow: queue a snapshot, landed pieces in black, in the air in red."""
        plan = self.plan
        self._new_frame()
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

    def _show_fast(self, moving, pulls):
        """Partial refresh: landed pieces and the ones in the air, all in
        black. moving is a list of cell lists, one per piece in the air."""
        plan = self.plan
        self._new_frame()
        for i in self.landed:
            plan.draw_piece(display.black, plan.pieces[i])
        for cells in moving:
            plan.draw_cells(display.black, cells)
        display.update(fast=True, pulls=pulls)
        self.frame_ms = time.ticks_ms()

    def _set_leds(self, n):
        """Light the first n LEDs (the last n with FILL_REVERSE), the rest off."""
        n = max(0, min(NUM_LEDS, n))
        if n == self.led_n:
            return
        self.led_n = n
        for i in range(NUM_LEDS):
            on = i >= NUM_LEDS - n if FILL_REVERSE else i < n
            leds[i] = FILL_COLOR if on else (0, 0, 0)
        leds.write()

    def _start_fill(self, frame, last):
        """As frame `frame` of a fall (the landing frame is `last`) is queued, start the
        LEDs filling, paced to the time the whole fall takes so the bar is full just as
        the piece lands. The bar from the last piece stays lit for FILL_HOLD_MS first."""
        if not FILL_ENABLED:
            return
        spans = [_fall_pulls(k, last) * _PULL_MS + _FRAME_MS for k in range(last + 1)]
        total = sum(spans)
        now = time.ticks_ms()
        start = now
        if frame == 0 and self.led_hold is not None and time.ticks_diff(self.led_hold, now) > 0:
            start = self.led_hold
        length = spans[frame] - time.ticks_diff(start, now)
        self.led_ramp = (start, max(1, length),
                         NUM_LEDS * sum(spans[:frame]) / total,
                         NUM_LEDS * sum(spans[:frame + 1]) / total)
        self.led_last = frame == last

    def _tick_leds(self):
        """Move the fill along. Never shows a full bar before the piece has landed."""
        if self.led_ramp is None:
            return
        start, length, a, b = self.led_ramp
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        if elapsed < 0:
            return  # still holding the full bar from the last piece
        level = a + (b - a) * min(1.0, elapsed / length)
        self._set_leds(min(int(level), NUM_LEDS - 1))

    def _drop_frame(self):
        """One partial refresh of the current wave: the pieces appear at the spawn
        height turned a random way, turn 90 degrees a frame until they are the right
        way up, then drop into place."""
        wave = self.waves[self.batch]
        landing = max(len(frames) for _, frames in wave) - 1  # last refresh of the fall
        moving = [frames[min(self.frame, len(frames) - 1)] for _, frames in wave]
        self._show_fast(moving, _fall_pulls(self.frame, landing))
        self._start_fill(self.frame, landing)
        if self.frame == landing:
            self.landed.extend(i for i, _ in wave)
            self.batch += 1
            self.frame = 0
        else:
            self.frame += 1

    def _start_blink(self):
        self.state = _BLINK
        self.blink_step = 0
        self.blink_ms = time.ticks_ms()
        self.led_n, self.led_ramp, self.led_last = -1, None, False
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
            return
        shown = self.order if self.blink_step % 2 else []
        if self.fast and not display.supports_fast:
            self.fast = False
        if self.fast:
            self.landed = shown
            self._show_fast([], BLINK_PULLS)
        else:
            self._show(shown)
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

        # Fast refreshes leave the LEDs alone, so the fill can carry on while one runs.
        if self.state == _DROP:
            self._tick_leds()

        # A refresh in progress owns the framebuffers.
        if not display.is_done_updating():
            return

        if self.led_last and FILL_ENABLED:
            # The piece has landed: every LED lit, held briefly before the next piece.
            self.led_last = False
            self.led_ramp = None
            self._set_leds(NUM_LEDS)
            self.led_hold = time.ticks_add(time.ticks_ms(), FILL_HOLD_MS)

        if self.frame_ms:
            print("refresh ms:", time.ticks_diff(time.ticks_ms(), self.frame_ms))
            self.frame_ms = 0

        if self.state == _CLEAR:
            # The one full refresh per name: wipes the last name and any ghosts,
            # and draws the red banner, which the fast frames then hold.
            self.screen_ready = False
            self._new_frame()
            display.update()
            self.frame_ms = time.ticks_ms()
            self.state = _DROP
        elif self.state == _DROP:
            if not display.supports_fast:
                # The driver gave up on fast refresh after repeated failures.
                print("Fast refresh stopped working, using the slideshow")
                self._start_word(self.word)
            elif self.batch < len(self.waves):
                self._drop_frame()
            else:
                self._start_blink()
        elif self.state == _BUILD:
            if self.frame < self.frames:
                self._show_frame()
            else:
                self._start_blink()
        elif BLINK_MODE == "leds":
            self._blink_leds()
        else:
            self._blink_screen()
