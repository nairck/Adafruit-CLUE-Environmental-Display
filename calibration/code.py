# SPDX-FileCopyrightText: 2026 Adam B. Johnson
# SPDX-License-Identifier: CC-BY-NC-4.0
#
# Magnetometer hard-iron calibration tool for the Adafruit CLUE.
#
# Usage: this file is already named code.py in the repository's calibration
# folder. Copy it to the top level of the CIRCUITPY drive, where it replaces
# the dashboard and starts on its own; copy the dashboard's code.py back
# when done. Slowly tumble the board through every orientation, well away
# from cables, desk frames, and laptops. Include steep attitudes: the field
# here dips about 70 degrees below horizontal, so full coverage means
# turning the board over and pitching it nose down toward north, not just
# spinning it flat. Best run on battery; if USB stays attached, keep the
# cable slack from moving with the board.
#
# Method: offset per axis = (min + max) / 2 of everything seen. That
# midpoint is only correct once each axis has pointed both directly along
# and directly against the Earth's field, so the convergence metric is the
# span (max minus min) per axis: done when all three spans agree within a
# few uT, at about twice the local total field (roughly 95 to 110 here).
#
# Screen, per axis: o = offset estimate, s = span so far.
# |B|r / |B|c: raw and offset-corrected field magnitude. Converged and
# clean, |B|c sits near-constant in any orientation.
# hdg: level-board heading from the corrected components on the raw
# sensor axes, without the dashboard's screen-referenced forward axis or
# its MAG_HEADING_OFFSET, so expect it to differ from the dashboard.
#
# Buttons: A clears the collection and resumes live sampling. B freezes the
# numbers for copying into MAG_OFFSET in the dashboard; the offset line
# also prints to serial once per second in paste-ready form.

import time
from math import atan2, degrees, sqrt

from adafruit_clue import clue

BTN_LOCKOUT = 0.2   # s, contact-bounce lockout per button

d = clue.simple_text_display(text_scale=2, colors=(clue.WHITE,))

mins = [1e9, 1e9, 1e9]
maxs = [-1e9, -1e9, -1e9]
frozen = False
prev_a = False
prev_b = False
btn_a_time = -1.0
btn_b_time = -1.0
last_print = 0.0
last_paint = 0.0
n = 0

d[0].text = "MAG CAL: tumble me"
d[6].text = "spans equal = done"
d[7].text = "A:reset B:freeze"
d.show()

while True:
    now = time.monotonic()
    a_now = clue.button_a
    b_now = clue.button_b
    if a_now and not prev_a and (now - btn_a_time) > BTN_LOCKOUT:
        btn_a_time = now
        mins = [1e9, 1e9, 1e9]
        maxs = [-1e9, -1e9, -1e9]
        frozen = False
        n = 0
    if b_now and not prev_b and (now - btn_b_time) > BTN_LOCKOUT:
        btn_b_time = now
        frozen = not frozen
    prev_a = a_now
    prev_b = b_now

    m = clue.magnetic
    if not frozen:
        n += 1
        for i in range(3):
            if m[i] < mins[i]:
                mins[i] = m[i]
            if m[i] > maxs[i]:
                maxs[i] = m[i]

    if now - last_paint > 0.25:
        last_paint = now
        off = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
        spans = tuple(maxs[i] - mins[i] for i in range(3))
        cx = m[0] - off[0]
        cy = m[1] - off[1]
        cz = m[2] - off[2]
        mag_raw = sqrt(m[0] * m[0] + m[1] * m[1] + m[2] * m[2])
        mag_cal = sqrt(cx * cx + cy * cy + cz * cz)
        hdg = degrees(atan2(-cx, cy)) % 360.0
        d[1].text = "x o{:7.1f} s{:6.1f}".format(off[0], spans[0])
        d[2].text = "y o{:7.1f} s{:6.1f}".format(off[1], spans[1])
        d[3].text = "z o{:7.1f} s{:6.1f}".format(off[2], spans[2])
        d[4].text = "|B|r{:6.1f} c{:6.1f}".format(mag_raw, mag_cal)
        d[5].text = "hdg {:5.1f}".format(hdg)
        d[8].text = "FROZEN" if frozen else "live  n={}".format(n)

    if now - last_print > 1.0:
        last_print = now
        off = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
        spans = tuple(maxs[i] - mins[i] for i in range(3))
        print("MAG_OFFSET = ({:.2f}, {:.2f}, {:.2f})   spans ({:.1f}, {:.1f}, {:.1f})".format(
            off[0], off[1], off[2], spans[0], spans[1], spans[2]))

    time.sleep(0.002)
