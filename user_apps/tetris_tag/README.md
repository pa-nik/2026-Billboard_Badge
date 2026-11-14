# Tetris Tag

Tetris Tag takes inspiration from Tetris to assemble your name on the badge. Use User A and B buttons to play!

Tetris-like pieces fall and stack up to spell a name along the bottom edge of
the screen, one at a time, and you steer them. The name blinks three times, stays up for
30 seconds, then the name is built again, and it loops forever. Each round starts with a black
cat that walks in from the side of the screen and sits down just below the banner; a piece falls
out of its rear, then the cat walks over to where the next piece goes, sits down there, and the
next piece falls (see "The cat"). This is the "FELIX" version, with "🐾 BARTRIS 🐾" in the banner
and no footer; put your own name in `NAMES` (see below).

Concept by the Soviet people, execution by [pa-nik](https://github.com/pa-nik) & Claude.

Controls:
```
User A (bottom left button): select the next name from the list in the left score panel
User B (bottom right button): turn the falling piece 90 degrees clockwise
Menu +/-: back to the app menu (as for every app)
```
The two top buttons are Menu -/+, which the badge firmware reserves for leaving an app, so
the game uses the two bottom ones (positions from the PCB layout in `hardware/billboard_pcb`).
User A selects the next name at any time (the round starts again, with the cat building it);
User B, outside a falling piece, restarts the current name. (`NAME_MENU = False` gives the
other versions' controls: two pieces, A turns the left one and B the right one, and between
names A skips to the next name.)

To install, run this from the root of the repo (the app also needs the newer display driver
and its two banner images; see Installing below):
```
mpremote cp firmware/badge/lib/epd.py :lib/epd.py
mpremote cp firmware/badge/lib/epd_partial.py :lib/epd_partial.py
mpremote cp firmware/badge/lib/large_png.py :lib/large_png.py
mpremote cp firmware/badge/data/rendered_luts.py :data/rendered_luts.py
mpremote cp user_apps/tetris_tag/tetris_banner.png :data/graphics/tetris_banner.png
mpremote cp user_apps/tetris_tag/tetris_tag.py :apps/tetris_tag.py
mpremote reset
```
Then select "Tetris Tag" from the menu.

## How to play

The three names, FELIX, SONYA and IRINA, are listed at the left of the banner on small labels:
the selected one black on white, the other two white on black. Press **User A** to select the next one (it cycles); the screen
is wiped, the cat walks in, and the selected name is built out of falling pieces. Press **User B**
to turn the falling piece: each press turns it 90 degrees clockwise at the next refresh.

One piece falls at a time, out of the cat. It appears just under the cat, turned a random
quarter turn, and falls about a row per refresh (about 0.65 s) **without turning** until you turn
it. When the piece is the right way up it drops into its place on the next refresh. A piece
is solid black while it falls, and it arrives at its place still solid black; one refresh later
it turns white with a black border, and then the cat walks to where the next piece goes. So
the name ends up as white letters with black borders. A piece you leave alone turns itself, 90 degrees a refresh by the shorter way, once it
reaches the auto-turn line (`AUTO_TURN_PCT`, and a little higher, see Where the name sits), so
the game plays itself if nobody presses. Buttons only count above that line.

## Make it your own

Edit the top of `tetris_tag.py`:

- `NAMES`: the names to build. It starts as `("FELIX", "SONYA", "IRINA")`: replace them with
  your own (the first three are listed in the left panel for User A to pick from; with
  `NAME_MENU = False` they are shown in turn instead). Only characters in `FONT` can be
  shown: the letters A to Z and a to z, é, the digits 0 to 9, and space. There is no punctuation yet:
  add a glyph to `FONT` for any other character (5 wide, 7 tall, `X` is a block). Long names
  get small blocks and take longer, since the pieces fall a fixed distance per refresh.
- `PIECES_AT_ONCE`, `SPAWN_PCT`, `FALL_PX`, `MIN_PRESS_FRAMES`, `AUTO_TURN_PCT`: how many pieces
  fall at a time (1 or 2; the two are picked far apart, one over the first word and one over the
  last words of the name, or, for a one-word name, at least 40% of its width apart), the screen
  height they start from, how far they fall each refresh in
  pixels (36: 3 rows for 12 px blocks, 1.8 for 20 px blocks, slowed to 1 here; larger is a faster game but leaves
  less time to press a button before the piece turns itself), the fewest refreshes a player is
  to get to turn a piece (the fall slows down to allow it), and the screen height where an
  unturned piece starts turning itself.
- `BLINK_MODE`, `BLINK_COUNT`, `BLINK_MS`: see below. `HOLD_S`: how long the finished name
  stays up after the blinking (30 s).
- `BANNER_PCT`, `BANNER_IMAGE`: the banner height and its image (see Banner).
- `FOOTER_PCT`, `FOOTER_IMAGE`, `BOTTOM_MARGIN`, `NAME_RISE_PCT`: the footer band at the bottom
  (0: none on this branch), its image, and where the name sits (see Footer).

## Footer

There is no footer on this branch: `FOOTER_PCT = 0`, so the whole screen below the banner is
white and the name has the room to itself. (`FOOTER_PCT = 25` brings back a red band across the
bottom 25% from `FOOTER_IMAGE`, a white-on-red picture made with `make_banner.py`, for example
`python3 make_banner.py --text "yourname.com" --pct 25 --size 72 --out footer.png`, copied to the
badge; the name then stands `BOTTOM_MARGIN` above it.)

### Where the name sits

The letters are built from 20 px blocks (`MAX_CELL`; it was 16, so they are 25% larger): "FELIX",
"SONYA" and "IRINA" are 29, 29 and 25 blocks wide, 580 px at most, and 7 blocks (140 px) tall.
With no footer the name sits `BOTTOM_MARGIN` above the bottom of the screen: 72 px, about 15% of
the screen height (100 px) lower than it was above the old 168 px footer (letters from y 460 to
600 of 672). The cat sits high, just under the banner, and the pieces come out below it (at
y 300), so they have about 160 px to fall and turn in. A piece has to be the right way up before
it reaches the name, so the line where an unturned piece starts turning itself (`AUTO_TURN_PCT`,
55% = row 18, 360 px) is as high as needs be, and the fall slows down when needed, in quarter rows
down to one row a refresh, so that a player gets at least `MIN_PRESS_FRAMES` (3) refreshes, about
2 s, to turn a piece: for these names the piece falls one row (20 px) a refresh and there are
3 refreshes to press. The larger blocks only fit with this margin and an auto-turn line of 55%:
with a margin of 75 px or the line at 50% a player would get one refresh. `NAME_RISE_PCT` lifts
the name and leaves less time.

### Score boards

At each end of the top banner is a panel: **User A on the left, User B on the right**. Both are
the red band with white lettering, and the right one is placed so that its outer margin to the
screen edge (14 px) equals the left one's.

**Left (User A): the names.** Only User A's button part is kept (the big A
and two circles drawn like the two buttons on that side of the badge, one above the other: an
outline for the menu button and a filled circle for the User button), moved up to the top edge
of the screen, as User B's is on the right (`_BTN_UP`); there is no `USER` text above them any more. Beside it the three names
are set in the game's own block letters (small: 2.8 px blocks), each on its own label, one
above the other: the selected name black on a white label and the other two white on black
labels. User A's button cycles through them. A black dot appears in the middle of
the filled circle on the refresh after the button is pressed (and stays while it is held), so
you can see that the badge noticed the press. The refresh takes about 0.65 s, so the dot lags
the press a little.

**Right (User B): the score.** It keeps the score of the falling pieces for the whole game:

- `SCORE`: 10 points for each piece that lands, 10 more if the player turned it right way up
  themselves before it started turning itself, and 100 for the piece that finishes a letter
  (the letters finished are still counted for that bonus, but there is no `LINES` display);
- `NEXT`, under the score: the piece that will come down after the one that is falling (or
  being walked to);
- the big B and its two button circles, with the same press dot (User B turns the piece).

The score starts again from 0 with each name. (`NAME_MENU = False` brings back the two-panel
layout with `SCORE`, `LINES` and `NEXT` on each side.)

In the middle at the top, a timer in `MM:SS` (white on black) shows the time since the first piece started to
fall; it stops when the last piece lands. There is no level, as nothing speeds up. The numbers use
the same block font as the name, so the digits 0 to 9 and the colon are in it.
`SCOREBOARD = False` (or a banner smaller than the full 25%) leaves the banner without them.

**Why the names are on labels:** a name cannot be white lettering on the red and then become black
on a white background when it is selected: the partial refresh cannot turn red pixels into anything
else, and the red under a white label could never come back. So every name has its own label that
is not red from the start (the full refresh leaves it black or white), and the partial refresh only
swaps the colours: white label with black letters for the selected name, black label with white
letters for the others, like the timer.

**Why the numbers sit in white boxes:** red can only be drawn by the ~36 s full refresh; the fast
partial refresh can only switch pixels between black and white, and a pixel that has been made
white (or black) cannot be turned back to red by it. White digits on a red background would
therefore need a full refresh every time a number changes. So the lettering and the
background are drawn once, by the full refresh at launch, and everything that changes (the three
numbers and the next piece) is black in a small white box that the partial refresh can
redraw. The timer is the other way round, white digits on a black box: a black background works
just as well as a white one, because the box is not red (the full refresh leaves it black) and the
partial refresh only has to switch its pixels between black and white. Only those boxes are ever
changed after launch, so the red is never touched.

## The cat

At the start of each round (after the wipe, or after the one full refresh when the app is
launched) a black cat walks in from the nearer side of the screen to the place where the first
piece will land, a step and a new pose each refresh, and sits down just below the banner (its top
is `CAT_GAP_PX`, 8 px, under it). Then **one piece** falls out of its rear, straight down to its
place in the name. When it has landed the cat gets up and walks over to the place where the next
piece goes, sits down there, and that piece falls, and so on until the name is built. The cat
faces the way it walked, so it turns round when the next place is to its left. It stays where it
sat for the last piece while the name is held, and is wiped with the rest of the field before the
next round, when it walks in again.

Because only one piece falls, User B turns it (User A selects the name, even while the cat is
walking, which starts the round again). While the cat is walking User B does nothing.

The cat is black on white, drawn into the black plane between the red banner and the bottom of
the screen, so it is just more pixels for the partial refresh (the red is never touched, and
nothing has to be installed: the pictures are in `tetris_tag.py`). `CAT = False` leaves it out
and the pieces appear at `SPAWN_PCT` (one at a time while `NAME_MENU` is on, else two, as in the other versions). The cat only
exists on the partial-refresh path, not in the slideshow fallback.

The pictures are drawn with `#` in the `_CAT_WALK` (four walking poses) and `_CAT_SIT` tables in
`tetris_tag.py`, which are easy to edit; `CAT_SCALE` (6) is how many screen pixels a `#` is (the
sitting cat is 114 x 108 px, the walking one 162 x 96), `CAT_STEP_PX` (72) how far it walks each
refresh. They are my own pixel art, in the style of black pixel-art cat silhouettes, not a copy of
any image. A bigger cat would leave fewer than 3 refreshes to press a button.

The files `faberrgen/`, `make_faberrgen.py`, `make_faberrgen_psd.py` and `psd_text.py` belong to
the Faberrgen screen of the main branch, which this branch does not show; they are not used here.

## Banner

A red banner runs across the top 25% of the screen, with "🐾 BARTRIS 🐾" in white
Helvetica Bold centred in it, low in the band under the timer and between the two score boards
(see Score boards), so the lettering is smaller than the band would allow. Pieces fall in the
space below it.

The lettering is an image, `tetris_banner.png`, not text drawn by the badge: the badge
has no Helvetica, and its built-in font has neither Cyrillic nor the hammer and sickle.
`make_banner.py` makes it on your computer:

```
pip install pillow fonttools
python3 make_banner.py --text "🐾 BARTRIS 🐾" --pct 25 --margin 190 --height-fraction 0.42 --drop 18   # tetris_banner.png (88 px letters)
python3 make_banner.py --text "HELLO" --pct 25 --margin 190 --height-fraction 0.42 --drop 18
mpremote cp tetris_banner.png :data/graphics/tetris_banner.png
```

It sets the text in the Helvetica Bold that ships with macOS, which has the Cyrillic
and Latin letters. Helvetica has no hammer and sickle, so that one glyph comes from a
fallback font (Apple Symbols by default, thickened a little to match the bold letters;
`--symbol-font` picks another). Emoji, such as the paw prints, come from Apple Color Emoji
(colour pictures only, so their outline is used, as a white shape as tall as the capitals).
Only the rendered shapes end up in the PNG, no font file.
`--margin 190` keeps the lettering between the score boards, `--drop 18` moves it down under
the timer, and `--size N` forces a font size. `BANNER_PCT` in
`tetris_tag.py` and `--pct` must agree (25% is 168 px). If the image
is not on the badge, the banner is a plain red band.

The panel can only make red with a full refresh, so the banner is drawn once, by
the one full refresh when the app is launched (about 36 s, the first LED blinks red), and the partial
refreshes then leave it untouched.

## Partial refresh

The panel's own refresh takes about 30 s, which is no use for animation. This app uses the
partial refresh driver `firmware/badge/lib/epd_partial.py` (`PartialEPD`), which redraws only
the pixels that changed, in about 0.65 s a frame (measured on a badge: median 629 ms):

1. When the app is launched there is one normal full refresh to a blank field with the red
   bands (about 36 s). Each new name after that starts with a partial wipe of the field
   instead: all black for one refresh, then all white (about 1.5 s), which also takes most
   ghosting off. The app opens its partial session on top of what the full refresh drew
   (`PartialEPD.start()` would flash the panel white first, which would also wipe the red
   bands, so the app has its own `start_keep`). The partial pulls only touch the pixels around
   what changed, so the bands are not driven.
2. The pieces then fall (one at a time with the cat, see The cat). A fall is one refresh to show the
   pieces, a few more while they fall and turn, one to drop each into place (still solid black) and
   one more to turn it white with a black border. A square,
   which looks the same turned, is never turned and drops straight away.
   Pieces are two to four blocks, with no single-block pieces. A piece normally joins blocks
   edge to edge, like a real Tetris piece, but where a letter needs it (the diagonal strokes
   of K, N, R, V, Y) a piece may join two blocks that touch only at a corner, a shape the real
   game does not have. The splitter prefers real shapes and fewer pieces. A block with nothing
   around it at all, such as the dot of a lowercase i, would still be alone; none of the
   built-in letters in the default name do that.
3. A background task owns the panel while the app runs, as in the Pong app: it hands the panel
   back about 2.5 s after you leave the app and powers it down after 2 s without changes.
   The LEDs only blink at the end of a name.

Ghosting: partial refreshes leave light ghosts that build up; the black-then-white wipe at the
start of each name takes most of them off, and a full refresh (relaunch the app) takes off all.

Red pieces were tried (falling red, then one extra refresh to turn black) and did not work
on a partial refresh: it is black and white by design and cannot make a good red on this
panel. The red bands are unaffected: they are not driven.

Speed. Each refresh takes about 0.65 s, which is the driver's floor, so the length of a pass
depends on how many refreshes it needs. A round of "FELIX" is 19 pieces, one after the other, each
with a walk of the cat to its place (up to about 13 refreshes the first time, usually a few) and
a fall of up to 12 refreshes: in simulation 95 to 120 s from the wipe to the finished name with
some button presses (a piece you turn right way up early drops sooner). The app prints `refresh ms:`
over serial after every frame, so you can see the real times.

If the badge is not a B1 panel, or the firmware does not have `epd_partial.py`, or the partial
refresh stops working, the app falls back to a slideshow of full refreshes, one per snapshot,
with the pieces in the air in red. The slideshow does not turn the pieces.

## Blinking and holding

The paper cannot refresh in half a second, so `BLINK_MODE = "leds"` (the default)
keeps the finished name on the paper and blinks the LED bar, half a second on and
half a second off, three times. `BLINK_MODE = "screen"` blinks the paper itself
(name, blank, name...), but each step is at least one drive step, so it is much slower.

When the blinking is over the finished name stays on the screen, untouched, for `HOLD_S`
seconds (30), then the next round starts with a partial wipe and the cat walks in again, building
the same name (the selection stays until User A changes it). User A starts the next name right
away and User B, between pieces, restarts the current one.

## Installing

The commands at the top copy the app, the banner image and the display files it needs.
The app needs the newer display driver on the badge as well as the app itself. Badges that
shipped with older firmware are missing `rendered_luts.py`, which the partial refresh uses, and
an updated `epd.py` (it has the display lock) and `large_png.py`, which `epd_partial.py` relies on. `mpremote ls :lib :data` shows
what is on the badge. After the first install only `tetris_tag.py` changes, so
`mpremote cp user_apps/tetris_tag/tetris_tag.py :apps/tetris_tag.py` and a reset is enough.

Alternatively, `python scripts/update.py push` from `firmware/` brings the whole badge up
to date, but it deletes anything on the badge that is not in `firmware/badge/`,
including this app, so copy the app again afterwards.
