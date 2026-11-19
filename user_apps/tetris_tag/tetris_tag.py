"""Tetris Tag. Tetris-like pieces fall and stack up to spell a name along the
bottom edge of the screen and the LEDs blink when the name is done; then the animation stops and
the ESP32 sleeps until the wake-up button (User A) is pressed (SLEEP_WHEN_DONE). A black cat walks in from the
side at the start of each round and sits just below the banner; one piece at a time falls out
of its rear, and after each the cat walks over to where the next one goes and sits down
there before it falls.

User A: select the next name of the list in the left score panel (the round starts again,
        with the cat building it)
User B: turn the falling piece 90 degrees clockwise (one piece falls at a time)
When the name is done and the badge sleeps, the wake-up button (User A) wakes it and the next name starts.
(with NAME_MENU = False: two pieces fall, A turns the left one and B the right one, and
between names A skips to the next name and B restarts the current one)

A red banner with white Helvetica Bold lettering ("🐾 BARTRIS 🐾") and the two players' score
boards runs across the top of the screen. There is no footer on this branch.
The lettering is an image made on a computer by make_banner.py. Edit NAMES and the
settings below to make it your own.

The panel's own refresh takes about 30 s, far too slow to animate. On B1 panels with
lib/epd_partial.py (about 0.65 s a frame) the pieces fall in partial refreshes (two at a
time, like a two-player Tetris, when CAT is False): the screen is cleared with one full refresh that also draws
the red bands, then only the pixels that change are redrawn. A piece appears
turned a random quarter turn (just below the cat, or at 25% of the screen height) and falls
without turning; each press turns it 90 degrees clockwise.
Once a piece is the right way up it drops into place on the next refresh. A piece
nobody has turned starts turning itself when it reaches 50% of the screen height.
Elsewhere the app falls back to a slideshow, one full refresh per snapshot, showing
the pieces landed (black) and the next few still in the air (red).
"""

import asyncio as aio
import framebuf
import gc
import math
import random
import sys
import time

from apps.base_app import BaseApp
from lib.button import UserA, UserB
try:
    from lib import button as _button_module
    _PINS = {"A": _button_module.USER_A_PIN, "B": _button_module.USER_B_PIN}
except (ImportError, AttributeError):
    _PINS = {"A": 39, "B": 16}  # the badge's User A and User B buttons
from lib.epd import display, display_width, display_height
from lib.led_bar import leds

try:  # the partial refresh driver; without it the app falls back to the slideshow
    from lib import epd_partial as _ep
except ImportError:
    _ep = None

NAMES = ("IRINA", "SONYA", "FELIX")
"""The names to build. With NAME_MENU (below) the first three are listed in the left score
panel and User A picks one; without it they are shown in turn, forever. Use only the
characters in FONT below (the letters A to Z and a to z, é, and space). Punctuation needs a
5 x 7 glyph of its own."""

NAME_MENU = True
"""List the names in NAMES (the first three) in the left score panel, the one for User A, in
place of its score, and use the buttons differently: User A selects the next name (the round
starts again with the cat building that name) and User B turns the falling piece. One piece
falls at a time, all the points go to the right panel (User B's), and the same name is built
again after each hold instead of moving on to the next. The selected name is white, the others
black. The right panel shows SCORE and NEXT (no LINES). False: two score panels with SCORE,
LINES and NEXT, and the buttons turn the pieces, as in the other versions."""

BANNER_IMAGE = "/data/graphics/tetris_banner.png"
"""White lettering on red, 960 px wide, made on a computer by make_banner.py and
copied to the badge (the badge has no Helvetica, and its built-in font has neither
Cyrillic nor the hammer and sickle). The lettering sits in the middle, low in the band,
between and under the score boards (see SCOREBOARD):
    python3 make_banner.py --pct 25 --margin 190 --height-fraction 0.42 --drop 18
If the file is missing, the banner is a plain red band."""

BANNER_PCT = 25
"""Banner height as a percent of the screen height. 0 for no banner. Must match the
image (make_banner.py --pct). The banner is red, so it is drawn by the one full refresh
when the app is launched, and the partial refreshes leave it untouched."""

TARGET_FRAMES = 8
"""Roughly how many e-paper refreshes it takes to build one name.
More frames is smoother, but each one costs a full refresh."""

MAX_CELL = 20
"""Largest block size in pixels (20 is 25% more than 16). Names are scaled down to fit the width."""

BOTTOM_MARGIN = 72
"""Pixels left clear between the letters and the footer band (or the bottom of the
screen, with no footer). 72 with no footer: the name sits 15% of the screen height (about 100 px)
lower than it did above the 168 px footer; the larger blocks need this room."""

NAME_RISE_PCT = 0
"""How far the name is lifted above that position, as a percent of the screen height (6.55
is 44 px). The pieces then have that much less to fall. 0 here: the cat sits high and the
pieces start below it, so the name stays low to leave them room to fall."""

FOOTER_PCT = 0
"""Height of the red footer band across the bottom, as a percent of the screen height.
It is drawn by the one full refresh when the app is launched and stays on the screen all
the time; the name lands right above it. 0 for no footer (none on this branch)."""

FOOTER_IMAGE = "/data/graphics/faberrgen_footer.png"
"""White lettering on red, 960 px wide, made by make_faberrgen.py (it is the same band as
on the Faberrgen screen of the main branch). For your own text make one with make_banner.py, e.g.
    python3 make_banner.py --text "web / @socials" --pct 25 --size 78 --out tetris_footer.png
(78 px is the top banner's lettering size) and point FOOTER_IMAGE at it. If the file is
missing the footer is a plain red band."""

SCOREBOARD = True
"""Show a score board for each player at the two ends of the top banner (SCORE, LINES, the
NEXT piece and which button, User A on the left and User B on the right). Needs the banner to be the full 25%. A letter finished is a line; 10 points
for a piece landed, 10 more if the player turned it right way up before it started turning
itself, 100 for the piece that finishes a letter. The panels are red with white lettering;
the numbers and the next piece are black in small white boxes, because only white and black
can be changed by a partial refresh."""

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

HOLD_S = 30
"""Seconds the finished name stays on the screen, after the blinking, before the next
round starts. User A skips the wait to the next name, User B restarts this one."""

CAT = True
"""A black pixel-art cat walks in from the nearer side of the screen at the start of each round
and sits just below the banner, and one piece at a time falls out of its rear. After each
piece lands the cat walks over to where the next one goes, sits down there, and then that
piece falls. Needs the partial refresh (on the slideshow fallback there is no cat). With the
cat on, one piece falls at a time whatever PIECES_AT_ONCE says. False: no cat, the pieces
appear at SPAWN_PCT."""

CAT_SCALE = 6
"""Pixels on the screen for each pixel of the cat (4 was 1.5 times smaller)."""

CAT_STEP_PX = 72
"""How far the cat walks in each refresh (about 0.65 s), at most."""

CAT_GAP_PX = 8
"""Space between the bottom of the banner and the top of the sitting cat."""

SLEEP_WHEN_DONE = True
"""When the name is finished (the last piece has landed and the LEDs have blinked) the animation
stops, the picture stays on the paper, and the ESP32 goes to light sleep until the wake-up button
(SLEEP_WAKE_BUTTON) is pressed. It sleeps in short naps and looks at the button after each one
(SLEEP_POLL_MS), instead of waking on a pin interrupt: this firmware (MicroPython 1.24) only accepts a
pin wake-up on GPIO 0 to 21 (not User A, GPIO 39) and on the badge the pin wake-up woke the chip by
itself after a while. The e-paper is powered down first (the paper keeps its picture without power).
False: hold the name for HOLD_S seconds and build it again, forever, as before."""

SLEEP_WAKE_BUTTON = "A"
"""Which button wakes the badge: "A" (User A, GPIO 39) or "B" (User B, GPIO 16). Use "A": on the
ESP32-S3 GPIO 15 and 16 are the pins of the optional 32 kHz crystal, and on this badge User B (16)
and Menu + (15) misbehave when the chip goes to sleep: GPIO 16 chattered and then read low about
0.4 s after the sleep began, with nobody touching it, so it counted as a press."""

SLEEP_POLL_MS = 40
"""How long each nap is while it waits for the button, in ms. A button press has to last a bit
longer than this (plus 30 ms) to be seen. Shorter naps catch quicker taps and use a little more power."""

WAKE_NEXT_NAME = True
"""What the wake-up press does: True starts the next name of the list (what User A does when
the badge is awake), False the same name again (what User B does)."""

BATTERY_ICON = True
"""A phone-style battery icon in the middle of the top band: an outline with 5 segments that show
the battery's charge (read from the voltage sense on GPIO 14, a 1/2 divider on the input of the
3.3 V regulator). While USB is plugged in that pin sees the USB supply, not the battery, so
the icon then shows a lightning bolt (charging / on USB) instead of segments. Measured every
30 s. Needs SCOREBOARD."""

SAND = True
"""Sand under the name: an evenly stippled ground from just under the letters to the bottom of
the screen, with small hills and valleys along its top edge (no line: the edge of the grains).
The letters stand on it, so they overlap the hills a little. It is drawn once per round (new
dunes every round) and kept as a copy of its rows, so it costs the frames almost nothing."""

SAND_DENSITY = 28
"""How many of every 100 squares of 4 x 4 pixels get a grain (a 2 x 2 pixel black dot), the
same everywhere in the sand: 28 is about 7% of the pixels black."""

SAND_HILL_PX = 22
"""How much higher the top of a hill is than a valley, in pixels. The valleys are as low as
the bottom of the letters, the hills rise as far as the lowest row of blocks (20 px) and
a little more, so the letters seem to stand in the sand."""

FAST = True
"""Use partial refreshes (lib/epd_partial.py) where the panel and firmware support
them. False forces the slideshow."""

PIECES_AT_ONCE = 2
"""Pieces falling at the same time: 1 or 2 (always 1 with the cat or the NAME_MENU). With 2,
User A turns the left one and User B the right one (with 1, either button turns it). Two pieces only fall together if
they land in separate columns, and each stays on its own side of the screen while it
is in the air. They are chosen far apart: a name of two or more words gets the left piece
from its first part (the first word, or the words left of the middle) and the right piece
from the rest; a one-word name gets two pieces at least 40% of its width apart. When
nothing suitable is ready, a piece falls alone."""

SPAWN_PCT = 25
"""Every piece appears at this percent of the screen height, measured from the top.
25 is the bottom edge of the banner. It is never put inside the banner. (With the cat the
pieces appear just below it instead.)"""

FALL_PX = 36
"""How far, in pixels, a piece falls in each refresh while it is turning or waiting to be
turned (rounded to whole block rows: 3 rows for 12 px blocks, 2 for 16 px blocks). Once it
is the right way up it falls the rest of the way into place in one refresh. Raise it for a
faster game, but the time a player has to press a button before the piece turns itself
shrinks in the same proportion."""

MIN_PRESS_FRAMES = 3
"""The fall slows down, if it has to, until a player has at least this many refreshes to turn
a piece before it starts turning itself (a short play field leaves little time). It never
falls less than one row a refresh."""

AUTO_TURN_PCT = 55
"""A piece that is still not the right way up turns itself, 90 degrees a refresh by the
shorter way round, once it reaches this percent of the screen height. Buttons only turn
a piece above this line. The line is never lower than the pieces need to finish turning
above the name, so with the footer it ends up higher than this."""

FLIGHT_MIN_ROWS = 2
"""Slideshow only: pieces in the air are drawn at least this many rows above
their landing spot."""

SPLIT_ATTEMPTS = 10
"""Random tries at cutting each letter into pieces. Fewer pieces is better."""

GLYPH_ROWS = 7

FONT = {
    " ": ("...",) * GLYPH_ROWS,
    "A": (".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "B": ("XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."),
    "C": (".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."),
    "D": ("XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."),
    "E": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"),
    "F": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."),  # E without its bottom bar
    "G": (".XXXX", "X....", "X....", "X.XXX", "X...X", "X...X", ".XXXX"),
    "H": ("X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "I": ("XXX", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"),
    "J": ("..XXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."),
    "K": ("X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"),
    "L": ("X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"),
    "M": ("X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"),
    "N": ("X...X", "X...X", "XX..X", "X.X.X", "X..XX", "X...X", "X...X"),
    "O": (".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "P": ("XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."),
    "Q": (".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"),
    "R": ("XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"),
    "S": (".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."),
    "T": ("XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."),
    "U": ("X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "V": ("X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "W": ("X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"),
    "X": ("X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"),
    "Y": ("X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."),
    "Z": ("XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"),
    # Lowercase letters have no descender, so every letter sits on the same floor.
    "a": (".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX"),
    "b": ("X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX."),
    "c": (".....", ".....", ".XXXX", "X....", "X....", "X....", ".XXXX"),
    "d": ("....X", "....X", ".XXXX", "X...X", "X...X", "X...X", ".XXXX"),
    "e": (".....", ".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXXX"),
    # Acute accent in the two rows above the x-height.
    "é": ("...X.", "..X..", ".XXX.", "X...X", "XXXXX", "X....", ".XXXX"),
    "f": ("..XX.", ".X...", "XXXX.", ".X...", ".X...", ".X...", ".X..."),
    "g": (".....", ".....", ".XXXX", "X...X", ".XXXX", "....X", ".XXX."),
    "h": ("X....", "X....", "X.XX.", "XX..X", "X...X", "X...X", "X...X"),
    "i": (".X.", "...", "XX.", ".X.", ".X.", ".X.", "XXX"),
    "j": ("...X.", ".....", "...X.", "...X.", "...X.", "X..X.", ".XX.."),
    "k": ("X....", "X....", "X..X.", "X.X..", "XX...", "X.X..", "X..X."),
    "l": ("XX.", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"),
    "m": (".....", ".....", "XX.X.", "X.X.X", "X.X.X", "X.X.X", "X.X.X"),
    "n": (".....", ".....", "X.XX.", "XX..X", "X...X", "X...X", "X...X"),
    "o": (".....", ".....", ".XXX.", "X...X", "X...X", "X...X", ".XXX."),
    "p": (".....", ".....", "XXXX.", "X...X", "XXXX.", "X....", "X...."),
    "q": (".....", ".....", ".XXXX", "X...X", ".XXXX", "....X", "....X"),
    "r": (".....", ".....", "X.XX.", "XX..X", "X....", "X....", "X...."),
    "s": (".....", ".....", ".XXXX", "X....", ".XXX.", "....X", "XXXX."),
    "t": (".X...", ".X...", "XXXX.", ".X...", ".X...", ".X..X", "..XX."),
    "u": (".....", ".....", "X...X", "X...X", "X...X", "X...X", ".XXXX"),
    "v": (".....", ".....", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "w": (".....", ".....", "X...X", "X...X", "X.X.X", "X.X.X", ".X.X."),
    "x": (".....", ".....", "X...X", ".X.X.", "..X..", ".X.X.", "X...X"),
    "y": (".....", ".....", "X...X", "X...X", ".XXXX", "....X", ".XXX."),
    "z": (".....", ".....", "XXXXX", "...X.", "..X..", ".X...", "XXXXX"),
    "0": (".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."),
    "1": ("..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."),
    "2": (".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"),
    "3": (".XXX.", "X...X", "....X", "..XX.", "....X", "X...X", ".XXX."),
    "4": ("...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."),
    "5": ("XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."),
    "6": (".XXX.", "X....", "X....", "XXXX.", "X...X", "X...X", ".XXX."),
    "7": ("XXXXX", "....X", "...X.", "..X..", ".X...", ".X...", ".X..."),
    "8": (".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."),
    "9": (".XXX.", "X...X", "X...X", ".XXXX", "....X", "....X", ".XXX."),
    ":": ("...", "...", ".X.", "...", ".X.", "...", "..."),
}

_BUILD = 0
_BLINK = 1
_CLEAR = 2
_DROP = 3
_HOLD = 4
_CAT = 5  # the cat walks in and sits down
_SLEEP = 6  # the name is finished: wait for the panel to power down, then sleep until User A

_FULL = 1  # what the screen task is asked to do: a normal refresh of the whole panel,
_PART = 2  # or a partial one of what changed
_ALIVE_MS = 2500  # the screen task gives the panel back this long after run() stops
_IDLE_MS = 2000   # and powers it down this long after the picture stops changing


if _ep is not None:
    class _Panel(_ep.PartialEPD):
        """PartialEPD for a screen that has red on it. start() wipes the panel to white,
        which would also wipe the red bands; this opens a session on top of the picture
        a normal refresh has just drawn instead. Black pixels the partial pulls never
        touch, and so the red under them, stay as they are."""

        async def start_keep(self, film):
            """Open a session. film is the black plane the last normal refresh drew."""
            d = display
            if not d._reverse_fb_bits:
                raise _ep.PanelError("partial refresh is only known to work on the B1 panel")
            while d._framebuffer_ready.is_set() or not d.is_done_updating():
                await aio.sleep_ms(50)
            lock = getattr(d, "lock", None)
            if lock is not None:
                await lock.acquire()
                self._locked = True
            try:
                if self._rst():  # chips awake, maybe still refreshing: never reset mid-refresh
                    await self._ready("idle", 60_000)
                self._spi = d.spi
                if self.buf is None:
                    # (epd_partial's own sizes are const()s with a leading underscore, which
                    # MicroPython does not export from the module.)
                    plane = display_width * display_height // 8
                    self.buf = bytearray(plane)
                    self.fb = framebuf.FrameBuffer(self.buf, display_width, display_height,
                                                   framebuf.MONO_HLSB)
                    self._shown = bytearray(plane)
                    self._stage = bytearray(plane // 2)
                memoryview(self._shown)[:] = film
                memoryview(self.buf)[:] = film
                await self._open()
            except BaseException:
                await self.stop()
                raise


def _neighbors(c):
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _around(c):
    """The eight cells around c, the four that share an edge first."""
    x, y = c
    return _neighbors(c) + ((x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1))


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
    """Cut cells into pieces of up to four, hardest-to-fill cells first. A piece prefers
    cells that share an edge, but may reach across a corner, so a diagonal stroke can be
    cut into pieces of two."""
    free = set(cells)
    pieces = []
    while free:
        best = None
        best_n = 9
        for c in free:
            n = sum(1 for nb in _around(c) if nb in free)
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
                for pc in piece:
                    for nb in _around(pc)[4:]:
                        if nb in free and nb not in options:
                            options.append(nb)
            if not options:
                break
            nxt = random.choice(options)
            piece.append(nxt)
            free.discard(nxt)
        pieces.append(piece)
    return _absorb_singles(pieces)


def _connected(cells, corners=True):
    """True if the cells touch as one group, by edges only unless corners is True."""
    rest = set(cells)
    stack = [rest.pop()]
    while stack:
        c = stack.pop()
        for nb in (_around(c) if corners else _neighbors(c)):
            if nb in rest:
                rest.discard(nb)
                stack.append(nb)
    return not rest


def _absorb_singles(pieces):
    """Fold lone cells into a piece next to them (edge or corner): join one that has room,
    or take a cell off a bigger one that stays whole without it. A cell with nothing
    around it stays alone."""
    changed = True
    while changed:
        changed = False
        for single in [p for p in pieces if len(p) == 1]:
            cell = single[0]
            for nb in _around(cell):
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
        # Fewest single blocks first, then fewest pieces held together only by a corner
        # (not like a real Tetris piece), then fewest pieces.
        score = (sum(1 for p in pieces if len(p) == 1),
                 sum(1 for p in pieces if not _connected(p, False)),
                 len(pieces))
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


class _Flier:
    """A piece on its way down: turned some way, in its own columns, at some row."""

    def __init__(self, plan, i, lane, side):
        cells = plan.pieces[i]
        self.plan = plan
        self.i = i
        self.lane = lane
        self.side = side
        self.left = min(x for x, _ in cells)
        self.top = min(y for _, y in cells)
        final = sorted((x - self.left, y - self.top) for x, y in cells)
        self.width = max(x for x, _ in final) + 1
        self.shapes = [final]  # shapes[n]: the landed shape turned n quarter turns clockwise
        for _ in range(3):
            self.shapes.append(_turn(self.shapes[-1]))
        self.rot = random.randint(1, 3)
        self.way = random.choice((1, -1))  # which way to turn when both ways are as short
        self.rowf = float(plan.spawn_row)  # a float: the fall can be a fraction of a row
        self.row = plan.spawn_row
        self.arrived = False  # at its place, still solid black
        self.landed = False  # and white with a black border, one refresh later
        self.touched = False  # its player turned it
        self.auto = False  # it had to turn itself
        self.cells = self._place()

    def upright(self):
        return self.shapes[self.rot] == self.shapes[0]

    def _place(self):
        """Cells at the current turn and row, centred over the landing spot but kept
        inside this piece's lane."""
        shape = self.shapes[self.rot]
        w = max(x for x, _ in shape) + 1
        x = max(self.lane[0], min(self.left + (self.width - w) // 2, self.lane[1] - w))
        return [(x + sx, self.row + sy) for sx, sy in shape]

    def _auto_turn(self):
        """+1 or -1: the shorter way round to the right way up."""
        cw = 1
        while self.shapes[(self.rot + cw) % 4] != self.shapes[0]:
            cw += 1
        ccw = 1
        while self.shapes[(self.rot - ccw) % 4] != self.shapes[0]:
            ccw += 1
        if cw == ccw:
            return self.way
        return 1 if cw < ccw else -1

    def step(self, turns, auto_row):
        """Move on one refresh. A piece that is the right way up drops into place and stays
        solid black for one refresh (arrived), then turns white with a black border (landed);
        otherwise it falls plan.fall_rows, turned by the player's presses if it is still above auto_row, and by
        itself once it has fallen to auto_row."""
        if self.landed:
            return
        if self.arrived:
            self.landed = True
            return
        if self.upright():
            self.arrived = True
            self.cells = list(self.plan.pieces[self.i])
            return
        if turns and self.row < auto_row:
            self.rot = (self.rot + turns) % 4
            self.touched = True
        self.rowf = min(self.rowf + self.plan.fall_rows, self.top)
        self.row = int(self.rowf)
        if not self.upright() and self.row >= auto_row:
            self.rot = (self.rot + self._auto_turn()) % 4
            self.auto = True
        self.cells = self._place()


def _text(plane, s, x, y, cell, value=1):
    """Draw the string with the block font, each block `cell` pixels (may be fractional:
    4.5 gives blocks of 4 and 5 pixels). value 1 sets the pixels of the plane, 0 clears them:
    black digits on the black plane, white lettering by clearing the red plane."""
    pen = x  # a float when cell is: the pixel positions are rounded from it
    for ch in s:
        rows = FONT.get(ch)
        if rows is None:
            continue
        n = len(rows[0])
        for gy in range(GLYPH_ROWS):
            row = rows[gy]
            y0 = int(y + gy * cell + 0.5)
            high = int(y + (gy + 1) * cell + 0.5) - y0
            gx = 0
            while gx < n:
                if row[gx] == "X":
                    end = gx
                    while end < n and row[end] == "X":
                        end += 1
                    x0 = int(pen + gx * cell + 0.5)
                    plane.fill_rect(x0, y0, int(pen + end * cell + 0.5) - x0, high, value)
                    gx = end
                else:
                    gx += 1
        pen += (n + 1) * cell


def _disc(plane, cx, cy, r, value):
    """A filled circle of radius r (2 r + 1 pixels across), as rows of fill_rect."""
    for dy in range(-r, r + 1):
        half = int(((r + 0.5) ** 2 - dy * dy) ** 0.5)
        plane.fill_rect(cx - half, cy + dy, 2 * half + 1, 1, value)


_CAT_WALK = (  # four walking poses, facing right; # is a black block (CAT_SCALE px)
    (
        "............................",
        "..###................#....#.",
        ".##.#................##..##.",
        ".##..................######.",
        ".##................########.",
        ".##...######################",
        ".###########################",
        ".##########################.",
        "...######################...",
        "....#################.......",
        ".....#################......",
        ".......##############.......",
        "......##.##.......####......",
        ".....##..##........###......",
        "....##...##.........##......",
        "....##...##.........##......",
        "...###...###........####....",
    ),
    (
        "............................",
        "..###................#....#.",
        ".##.#................##..##.",
        ".##..................######.",
        ".##................########.",
        ".##...######################",
        ".###########################",
        ".##########################.",
        "...######################...",
        "....#################.......",
        ".....#################......",
        ".......##############.......",
        "......##.##.......####......",
        "......##.##.......####......",
        "......##.##.......####......",
        ".....##...##.......##.......",
        ".....###..###......###......",
    ),
    (
        "............................",
        "..###................#....#.",
        ".##.#................##..##.",
        ".##..................######.",
        ".##................########.",
        ".##...######################",
        ".###########################",
        ".##########################.",
        "...######################...",
        "....#################.......",
        ".....#################......",
        ".......##############.......",
        "......##.##.......####......",
        "......##.##.......##.##.....",
        ".......###.......##...##....",
        ".......###......##....##....",
        ".......####.....###....###..",
    ),
    (
        "............................",
        "..###................#....#.",
        ".##.#................##..##.",
        ".##..................######.",
        ".##................########.",
        ".##...######################",
        ".###########################",
        ".##########################.",
        "...######################...",
        "....#################.......",
        ".....#################......",
        ".......##############.......",
        ".......####.......####......",
        ".......####.......####......",
        ".......####.......####......",
        ".......####.......####......",
        ".......#####......#####.....",
    ),
)

_CAT_SIT = (  # sitting, facing right
    "..........#....#...",
    "..........##..##...",
    ".........########..",
    ".........#########.",
    ".........##########",
    ".........##########",
    ".........#########.",
    "........#########..",
    ".###....#########..",
    "##.#...##########..",
    "##....###########..",
    "##...############..",
    "##..#############..",
    "##..#############..",
    "##.##############..",
    "##.##############..",
    "##.###############.",
    "##################.",
)
_CAT_DROP_GAP = 4  # pixels between the sitting cat and where the piece appears
_CAT_SIT_RUMP = 5  # the column of its picture where the sitting cat's rear is (the piece falls there)
_CAT_WALK_RUMP = 4  # and the walking cat's
_CAT_SNAP_PX = 24  # the cat just shifts, without walking, if the next place is this close


def _cat_ground():
    """The line the cat stands and sits on: the bottom of the sitting cat."""
    return display_height * BANNER_PCT // 100 + CAT_GAP_PX + len(_CAT_SIT) * CAT_SCALE


def _draw_sprite(plane, rows, x, y, scale, value=1):
    """Draw a sprite (rows of '#' and '.') with its top left at x, y, clipped to the screen."""
    for gy, row in enumerate(rows):
        n = len(row)
        gx = 0
        while gx < n:
            if row[gx] != "#":
                gx += 1
                continue
            end = gx
            while end < n and row[end] == "#":
                end += 1
            x0 = max(0, x + gx * scale)
            x1 = min(display_width, x + end * scale)
            if x1 > x0:
                plane.fill_rect(x0, y + gy * scale, x1 - x0, scale, value)
            gx = end


def _draw_cat_at(plane, rows, rump, cx, face):
    """The cat (a picture and the column of its rear) standing on the ground line with its rear
    at x = cx, facing right (face 1) or left (-1, the picture turned round)."""
    if face < 0:
        # (MicroPython cannot slice with a step, so the row is reversed by hand)
        rows = ["".join([r[i] for i in range(len(r) - 1, -1, -1)]) for r in rows]
        rump = len(rows[0]) - 1 - rump
    _draw_sprite(plane, rows, int(cx - (rump + 0.5) * CAT_SCALE),
                 _cat_ground() - len(rows) * CAT_SCALE, CAT_SCALE)


def _sleep_note(lines):
    """Leave a note on the badge's flash: the serial port is gone while it sleeps (and after), so
    this is the only record of what woke it. Read it with `mpremote cat :sleep_note.txt`."""
    try:
        with open("/sleep_note.txt", "w") as note:
            note.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _light_sleep_until_button(pin_number):
    """Light-sleep the ESP32 in short naps until the button on pin_number is pressed (the pin reads
    0 then): after each nap of SLEEP_POLL_MS the pin is read, and it counts as a press if it stays low
    for 30 ms. Light sleep, not deep sleep, so the RAM is kept and the app carries on where it
    stopped. Returns "woke" when it was pressed (and has been let go again), "busy" if the button is
    down now (try again later), or "unavailable" if this firmware cannot do it. The USB serial link
    goes away when it sleeps and does not come back by itself: replug or reset the badge."""
    diary = []  # what it saw, for /sleep_note.txt
    try:
        import machine
        pin = machine.Pin(pin_number, machine.Pin.IN, machine.Pin.PULL_UP)
        if pin.value() == 0:
            return "busy"
        print("Light sleep until the button is pressed")
        time.sleep_ms(100)  # let the line above out of the serial port
        try:  # a clock that keeps counting while the chip sleeps (ticks_ms may not)
            wall0 = time.time_ns()
        except AttributeError:
            wall0 = None
        naps = 0
        bounces = 0
        while True:
            machine.lightsleep(SLEEP_POLL_MS)
            naps += 1
            time.sleep_ms(3)  # the pull-up is back before the pin is read
            if pin.value() != 0:
                continue
            held = True
            for _ in range(3):  # a press stays down; a glitch or a bounce does not
                time.sleep_ms(10)
                if pin.value() != 0:
                    held = False
                    break
            since = -1 if wall0 is None else (time.time_ns() - wall0) // 1000000
            if held:
                diary.append("PRESS after %d naps, %d ms after going to sleep" % (naps, since))
                break
            bounces += 1
            if len(diary) < 12:
                diary.append("nap %d, %d ms after going to sleep: pin low but not for 30 ms, ignored" % (naps, since))
            if bounces >= 200:  # the pin keeps blipping low: not a button, give up and stay awake
                diary.append("gave up after %d blips" % bounces)
                _sleep_note(diary)
                return "unavailable"
        t0 = time.ticks_ms()
        while pin.value() == 0 and time.ticks_diff(time.ticks_ms(), t0) < 3000:
            time.sleep_ms(10)  # wait for the release, so it is not counted a second time
        _sleep_note(diary)
        return "woke"
    except (ImportError, AttributeError, ValueError, TypeError, OSError) as ex:
        print("No light sleep here:", ex)
        return "unavailable"


def _noise(a, b, seed):
    """A fixed 16-bit scramble of two numbers and a seed (small ints only: no slow big numbers)."""
    h = (a * 157 + b * 311 + seed) & 0xFFFF
    h = ((h ^ (h >> 7)) * 251 + 29) & 0xFFFF
    h = ((h ^ (h >> 5)) * 241 + 61) & 0xFFFF
    return h ^ (h >> 8)


_SAND_STRIP = 6  # width of one step of the top of the sand
_SAND_GRAIN = 4  # the grains of sand sit in a grid of squares this big


def _sand_profile(valley, seed):
    """The y of the top line of the sand for each strip of _SAND_STRIP pixels: hills and valleys
    (SAND_HILL_PX apart, in steps of 2 px) from two slow waves and a little noise. A valley is at
    `valley`."""
    ph1 = (seed % 628) / 100.0
    ph2 = ((seed // 7) % 628) / 100.0
    out = []
    for i in range(display_width // _SAND_STRIP):
        v = (0.50 * math.sin(i / 6.0 + ph1) + 0.38 * math.sin(i / 2.6 + ph2)
             + 0.12 * (_noise(i, 3, seed) % 100 / 50.0 - 1.0))
        h = int((v + 1.0) / 2.0 * SAND_HILL_PX + 0.5)
        out.append(valley - h // 2 * 2)
    return out


def _draw_sand_into(plane, profile, seed):
    """Draw the sand into a bit plane: grains, evenly spread (SAND_DENSITY), from the top
    profile down to the bottom of the screen. There is no line: the hills and valleys show only
    as the edge of the grains."""
    strip = _SAND_STRIP
    g = _SAND_GRAIN
    for cy in range(min(profile) // g * g, display_height - 2, g):
        for cx in range(0, display_width - 3, g):
            if cy < profile[cx // strip]:
                continue
            n = _noise(cx // g, cy // g, seed)
            if n % 100 < SAND_DENSITY:
                plane.fill_rect(cx + ((n >> 8) & 1), cy + ((n >> 9) & 1), 2, 2, 1)


_HUD_W = 149  # how wide a player's panel is
_HUD_H = 152
_PANEL_MARGIN = 6  # of the left panel from the left edge
_RIGHT_PANEL_SHIFT = 12  # the right panel sits this much further in from the right edge: its outer
# margin then equals the left panel's (14 px)
_SCORE_CELL = 3  # block size of the score digits (and of the names in the menu)
_BATT_PIN = 14  # the ADC pin of the battery sense (lib/board.py BATT_V_SNS_PIN)
_BATT_BODY = (110, 44)  # outer size of the battery body
_BATT_NUB = (8, 18)  # and of the terminal on its right
_BATT_EDGE = 3  # width of the white outline
_BATT_SEGS = 5  # segments
_BATT_SEG = (16, 30, 4)  # one segment: width, height, gap to the next
_BATT_STEPS = (3.55, 3.70, 3.80, 3.92, 4.05)  # volts at which the 1st ... 5th segment lights (a
# Li-ion cell is full at 4.2 V and empty at about 3.3 V; roughly 5%, 25%, 45%, 65%, 85%)
_BATT_USB_V = 4.35  # above this the sense sees USB, not the battery
_BATT_BOLT = (  # the lightning bolt shown on USB, 8 x 14 blocks of 2 px
    "......##",
    ".....###",
    "....###.",
    "...###..",
    "..####..",
    ".#######",
    "..#####.",
    "....###.",
    "...###..",
    "..###...",
    ".###....",
    ".##.....",
    "##......",
    "#.......",
)


def _battery_volts():
    """The volts at the input of the 3.3 V regulator (the battery, or USB while it is plugged in),
    from the ADC on GPIO 14 through the 1/2 divider; None if there is no ADC (or no board)."""
    try:
        import machine
        adc = machine.ADC(machine.Pin(_BATT_PIN), atten=machine.ADC.ATTN_11DB)
        total = 0
        for _ in range(8):
            total += adc.read_uv()
        return total / 8 * 2 / 1000000
    except (ImportError, AttributeError, ValueError, TypeError, OSError):
        return None
# Where the SCORE/LINES column and the NEXT/button column start inside a panel. The left panel
# (User A) has NEXT/button first; the right panel (User B) has SCORE/LINES first. 19 px apart.
_SCORE_DX = (69, 8)
_NEXT_DX = (8, 107)
_BTN_R = 8  # radius of the button circles beside the big A or B
_DOT_R = 4  # radius of the black dot shown while the button is down (9 px across, was 7)
_BTN_DX = (8, 36)  # where their centres are in the column: left of the A, right of the B
_LETTER_DX = (21, 0)  # and where the A or B itself starts
_BTN_UP = 80  # with the name menu the A and B button groups sit this much higher, near the top edge
_MENU_DX = 71  # the labels of the names in the left panel: where the first starts inside the panel,
_MENU_DY = 28  # how far down (level with the top of the SCORE box),
_MENU_GAP = 5  # the space between two labels,
_MENU_PAD = 5  # the space round the letters inside a label,
_MENU_CELL = _SCORE_CELL  # the block size of the letters: the same as the score digits (smaller if a name would be wider than
_MENU_MAX_W = 105  # this many pixels)


def _text_w(s, cell):
    """The width in pixels of the string drawn by _text."""
    w = 0
    for ch in s:
        rows = FONT.get(ch)
        if rows is not None:
            w += (len(rows[0]) + 1) * cell
    return int(w - cell + 0.5)


class _Hud:
    """The score boards in the top banner: a panel for each player at its end. Red can only be
    drawn by the full refresh, so whatever changes has to sit on white or black: the panels
    are the red band with white lettering, the numbers and the next piece are black in small
    white boxes. Partial refreshes change only those boxes. The names of the menu (NAME_MENU) are in boxes too, a
    label for each: the selected one white with black letters, the others black with white
    letters. (A name cannot be white on the red and become black on white when it is selected:
    the red under a white label could never come back.)"""

    def __init__(self, top):
        self.xs = (_PANEL_MARGIN, display_width - _PANEL_MARGIN - _HUD_W - _RIGHT_PANEL_SHIFT)
        self.y = top + 8
        self.by = self.y - (_BTN_UP if NAME_MENU else 0)  # the y the button groups are measured from
        # the battery icon, centred, level with where the clock was: body, terminal, the black box inside
        total_w = _BATT_BODY[0] + _BATT_NUB[0]
        self.batx = (display_width - total_w) // 2
        self.baty = top + 6
        e = _BATT_EDGE
        self.batwell = (self.batx + e, self.baty + e, _BATT_BODY[0] - 2 * e, _BATT_BODY[1] - 2 * e)
        self.menu = []  # the labels of the names listed in the left panel: (name, x, y)
        self.menu_cell = _MENU_CELL
        self.menu_w = self.menu_h = 0
        if NAME_MENU:
            names = NAMES[:3]
            widest = 0
            for name in names:
                while self.menu_cell > 2 and _text_w(name, self.menu_cell) > _MENU_MAX_W:
                    self.menu_cell -= 0.5
            for name in names:
                widest = max(widest, _text_w(name, self.menu_cell))
            self.menu_w = widest + 2 * _MENU_PAD
            self.menu_h = int(GLYPH_ROWS * self.menu_cell + 0.5) + 2 * _MENU_PAD
            for n, name in enumerate(names):
                self.menu.append((name, self.xs[0] + _MENU_DX, self.y + _MENU_DY + n * (self.menu_h + _MENU_GAP)))

    def boxes(self):
        """The white boxes that change, as (x, y, width, height)."""
        out = []
        for side in (0, 1):
            if side == 0 and NAME_MENU:
                continue  # the left panel is the list of names
            x, sx, nx = self.xs[side], _SCORE_DX[side], _NEXT_DX[side]
            if NAME_MENU:  # SCORE, and NEXT in place of LINES
                out += [(x + sx, self.y + 28, 80, 29), (x + sx, self.y + 82, 42, 42)]
                continue
            out += [(x + sx, self.y + 28, 80, 29), (x + sx, self.y + 82, 44, 29),
                    (x + nx, self.y + 28, 42, 42)]
        for name, mx, my in self.menu:
            out.append((mx, my, self.menu_w, self.menu_h))
        if BATTERY_ICON:
            out.append(self.batwell)
        return out

    def wells(self):
        """Everything that may change after the full refresh: the boxes and the squares round
        the filled button circles (the dot appears in them)."""
        out = self.boxes()
        for side in (0, 1):
            cx = self.xs[side] + _NEXT_DX[side] + _BTN_DX[side]
            out.append((cx - _BTN_R, self.by + 131 - _BTN_R, 2 * _BTN_R + 1, 2 * _BTN_R + 1))
        return out

    def draw_static(self):
        """Lettering and the empty boxes, drawn with the band by the full refresh."""
        red = display.red
        for side in (0, 1):
            x, y, sx, nx = self.xs[side], self.y, _SCORE_DX[side], _NEXT_DX[side]
            if NAME_MENU:
                if side == 1:
                    _text(red, "SCORE", x + sx + 2, y + 10, 2, 0)
                    _text(red, "NEXT", x + sx + 2, y + 64, 2, 0)  # where LINES was
                elif self.menu:  # the same size and height as SCORE, over the list of names
                    _text(red, "NAME", self.menu[0][1] + 2, y + 10, 2, 0)
            else:
                _text(red, "SCORE", x + sx + 2, y + 10, 2, 0)
                _text(red, "LINES", x + sx + 2, y + 64, 2, 0)
                _text(red, "NEXT", x + nx, y + 10, 2, 0)
            by = self.by
            _text(red, "AB"[side], x + nx + _LETTER_DX[side], by + 104, 5, 0)
            # The badge's two buttons on that side, one above the other: the menu button
            # (an outline) and the user button (filled).
            cx = x + nx + _BTN_DX[side]
            _disc(red, cx, by + 112, _BTN_R, 0)
            _disc(red, cx, by + 112, _BTN_R - 2, 1)
            _disc(red, cx, by + 131, _BTN_R, 0)
        if BATTERY_ICON:  # the white outline and terminal; the box inside is cleared with the other boxes
            red.fill_rect(self.batx, self.baty, _BATT_BODY[0], _BATT_BODY[1], 0)
            red.fill_rect(self.batx + _BATT_BODY[0], self.baty + (_BATT_BODY[1] - _BATT_NUB[1]) // 2,
                          _BATT_NUB[0], _BATT_NUB[1], 0)
        for wx, wy, ww, wh in self.boxes():
            red.fill_rect(wx, wy, ww, wh, 0)

    def draw_battery(self, battery):
        """The inside of the battery icon: black, with `battery` (0 to 5) white segments, or a white
        lightning bolt if it is "usb"; empty for None (no reading)."""
        black = display.black
        wx, wy, ww, wh = self.batwell
        black.fill_rect(wx, wy, ww, wh, 1)
        if battery == "usb":
            rows = len(_BATT_BOLT)
            x0 = wx + (ww - 2 * len(_BATT_BOLT[0])) // 2
            y0 = wy + (wh - 2 * rows) // 2
            for gy, row in enumerate(_BATT_BOLT):
                for gx, ch in enumerate(row):
                    if ch == "#":
                        black.fill_rect(x0 + 2 * gx, y0 + 2 * gy, 2, 2, 0)
        elif battery:
            sw, sh, gap = _BATT_SEG
            pad = (ww - (_BATT_SEGS * sw + (_BATT_SEGS - 1) * gap)) // 2
            for k in range(battery):
                black.fill_rect(wx + pad + k * (sw + gap), wy + (wh - sh) // 2, sw, sh, 0)

    def draw_values(self, score, lines, nexts, pressed=(False, False), selected=0, battery=None):
        """The numbers and the next pieces: cleared and drawn again on each frame. The menu
        names too: the selected one black on a white label, the others white on a black label."""
        black = display.black
        if BATTERY_ICON:
            self.draw_battery(battery)
        for n, (name, mx, my) in enumerate(self.menu):
            black.fill_rect(mx, my, self.menu_w, self.menu_h, 0 if n == selected else 1)
            _text(black, name, mx + _MENU_PAD, my + _MENU_PAD, self.menu_cell, 1 if n == selected else 0)
        for side in (0, 1):
            x, y, sx, nx = self.xs[side], self.y, _SCORE_DX[side], _NEXT_DX[side]
            if NAME_MENU:
                if side == 1:  # SCORE, and the next piece in place of LINES
                    black.fill_rect(x + sx, y + 28, 80, 29, 0)
                    _text(black, "%04d" % min(score[side], 9999), x + sx + 4, y + 32, _SCORE_CELL)
                    black.fill_rect(x + sx, y + 82, 42, 42, 0)
                    for cx, cy in nexts[side] or ():
                        black.fill_rect(x + sx + 3 + cx * 9, y + 85 + cy * 9, 8, 8, 1)
            else:
                black.fill_rect(x + sx, y + 28, 80, 29, 0)
                _text(black, "%04d" % min(score[side], 9999), x + sx + 4, y + 32, _SCORE_CELL)
                black.fill_rect(x + sx, y + 82, 44, 29, 0)
                _text(black, "%02d" % min(lines[side], 99), x + sx + 4, y + 86, _SCORE_CELL)
                black.fill_rect(x + nx, y + 28, 42, 42, 0)
                for cx, cy in nexts[side] or ():
                    black.fill_rect(x + nx + 3 + cx * 9, y + 31 + cy * 9, 8, 8, 1)
            # A black dot in the middle of the filled circle while the button is down.
            bx = x + nx + _BTN_DX[side]
            black.fill_rect(bx - _BTN_R, self.by + 131 - _BTN_R, 2 * _BTN_R + 1, 2 * _BTN_R + 1, 0)
            if pressed[side]:
                _disc(black, bx, self.by + 131, _DOT_R, 1)


class _Banner:
    """A red band across the top and one across the bottom, each with its lettering
    image drawn over it."""

    def __init__(self):
        self.height = display_height * BANNER_PCT // 100
        self.foot = display_height * FOOTER_PCT // 100
        self.hud = None

    def draw(self):
        """Red band in the red plane, then the white lettering on top of it. The top band
        also gets the score boards. If an image cannot be drawn the band stays plain red."""
        if self.height:
            display.red.fill_rect(0, 0, display_width, self.height, 1)
            try:
                display.draw_png(BANNER_IMAGE, 0, 0)
            except Exception as ex:  # missing file, not a palette PNG, ...
                print("Banner image not drawn:", ex)
            if SCOREBOARD and self.height >= _HUD_H + 16:
                self.hud = _Hud(0)
                self.hud.draw_static()
        if self.foot:
            top = display_height - self.foot
            display.red.fill_rect(0, top, display_width, self.foot, 1)
            try:
                display.draw_png(FOOTER_IMAGE, top, 0)
            except Exception as ex:
                print("Footer image not drawn:", ex)


class _Plan:
    """A name cut into pieces, with the pixel layout to draw it."""

    def __init__(self, text):
        glyphs, cols = _text_cells(text)
        self.cell = max(2, min(MAX_CELL, display_width // (cols + 2)))
        self.gap = max(1, self.cell // 8)
        self.x0 = (display_width - cols * self.cell) // 2
        # The name sits BOTTOM_MARGIN pixels above the footer band, lifted by NAME_RISE_PCT;
        # y_off shifts the grid down by what is left over after whole rows.
        floor = (display_height - display_height * FOOTER_PCT // 100 - BOTTOM_MARGIN
                 - int(display_height * NAME_RISE_PCT / 100))
        self.floor = floor  # the bottom of the name
        self.field_rows = floor // self.cell
        self.y_off = floor - self.field_rows * self.cell
        self.y_grid = self.field_rows - GLYPH_ROWS
        # First grid row below the banner; pieces in the air stay under it.
        self.top_row = (display_height * BANNER_PCT // 100 + self.cell - 1) // self.cell
        # Row where every piece appears, and how far sideways a turned piece may reach.
        self.spawn_row = max(self.top_row,
                             (display_height * SPAWN_PCT // 100 + self.cell - 1) // self.cell)
        if CAT:  # the pieces appear just below the sitting cat
            self.spawn_row = max(self.top_row,
                                 (_cat_ground() + _CAT_DROP_GAP + self.cell - 1) // self.cell)
        # Rows a piece falls in each refresh: FALL_PX worth, slowed down (in quarter rows, to no
        # less than one) until a player gets MIN_PRESS_FRAMES refreshes before the auto-turn line.
        # That line is halfway down the screen, but no lower than the last place a piece can
        # finish turning above the name (two turns, each after a fall of up to ceil(fall)
        # rows, and a piece is at most four rows tall).
        halfway = display_height * AUTO_TURN_PCT // 100 // self.cell
        fall = max(1.0, FALL_PX / self.cell)
        while True:
            whole = int(fall) + (1 if fall > int(fall) else 0)
            auto = max(self.spawn_row, min(halfway, self.y_grid - 2 * whole - 3))
            if fall <= 1.0 or (auto - self.spawn_row) / fall >= MIN_PRESS_FRAMES:
                break
            fall = max(1.0, fall - 0.25)
        self.fall_rows = fall
        self.auto_row = auto
        self.min_x = -(self.x0 // self.cell)
        self.max_x = (display_width - self.x0) // self.cell
        self.cols = cols
        # Where the name divides into its left part (first word or first names) and its right
        # part: the middle of the gap between words that is nearest to the middle of the name.
        # None if the name is one word.
        self.split = None
        pen = 0
        for ch in text:
            width = len(FONT[ch][0]) + 1
            if ch == " " and 0 < pen and pen + width < cols:
                mid = pen + width / 2
                if self.split is None or abs(mid - cols / 2) < abs(self.split - cols / 2):
                    self.split = mid
            pen += width
        self.pieces = []
        self.before = []
        self.glyph_of = []  # for each piece, which letter it belongs to
        self.glyph_sizes = []  # pieces in each letter
        for cells in glyphs:
            pieces, before = _split_glyph(cells)
            base = len(self.pieces)
            self.glyph_sizes.append(len(pieces))
            for piece in pieces:
                self.glyph_of.append(len(self.glyph_sizes) - 1)
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

    def span(self, i):
        """Columns piece i covers when landed: (first, one past the last)."""
        xs = [x for x, _ in self.pieces[i]]
        return min(xs), max(xs) + 1

    def centre_px(self, i):
        """The x, in pixels, of the middle of piece i when landed."""
        a, b = self.span(i)
        return self.x0 + (a + b) * self.cell // 2

    def reach(self, i):
        """The most columns piece i covers in any orientation."""
        xs = [x for x, _ in self.pieces[i]]
        ys = [y for _, y in self.pieces[i]]
        return max(max(xs) - min(xs), max(ys) - min(ys)) + 1

    def lanes(self, wave):
        """The columns (first, one past the last) each piece of a wave of one or two may
        use while it is in the air, left piece first. None if they cannot be kept apart."""
        if len(wave) == 1:
            return [(self.min_x, self.max_x)]
        (a0, a1), (b0, b1) = self.span(wave[0]), self.span(wave[1])
        low = max(a1, self.min_x + self.reach(wave[0]))
        high = min(b0, self.max_x - self.reach(wave[1]))
        if low > high:
            return None
        edge = (low + high) // 2
        return [(self.min_x, edge), (edge, self.max_x)]

    def middle(self, i):
        """The column in the middle of piece i when landed."""
        a, b = self.span(i)
        return (a + b) / 2

    def partner(self, first, ready):
        """The piece from `ready` to fall together with `first`, or None. Two pieces fall
        side by side only if they can be kept in separate columns on the way down; of those,
        a name of two or more words takes one piece from its left part and one from its
        right part (at least 15% of the name's width apart), and a one-word name takes two that are well apart (at least 40% of the
        name's width, or failing that 25%, the farthest). Pieces that would fall close
        together fall alone instead."""
        apart, across = [], []
        for other in ready:
            pair = sorted((first, other), key=lambda i: self.span(i)[0])
            if self.span(pair[0])[1] > self.span(pair[1])[0] or not self.lanes(pair):
                continue
            gap = abs(self.middle(first) - self.middle(other))
            apart.append((gap, other))
            if (gap >= 0.15 * self.cols and self.split is not None
                    and (self.middle(first) < self.split) != (self.middle(other) < self.split)):
                across.append(other)
        if across:
            return random.choice(across)
        wide = [o for g, o in apart if g >= 0.4 * self.cols]
        if wide:
            return random.choice(wide)
        far = [(g, o) for g, o in apart if g >= 0.25 * self.cols]
        return max(far, key=lambda t: t[0])[1] if far else None

    def land_waves(self, at_most):
        """The pieces grouped into waves of one or two that fall together, each a list
        of piece numbers, left piece first. A wave only takes pieces whose supports have
        already landed, so none waits on another (see `partner` for who falls with whom)."""
        done = set()
        waves = []
        while len(done) < len(self.pieces):
            ready = [i for i in range(len(self.pieces))
                     if i not in done and self.before[i] <= done]
            first = random.choice(ready)
            ready.remove(first)
            wave = [first]
            other = self.partner(first, ready) if at_most >= 2 else None
            if other is not None:
                wave = sorted((first, other), key=lambda i: self.span(i)[0])
            done.update(wave)
            waves.append(wave)
        return waves

    def draw_cells(self, plane, cells):
        size = self.cell - self.gap
        for x, y in cells:
            plane.fill_rect(self.x0 + x * self.cell, y * self.cell + self.y_off, size, size, 1)

    def draw_hollow(self, plane, cells):
        """Blocks as a black border round white: a piece that has landed."""
        size = self.cell - self.gap
        border = 2 if size >= 8 else 1
        for x, y in cells:
            px = self.x0 + x * self.cell
            py = y * self.cell + self.y_off
            plane.fill_rect(px, py, size, size, 1)
            if size > 2 * border:
                plane.fill_rect(px + border, py + border, size - 2 * border, size - 2 * border, 0)

    def draw_piece(self, plane, cells, rows_up=0):
        size = self.cell - self.gap
        for x, y in cells:
            plane.fill_rect(self.x0 + x * self.cell,
                            (y - rows_up) * self.cell + self.y_off, size, size, 1)

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
        self.sleep_ms = 10  # short: the time between a refresh ending and the next starting counts
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
        self.hold_ms = 0
        self.frame_ms = 0
        self.fliers = []  # the pieces of the current wave in the air
        self.taps = [0, 0]  # presses of User A and User B since the last refresh
        self.panel = None  # the partial refresh driver
        self.task = None  # the task that owns the panel while the app runs
        self.req = None  # what it was last asked to do: _FULL or _PART
        self.pending = False  # a request is waiting or being shown
        self.failed = False  # the screen task stopped on an error
        self.beat = 0  # ticks_ms of the last run(); the task stops when it gets old
        self.film = None  # the black plane a normal refresh is about to draw
        self.need_full = True  # the next name starts with the one full refresh (red bands)
        self.wipe_step = 0
        self.cat_x = None  # where the cat's rear is (None: not on the screen yet this round)
        self.cat_face = 1  # which way it looks: 1 right, -1 left
        self.cat_from = self.cat_goal = 0  # a walk, from where to where
        self.cat_steps = 0  # in this many refreshes
        self.cat_k = 0  # and this is the one it is at
        self.cat_ready = False  # it is sitting where the next piece falls
        self.panel_asleep = False  # the screen task has powered the panel down (set by the task)
        self.sleep_t0 = 0  # when the name was finished
        self.sleep_warned = False
        self.sleep_unavailable = False  # light sleep does not work here: stay awake instead
        self.batt = None  # the battery level shown: 0 to 5 segments, "usb", or None (no reading yet)
        self.batt_lit = None  # the last number of segments (kept to give the thresholds some hysteresis)
        self.batt_t = None  # ticks_ms of the last measurement
        self.sand_seed = 0  # this round's dunes
        self.sand_y = 0  # the top row of the sand, and its rows kept as a copy (None: not drawn yet)
        self.sand_cache = None
        self.score = [0, 0]  # left and right player
        self.lines = [0, 0]  # letters finished
        self.glyph_left = []  # pieces still to land in each letter
        self.last_side = 0  # which player pressed a button last
        self.seen = [False, False]  # a button was pressed since the last refresh
        self.run_start = 0  # ticks_ms when the pieces started to fall; 0 before (for the log)
        self.run_end = 0  # and when the last piece landed; 0 while it runs (for the log)

    def _start_word(self, idx):
        self.word = idx % len(NAMES)
        plan = self.plans.get(self.word)
        if plan is None:
            gc.collect()  # planning allocates a lot; start from a clean heap
            plan = self.plans[self.word] = _Plan(NAMES[self.word])
        self.plan = plan
        if self.banner is None:
            self.banner = _Banner()
        self.fast = (FAST and _ep is not None and not self.failed
                     and getattr(display, "_reverse_fb_bits", False))
        if self.need_full or not self.fast:
            self.screen_ready = False  # the next frame starts from a full clear and the banner
        self.frame_ms = 0
        if self.fast:
            if self.film is None:
                self.film = bytearray(len(display._framebuffer_black))
            if self.task is None or self.task.done():
                self.req = None
                self.pending = False
            self._ensure_task()
            self.waves = plan.land_waves(1 if (CAT or NAME_MENU) else max(1, PIECES_AT_ONCE))
            self.order = [i for wave in self.waves for i in wave]
            self.score = [0, 0]
            self.lines = [0, 0]
            self.glyph_left = list(plan.glyph_sizes)
            self.run_start = self.run_end = 0
            self.batch = 0
            self.frame = 0
            self.landed = []
            self.cat_x = None
            self.cat_ready = False
            self.sand_cache = None  # new dunes
            self.sand_seed = random.randint(0, 9999)
            self.state = _CLEAR
            print(f"{NAMES[self.word]}: {len(self.order)} pieces in {len(self.waves)} waves, "
                  f"cell {plan.cell}px")
            return
        self.order = plan.land_sequence()
        count = len(self.order)
        self.batch_size = max(1, (count + TARGET_FRAMES - 1) // TARGET_FRAMES)
        # One snapshot per batch in the air, then one with everything landed.
        self.frames = (count + self.batch_size - 1) // self.batch_size + 1
        self.frame = 0
        self.state = _BUILD
        print(f"{NAMES[self.word]}: {count} pieces, {self.frames} frames, cell {plan.cell}px")

    def _alive(self):
        # run() stops being called when the user leaves the app (no hook for that), so
        # the task gives the panel back when the calls stop. Allow for the PNG decode and
        # a garbage collection, a second or so each, on top of a frame's work.
        return time.ticks_diff(time.ticks_ms(), self.beat) < _ALIVE_MS

    async def _screen(self):
        """Owns the panel while the app runs: does the normal and partial refreshes that
        run() asks for, one at a time, and hands the panel back when the app stops."""
        if self.panel is None:
            self.panel = _Panel()
        panel = self.panel
        session = False
        asleep = False
        still = time.ticks_ms()
        try:
            while self._alive():
                req = self.req
                if req is None:
                    if session and not asleep and time.ticks_diff(time.ticks_ms(), still) > _IDLE_MS:
                        await panel.sleep()  # the picture sits still: no point keeping the boost up
                        asleep = True
                        self.panel_asleep = True
                    await aio.sleep_ms(5)
                    continue
                self.req = None
                self.panel_asleep = False
                if req == _FULL:
                    if session:
                        await panel.stop()
                        session = False
                    display.update()
                    while not display.is_done_updating():
                        await aio.sleep_ms(50)
                    self.panel_asleep = True  # the stock driver powers the panel down when it is done
                else:
                    if not session:
                        await panel.start_keep(self.film)
                        session = True
                    memoryview(panel.buf)[:] = display._framebuffer_black
                    await panel.show()
                    asleep = False
                still = time.ticks_ms()
                self.pending = False
        except Exception as ex:
            print("Tetris Tag: screen stopped:", ex)
            sys.print_exception(ex)
            self.failed = True
            self.pending = False
        finally:
            if session:
                try:
                    await panel.stop()
                except Exception as ex:
                    print("Tetris Tag: panel stop:", ex)

    def _ensure_task(self):
        """Make sure the screen task is running (it stops when run() goes quiet)."""
        if not self.failed and (self.task is None or self.task.done()):
            self.beat = time.ticks_ms()
            self.task = aio.create_task(self._screen())

    def _request(self, kind):
        """Ask the screen task to show what is in the framebuffers."""
        self._ensure_task()
        if kind == _FULL:
            memoryview(self.film)[:] = display._framebuffer_black  # what the film will show
        self.req = kind
        self.pending = True
        self.frame_ms = time.ticks_ms()

    def _full(self):
        """A normal refresh of the whole panel (about 35 s)."""
        if self.fast:
            self._request(_FULL)
        else:
            display.update()
            self.frame_ms = time.ticks_ms()

    def _new_frame(self):
        """Blank canvas for the next frame. The banner is drawn once per name and then
        left where it is: redrawing it would decode the image for every frame."""
        if not self.screen_ready:
            display.clear()
            self.banner.draw()
            self._draw_hud()
            self.screen_ready = True
            self._draw_sand()
            return
        top = self.banner.height
        rows = display_height - self.banner.foot - top  # between the two bands
        display.black.fill_rect(0, top, display_width, rows, 0)
        display.red.fill_rect(0, top, display_width, rows, 0)
        self._draw_sand()

    def _draw_sand(self):
        """The sand, on a field that has just been cleared. The first time in a round it is drawn
        and its rows are kept; after that they are copied back (one memory copy, no drawing)."""
        if not SAND or self.plan is None or self.banner.foot:
            return
        pitch = display_width // 8
        buf = display._framebuffer_black
        if self.sand_cache is None:
            t0 = time.ticks_ms()
            profile = _sand_profile(self.plan.floor - self.plan.gap, self.sand_seed)
            _draw_sand_into(display.black, profile, self.sand_seed)
            self.sand_y = min(profile)
            self.sand_cache = bytes(buf[self.sand_y * pitch:])
            print("Sand drawn in", time.ticks_diff(time.ticks_ms(), t0), "ms, top row", self.sand_y)
        else:
            memoryview(buf)[self.sand_y * pitch:] = self.sand_cache

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

    def _battery_level(self):
        """The battery icon's state: measured every 30 s. 0 to 5 segments (a segment goes on a little
        above its threshold and off a little below it, so the icon does not flicker), "usb" while the
        sense sees the USB supply, or None if there is no reading."""
        now = time.ticks_ms()
        if self.batt_t is not None and time.ticks_diff(now, self.batt_t) < 30000:
            return self.batt
        self.batt_t = now
        v = _battery_volts()
        if v is None:
            self.batt = None
        elif v > _BATT_USB_V:
            if self.batt != "usb":
                print("Battery sense: %.2f V = USB power, no battery reading" % v)
            self.batt = "usb"
        else:
            new = 0
            for step in _BATT_STEPS:
                if v >= step:
                    new += 1
            lit = self.batt_lit
            if lit is not None:
                if new > lit and v < _BATT_STEPS[lit] + 0.02:
                    new = lit
                elif new < lit and v > _BATT_STEPS[lit - 1] - 0.02:
                    new = lit
            if new != lit:
                print("Battery: %.2f V, %d of %d segments" % (v, new, _BATT_SEGS))
            self.batt = self.batt_lit = new
        return self.batt

    def _draw_hud(self):
        """The numbers and next pieces on the score boards (if there are any)."""
        hud = self.banner.hud if self.banner else None
        if hud is None:
            return
        waves = self.waves if self.fast else ()
        upcoming = waves[self.batch + 1] if self.batch + 1 < len(waves) else ()
        nexts = []
        for side in (0, 1):
            # One piece at a time with the menu: the next one is shown on the right panel,
            # which keeps the score. Otherwise each panel shows the next piece of its side.
            n = upcoming[0] if (NAME_MENU and side == 1 and upcoming) else None
            if not NAME_MENU and side < len(upcoming):
                n = upcoming[side]
            if n is not None:
                cells = self.plan.pieces[n]
                left = min(x for x, _ in cells)
                top = min(y for _, y in cells)
                nexts.append([(x - left, y - top) for x, y in cells])
            else:
                nexts.append(None)
        pressed = (self.seen[0] or bool(getattr(UserA, "value", False)),
                   self.seen[1] or bool(getattr(UserB, "value", False)))
        hud.draw_values(self.score, self.lines, nexts, pressed, self.word, self._battery_level() if BATTERY_ICON else None)

    def _credit(self, flier, side):
        """A piece has landed: points to the player at `side`, and a line if it finished
        its letter."""
        points = 10 + (10 if flier.touched and not flier.auto else 0)
        letter = self.plan.glyph_of[flier.i]
        self.glyph_left[letter] -= 1
        if self.glyph_left[letter] == 0:
            self.lines[side] += 1
            points += 100
        self.score[side] += points

    def _show_fast(self, moving, settled=()):
        """Partial refresh: the pieces in the air and the one that has just dropped into place
        (`moving`, a list of cell lists) in solid black, the ones that have landed (`settled`,
        just now, and `self.landed`) as a black border round white."""
        plan = self.plan
        self._new_frame()
        if CAT:
            self._draw_cat()
        for i in self.landed:
            plan.draw_hollow(display.black, plan.pieces[i])
        for cells in settled:
            plan.draw_hollow(display.black, cells)
        for cells in moving:
            plan.draw_cells(display.black, cells)
        self._draw_hud()
        self._request(_PART)

    def _drop_frame(self):
        """One partial refresh of the current wave. The first one shows the pieces at
        the spawn height, turned a random way. After that each piece that is not yet the
        right way up falls a few rows, turned by its player if they pressed a button,
        or by itself once it is low enough. A piece that is the right way up drops into
        place, still solid black, and turns white with a black border one refresh later; the
        wave is over when every piece in it has."""
        wave = self.waves[self.batch]
        self.seen = [self.taps[0] > 0, self.taps[1] > 0]  # shown on the buttons drawn at the score boards
        if not self.run_start:
            self.run_start = time.ticks_ms() or 1  # (for the log)
        if self.frame == 0:
            lanes = self.plan.lanes(wave)
            self.fliers = [_Flier(self.plan, i, lanes[n], n) for n, i in enumerate(wave)]
            self.taps = [0, 0]
        else:
            auto_row = self.plan.auto_row
            for f in self.fliers:
                if len(self.fliers) == 1:
                    turns = self.taps[1] if NAME_MENU else self.taps[0] + self.taps[1]
                else:
                    turns = self.taps[f.side]
                was = f.landed
                f.step(turns % 4, auto_row)
                if f.landed and not was:
                    self._credit(f, 1 if NAME_MENU else (f.side if len(self.fliers) > 1 else self.last_side))
            self.taps = [0, 0]
        self._show_fast([f.cells for f in self.fliers if not f.landed],
                        [f.cells for f in self.fliers if f.landed])
        if all(f.landed for f in self.fliers):
            self.landed.extend(wave)
            self.batch += 1
            self.frame = 0
            self.cat_ready = False  # the cat walks to the next place
        else:
            self.frame += 1

    def _start_blink(self):
        self.state = _BLINK
        self.run_end = time.ticks_ms() or 1
        self.blink_step = 0
        self.blink_ms = time.ticks_ms()
        if BLINK_MODE == "leds":
            leds.fill(BLINK_COLOR)

    def _try_sleep(self):
        """The name is finished. Once the panel has powered down, put the ESP32 to sleep until
        the wake-up button (SLEEP_WAKE_BUTTON) is pressed, then start the name again (or the next one)."""
        if self.sleep_unavailable:
            return  # staying awake: the buttons still start a name
        if self.fast and not self.panel_asleep:  # never sleep with the panel's booster up
            if not self.sleep_warned and time.ticks_diff(time.ticks_ms(), self.sleep_t0) > 20000:
                self.sleep_warned = True
                print("Waiting for the panel to power down before sleeping")
            return
        leds.fill((0, 0, 0))
        wake_button = UserA if SLEEP_WAKE_BUTTON == "A" else UserB
        result = _light_sleep_until_button(_PINS[SLEEP_WAKE_BUTTON])
        if result == "unavailable":
            self.sleep_unavailable = True
        elif result == "woke":
            try:
                wake_button._pressed_state = 2  # this press is used up: it must not count again
            except AttributeError:
                pass
            self.beat = time.ticks_ms()  # the screen task must not think the app has stopped
            self.seen[0 if SLEEP_WAKE_BUTTON == "A" else 1] = True
            print("User " + SLEEP_WAKE_BUTTON + ": woke up, " + ("next name" if WAKE_NEXT_NAME else "same name again"))
            self._start_word(self.word + 1 if WAKE_NEXT_NAME else self.word)

    def _start_hold(self):
        """The name is finished: go to sleep until User A (SLEEP_WHEN_DONE), or stay up,
        untouched, for HOLD_S seconds."""
        if SLEEP_WHEN_DONE:
            self.state = _SLEEP
            self.sleep_t0 = time.ticks_ms()
            self.sleep_warned = False
            self.sleep_unavailable = False
            print(f"{NAMES[self.word]} finished: the animation stops")
            return
        self.state = _HOLD
        self.hold_ms = time.ticks_ms()
        print(f"Holding {NAMES[self.word]} for {HOLD_S} s")

    def _draw_cat(self):
        """The cat, sitting where it is."""
        if self.cat_x is not None:
            _draw_cat_at(display.black, _CAT_SIT, _CAT_SIT_RUMP, self.cat_x, self.cat_face)

    def _cat_begin(self):
        """The cat goes to where the next piece falls: at the start of a round in from the nearer
        side of the screen, after that from where it sits (a short way it just shifts)."""
        goal = self.plan.centre_px(self.waves[self.batch][0])
        if self.cat_x is None:
            far = int((len(_CAT_WALK[0][0]) - _CAT_WALK_RUMP - 0.5) * CAT_SCALE)  # rear to the far edge
            start = -far if goal < display_width // 2 else display_width + far
            print("Cat walks in")
        elif abs(goal - self.cat_x) < _CAT_SNAP_PX:
            self.cat_x = goal
            self.cat_ready = True
            self._drop_frame()
            return
        else:
            start = self.cat_x
        self.cat_from, self.cat_goal = start, goal
        self.cat_face = 1 if goal >= start else -1
        self.cat_steps = max(1, -(-abs(goal - start) // CAT_STEP_PX))
        self.cat_k = 0
        self.state = _CAT
        self._cat_next()

    def _cat_next(self):
        """One refresh of the cat walking: a step, in a new pose each time. After the last step one
        more with the cat sitting down; then the piece falls."""
        self.cat_k += 1
        k = self.cat_k
        self._new_frame()
        for i in self.landed:
            self.plan.draw_hollow(display.black, self.plan.pieces[i])
        if k <= self.cat_steps:
            self.cat_x = self.cat_from + (self.cat_goal - self.cat_from) * k // self.cat_steps
            _draw_cat_at(display.black, _CAT_WALK[k % 4], _CAT_WALK_RUMP, self.cat_x, self.cat_face)
        else:
            self.cat_x = self.cat_goal
            self._draw_cat()
            self.cat_ready = True
            self.state = _DROP
        self.seen = [False, False]
        self._draw_hud()
        self._request(_PART)

    def _wipe(self, then):
        """Clear the area between the two red bands with partial refreshes instead of a full
        one: all black for a refresh, then all white, which also takes the ghosts off. The
        bands are not driven, so they stay as they are."""
        top = self.banner.height
        rows = display_height - self.banner.foot - top
        if self.wipe_step == 0:
            display.black.fill_rect(0, top, display_width, rows, 1)
            self.wipe_step = 1
        else:
            self._new_frame()  # white between the bands
            self.wipe_step = 0
            self.state = then
        self._draw_hud()  # a new name shows as selected at once
        self._request(_PART)

    def _blink_leds(self):
        if time.ticks_diff(time.ticks_ms(), self.blink_ms) < BLINK_MS:
            return
        self.blink_ms = time.ticks_add(self.blink_ms, BLINK_MS)
        self.blink_step += 1
        if self.blink_step >= 2 * BLINK_COUNT:
            leds.fill((0, 0, 0))
            self._start_hold()
        else:
            leds.fill(BLINK_COLOR if self.blink_step % 2 == 0 else (0, 0, 0))

    def _blink_screen(self):
        # The name is up. Alternate blank and name, once per finished refresh.
        if self.blink_step >= 2 * BLINK_COUNT:
            self._start_hold()
            return
        shown = self.order if self.blink_step % 2 else []
        if self.fast:
            self.landed = shown
            self._show_fast([])
        else:
            self._show(shown)
        self.blink_step += 1

    def run(self):
        try:
            self._run()
        finally:
            # The task resumes when run() returns, so this is the heartbeat it checks. A
            # long run() (planning, a PNG decode) must not look like the app having stopped.
            self.beat = time.ticks_ms()

    def _run(self):
        self.beat = time.ticks_ms()
        if self.launched:
            leds.fill((0, 0, 0))
            self.failed = False
            self.need_full = True  # whatever was on the panel, draw the red bands afresh
            self._start_word(0)
            return

        if NAME_MENU:
            if UserA.pressed():  # the next name, whatever is going on
                leds.fill((0, 0, 0))
                self.seen[0] = True  # shows on the button circle at the next refresh
                print("User A: next name")
                self._start_word(self.word + 1)
            if UserB.pressed():
                if self.state == _DROP and self.fast:  # turns the piece at the next refresh
                    self.taps[1] += 1
                    self.last_side = 1
                    print("User B: turn piece")
                elif self.state != _CAT:  # (while the cat walks it does nothing)
                    leds.fill((0, 0, 0))
                    self._start_word(self.word)
        elif self.state == _CAT:
            UserA.pressed()  # the cat is walking: a press does nothing (and must not skip the name)
            UserB.pressed()
        elif self.state == _DROP and self.fast:
            # Presses wait for the next refresh, which turns the piece.
            if UserA.pressed():
                self.taps[0] += 1
                self.last_side = 0
                print("User A: turn left piece")
            if UserB.pressed():
                self.taps[1] += 1
                self.last_side = 1
                print("User B: turn right piece")
        elif UserA.pressed():
            leds.fill((0, 0, 0))
            self._start_word(self.word + 1)
        elif UserB.pressed():
            leds.fill((0, 0, 0))
            self._start_word(self.word)

        # A refresh in progress owns the framebuffers.
        if self.pending or not display.is_done_updating():
            return

        if self.frame_ms:
            print("refresh ms:", time.ticks_diff(time.ticks_ms(), self.frame_ms))
            self.frame_ms = 0

        if self.state == _CLEAR:
            if self.need_full:
                # The only full refresh, when the app starts: it draws the red bands,
                # which the partial refreshes then leave alone.
                self.screen_ready = False
                self._new_frame()
                self._full()
                self.need_full = False
                self.state = _DROP
            else:
                self._wipe(_DROP)  # a new name: wipe what is between the bands
        elif self.state == _DROP:
            if self.failed:
                # The partial refresh stopped working: the slideshow still works.
                print("Partial refresh stopped working, using the slideshow")
                self._start_word(self.word)
            elif self.batch < len(self.waves):
                if CAT and not self.cat_ready:
                    self._cat_begin()
                else:
                    self._drop_frame()
            else:
                self._start_blink()
        elif self.state == _BUILD:
            if self.frame < self.frames:
                self._show_frame()
            else:
                self._start_blink()
        elif self.state == _HOLD:
            if time.ticks_diff(time.ticks_ms(), self.hold_ms) >= HOLD_S * 1000:
                self._start_word(self.word if NAME_MENU else self.word + 1)
        elif self.state == _SLEEP:
            self._try_sleep()
        elif self.state == _CAT:
            self._cat_next()
        elif BLINK_MODE == "leds":
            self._blink_leds()
        else:
            self._blink_screen()
