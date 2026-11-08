"""Fast partial refresh for the B1 panel

display.update(fast=True, pulls=n) drives only the pixels that changed since the
last frame, with the short 400-byte waveform (data/rendered_luts.py, lutb_base)
instead of the panel's own ~34 s one. Black and white only: red is drawn as ink.

How it works, from the iTC97 driver reference:
* Each pixel's pair of plane bits (red, bw) picks a waveform table: 00 paper,
  01 ink, 11 drives nothing. Changed pixels get 00 or 01; every other pixel is
  sent as 11, so it holds. That is the partial update.
* The panel session stays open between frames. A frame then costs the plane
  transfer plus `pulls` bare 0x15 triggers of about 1.07 s each.
* One pull is a fraction of the full dose (the vendor uses three for solid
  black). Pixels driven with fewer than FULL_PULLS stay "dirty" and are driven
  again next frame, so the dose adds up and nothing is left grey.
* A session that has been idle for IDLE_MS is shut down by the display task.
* The first fast frame after a red or gray frame, or at boot when the panel
  content is unknown, is shown with one ordinary slow refresh first.

Reuses the helpers in lib.epd_grayscale (pull, shutdown) for the hardware steps.
"""

import asyncio as aio
import micropython
from micropython import const
import time

FRAME_BYTES = const(80640)
HALF_BYTES = const(40320)
FULL_PULLS = const(3)
IDLE_MS = const(2000)


@micropython.viper
def _copy(dst: ptr8, src: ptr8, count: int):
    for i in range(count):
        dst[i] = src[i]


@micropython.viper
def _fill(dst: ptr8, count: int, value: int):
    for i in range(count):
        dst[i] = value


@micropython.viper
def _ink(black: ptr8, red: ptr8, out: ptr8, count: int):
    # Red cannot be driven by the short waveform, so it is drawn as ink.
    for i in range(count):
        out[i] = black[i] | red[i]


@micropython.viper
def _planes(now: ptr8, prev: ptr8, dirty: ptr8, bw: ptr8, red: ptr8, keep_dirty: int):
    """Turn the wanted image into the two planes to send, and remember it.
    Changed or dirty pixels get their target: 00 paper, 01 ink. Others are 11, hold."""
    for i in range(80640):
        want = now[i]
        drive = (want ^ prev[i]) | dirty[i]
        hold = drive ^ 255
        bw[i] = hold | want
        red[i] = hold
        prev[i] = want
        if keep_dirty:
            dirty[i] = drive
        else:
            dirty[i] = 0


class _State:
    def __init__(self):
        # What the panel shows, as ink (1) over paper (0), in framebuffer order.
        self.prev = bytearray(FRAME_BYTES)
        # Pixels that have had a partial dose and are not settled yet.
        self.dirty = bytearray(FRAME_BYTES)
        # prev matches the panel and the panel holds only black and white.
        self.valid = False
        self.open = False
        self.last_ms = 0
        self.waveform = None
        # Scratch, allocated on first fast frame.
        self.now = None
        self.bw = None
        self.red = None
        self.halves = None


def state(display):
    st = display._fast
    if st is None:
        st = display._fast = _State()
    return st


def _scratch(st):
    if st.now is None:
        st.now = bytearray(FRAME_BYTES)
        st.bw = bytearray(FRAME_BYTES)
        st.red = bytearray(FRAME_BYTES)
        st.halves = tuple(bytearray(HALF_BYTES) for _ in range(4))


def _split(src, left, right):
    from lib.epd import _fast_split_and_reverse, _REVERSE_LUT
    _fast_split_and_reverse(src, left, right, _REVERSE_LUT)


async def leave(display, inexact):
    """Called by the display task before an ordinary refresh: record what it is
    about to show, and close the fast session. inexact: gray, so prev is unknown."""
    st = state(display)
    st.valid = not inexact
    if st.valid:
        _copy(st.prev, display._framebuffer_black, FRAME_BYTES)
    _fill(st.dirty, FRAME_BYTES, 0)
    if st.open:
        await close(display)


async def close(display):
    from lib.epd_grayscale import shutdown
    st = state(display)
    st.open = False
    try:
        await aio.wait_for(shutdown(display), 15)
    except Exception as ex:
        print("EPD fast: shutdown failed:", ex)
        display._panel_monochrome = False
        st.valid = False


async def idle_check(display):
    st = state(display)
    if st.open and time.ticks_diff(time.ticks_ms(), st.last_ms) > IDLE_MS:
        await close(display)


async def _promote(display, st):
    """One ordinary refresh, so the panel is black and white with known content."""
    print("EPD fast: promoting first frame to a full refresh")
    if st.open:
        await close(display)
    _scratch(st)
    _ink(display._framebuffer_black, display._framebuffer_red, st.now, FRAME_BYTES)
    bw_left, red_left, bw_right, red_right = st.halves
    _split(st.now, bw_left, bw_right)
    _fill(red_left, HALF_BYTES, 0)
    _fill(red_right, HALF_BYTES, 0)
    _copy(st.prev, st.now, FRAME_BYTES)
    _fill(st.dirty, FRAME_BYTES, 0)
    old = display._reverse_fb_bits
    display._reverse_fb_bits = False
    try:
        await display.global_update(bw_left, red_left, bw_right, red_right)
    finally:
        display._reverse_fb_bits = old
    st.valid = display._panel_monochrome


async def _open(display, st, halves):
    from data import rendered_luts
    if st.waveform is None:
        table = bytes(rendered_luts.lutb_base)
        if len(table) != 400:
            raise ValueError("Fast refresh requires the 400-byte B1 waveform")
        st.waveform = table
    await display._reset()
    display._send_images(*halves)
    await display.cog_initial()
    display._send_index_data(0xB0, st.waveform)
    await display._dcdc_soft_start()
    st.open = True


async def fast_update(display, pulls):
    from lib.epd_grayscale import pull
    st = state(display)
    try:
        if not (display._panel_monochrome and st.valid):
            await _promote(display, st)
            return
        _scratch(st)
        _ink(display._framebuffer_black, display._framebuffer_red, st.now, FRAME_BYTES)
        _planes(st.now, st.prev, st.dirty, st.bw, st.red, 1 if pulls < FULL_PULLS else 0)
        bw_left, red_left, bw_right, red_right = st.halves
        _split(st.bw, bw_left, bw_right)
        _split(st.red, red_left, red_right)
        old = display._reverse_fb_bits
        display._reverse_fb_bits = False  # Already reversed above.
        try:
            if st.open:
                display._send_images(bw_left, red_left, bw_right, red_right)
            else:
                await _open(display, st, st.halves)
        finally:
            display._reverse_fb_bits = old
        for _ in range(pulls):
            await pull(display)
        st.last_ms = time.ticks_ms()
    except Exception as ex:
        # Keep the display task alive. The next fast frame starts over with a
        # full refresh, since nothing is known about the panel now.
        print("EPD fast: update failed:", ex)
        display._panel_monochrome = False
        st.valid = False
        if st.open:
            await close(display)
