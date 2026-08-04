# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
#
# Adafruit CLUE sensor dashboard.
#
# Shows temperature, humidity, pressure, a tilt-compensated compass heading,
# and acceleration, with per-quantity colour ramps and an ambient-light
# driven backlight with manual button trim.
#
# Design:
#   * Static layout (scales, colours, positions) is set once. The first
#     paint fills every line in reading order, top to bottom, with auto
#     refresh on, so the screen builds visibly at startup; the main loop
#     then takes manual control of refresh.
#   * A label is touched only when its rendered string or colour changes;
#     glyph re-rendering is the display's true rate limit.
#   * Fast path, every pass: accelerometer and magnetometer reads, filters,
#     and buttons.
#   * Slow path: temperature, humidity, and pressure are read round robin,
#     one per sub-tick, so the worst-case frame hitch is one sensor
#     conversion (the SHT31-D humidity read blocks about 15 ms), not three.
#   * Ambient light is polled non-blocking via the sensor's data-ready flag.
#   * Loudness: short PDM microphone blocks on a fixed cadence; each block's
#     power is exponentially averaged (sound-level-meter fast weighting) and
#     shown in dB.
#   * display.refresh() runs manually, and only when something changed.

import array
import time
from math import atan2, cos, degrees, log, radians, sin, sqrt

import audiobusio
import board
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_clue import clue

try:
    from ulab import numpy as np   # C-speed microphone block power
except ImportError:
    np = None                      # pure-Python fallback in block_power

# ----------------------------------------------------------------------------
# Colour ramps. Temperature: white -> sky blue -> yellow -> red
# (RAMP_COLORS). Humidity and pressure: yellow -> white -> sky blue ->
# purple (HUM_PRESS_COLORS), each quantity with its own stop values.
# Stops are strictly increasing, one per colour: at or below the first stop
# the colour saturates to the first colour, at or above the last stop to
# the last colour, and in between it blends linearly within each segment.
# Blending happens in linear light (gamma decode, mix, re-encode) so
# midpoints do not go muddy. Colours are arbitrary RGB tuples, and the ramp
# handles any count: add a fifth stop and colour to any quantity for finer
# structure.
# ----------------------------------------------------------------------------
TEMP_STOPS = (0.0, 15.0, 25.0, 30.0)        # deg C
HUM_STOPS = (0.0, 10.0, 60.0, 100.0)        # %RH
PRESS_STOPS = (97.0, 101.0, 102.0, 103.0)   # kPa

SKY_BLUE = (0, 191, 255)   # deep sky blue: ramps, Dir line, default colour
GREEN = (0, 255, 0)   # acceleration header and components lines

RAMP_COLORS = (
    (255, 255, 255),   # white
    SKY_BLUE,          # sky blue
    (255, 255, 0),     # yellow
    (255, 0, 0),       # red
)

HUM_PRESS_COLORS = (
    (255, 255, 0),     # yellow
    (255, 255, 255),   # white
    SKY_BLUE,          # sky blue
    (3, 57, 248),      # purple
)
RAMP_GAMMA = 2.2

# ----------------------------------------------------------------------------
# Cadence. The fast sensors are read every pass regardless; these control how
# often labels are rewritten and how often the slow sensors are polled.
# ----------------------------------------------------------------------------
FAST_DISPLAY_PERIOD = 0.02   # s between fast label rewrites
SLOW_SENSOR_PERIOD = 0.5     # s per-quantity period for temp / humidity / pressure
LIGHT_POLL_PERIOD = 0.10     # s between checks of the light data-ready flag

# ----------------------------------------------------------------------------
# Filters. EMA with coefficient a = dt / (tau + dt): a first-order low-pass
# with cutoff fc = 1 / (2 pi tau), independent of the loop rate.
# ----------------------------------------------------------------------------
ACCEL_TAU = 0.10     # s, display smoothing for acceleration
HEADING_TAU = 0.10   # s, applied to the magnetometer field components; the
                     # heading comes from the filtered vector, so there is
                     # no 0/360 wrap artifact
GRAV_TAU = 0.5       # s, gravity-direction EMA for tilt compensation
GRAV_TOL = 0.30      # accept accel samples within this fraction of 1 g
ACC_G = 9.81         # m/s^2, gate reference for the gravity filter

# ----------------------------------------------------------------------------
# Magnetometer calibration. MAG_OFFSET is the per-unit hard-iron offset in
# uT, measured with the calibration tool (calibration/code.py in this
# repository) and subtracted from all three raw field
# components; the tilt compensation uses the full corrected vector. The
# offset vector competes with the roughly 16 uT horizontal Earth field at
# this latitude, so the heading is meaningless without it.
# MAG_HEADING_OFFSET is added to the final heading in degrees, wrapped mod
# 360. It is the one alignment knob: point the board and a trusted compass
# (a phone works) in the same direction, then add their difference,
# reference minus displayed, to this constant. The single number absorbs
# the magnetometer's mounting yaw, the choice of forward edge, and any
# true-versus-magnetic difference in the reference.
# ----------------------------------------------------------------------------
MAG_OFFSET = (-6.83, 18.31, 23.68)   # uT, from the calibration tool
MAG_HEADING_OFFSET = 160.0           # deg; set against a reference compass

# ----------------------------------------------------------------------------
# Screen-referenced heading. The compass forward axis follows the screen,
# not the raw sensor axes: forward is the diagonal between the screen's up
# direction for the current display.rotation (positive clockwise, viewed
# from the front) and the direction out the back of the screen. The bearing
# of that axis is the direction the reader faces, and it is the same
# whether the board lies flat like a hand compass or stands upright in
# front of the eyes, blending smoothly between the two holds.
# SCREEN_UP_R0 is the sensor-frame x, y of screen-up at display rotation 0.
# After changing display.rotation, verify the heading against a reference
# compass and trim MAG_HEADING_OFFSET if needed.
# ----------------------------------------------------------------------------
SCREEN_UP_R0 = (-1.0, 0.0)

# ----------------------------------------------------------------------------
# Microphone loudness. A short PDM block is recorded every SOUND_POLL_PERIOD
# and its mean-square power (about its own mean, which removes DC) is
# exponentially averaged with LOUD_TAU, the 0.125 s "fast" time weighting of
# a sound level meter, then shown as dB. SOUND_DB_OFFSET maps counts to an
# approximate dB SPL from the microphone's nominal -26 dBFS at 94 dB SPL
# sensitivity; the path is uncalibrated to a few dB, so trim it against a
# reference meter if absolute numbers matter. SOUND_BLOCK samples at 16 kHz
# set the blocking cost per poll (64 samples = 4 ms).
# ----------------------------------------------------------------------------
SOUND_POLL_PERIOD = 0.05   # s between microphone blocks
SOUND_BLOCK = 64           # samples per block at 16 kHz
LOUD_TAU = 0.125           # s, exponential time weighting of the power
SOUND_DB_OFFSET = 30.0     # dB, counts-to-SPL offset (nominal, trimmable)
LN10 = 2.302585092994046   # dB uses natural log; log10 is not in every build

# ----------------------------------------------------------------------------
# Backlight. Auto level comes from the APDS9960 clear channel: BRIGHTNESS_MIN
# at or below LIGHT_DARK counts, BRIGHTNESS_MAX at or above LIGHT_BRIGHT
# counts, linear in between. Buttons add a manual offset in steps of
# (range / BRIGHT_BTN_STEPS): A down, B up, edge triggered (one step per
# press, no holding). A+B together clears the offset back to pure auto.
# Clear-channel counts scale with integration time and gain, so calibrate
# LIGHT_DARK / LIGHT_BRIGHT using the debug line noted in the loop.
# ----------------------------------------------------------------------------
BRIGHTNESS_MIN = 0.03
BRIGHTNESS_MAX = 1.00
BRIGHT_BTN_STEPS = 4
LIGHT_DARK = 8           # clear counts at or below this: BRIGHTNESS_MIN
LIGHT_BRIGHT = 800       # clear counts at or above this: BRIGHTNESS_MAX
LIGHT_INTEGRATION = 10   # APDS9960 integration cycles, 2.78 ms each
LIGHT_GAIN = 1           # 0..3 -> 1x, 4x, 16x, 64x
BRIGHT_TAU = 0.4         # s, glide for light-driven changes (buttons act instantly)
BTN_LOCKOUT = 0.15       # s, contact-bounce lockout per button

TEMP_OFFSET = -6.0       # deg C, board self-heating correction
PRESS_TO_KPA = 0.1       # hPa to kPa

# ----------------------------------------------------------------------------
# Layout: line indices on the simple_text_display grid (text_scale=1 pitch).
# Indices are unique handles; on-screen position comes from the explicit
# pixel block below, so index order need not match screen order.
# ----------------------------------------------------------------------------
MAG_LOC = 1
TEMP_LOC = 3
TEMP_NUM_LOC = 4
HUM_LOC = 8
HUM_NUM_LOC = 9
PRESS_LOC = 12
BRIGHT_LOC = 16
LOUD_LOC = 14
ACC_HDR_LOC = 15
ACC_LOC = 17
LABEL_SCALE = 3
NUM_SCALE = 5
LINE_SCALE = 2

# ----------------------------------------------------------------------------
# Display setup: everything static happens exactly once.
# ----------------------------------------------------------------------------
display = board.DISPLAY
display.rotation = 90

# Compass forward axis for this screen orientation (see SCREEN_UP_R0).
_r = radians(display.rotation)
FWD = (SCREEN_UP_R0[0] * cos(_r) + SCREEN_UP_R0[1] * sin(_r),
       -SCREEN_UP_R0[0] * sin(_r) + SCREEN_UP_R0[1] * cos(_r),
       -1.0)

clue.sea_level_pressure = 1013.25   # only affects clue.altitude

clue_display = clue.simple_text_display(text_scale=1, colors=(SKY_BLUE,))

clue_display[MAG_LOC].scale = LINE_SCALE
clue_display[MAG_LOC].color = SKY_BLUE
clue_display[TEMP_LOC].scale = LABEL_SCALE
clue_display[TEMP_NUM_LOC].scale = NUM_SCALE
clue_display[HUM_LOC].scale = LABEL_SCALE
clue_display[HUM_NUM_LOC].scale = NUM_SCALE
clue_display[PRESS_LOC].scale = LINE_SCALE
clue_display[BRIGHT_LOC].scale = LINE_SCALE
clue_display[LOUD_LOC].scale = LINE_SCALE
clue_display[ACC_HDR_LOC].color = GREEN
clue_display[ACC_HDR_LOC].scale = LINE_SCALE
clue_display[ACC_LOC].color = GREEN
clue_display[ACC_LOC].scale = LINE_SCALE

# Explicit pixel positions, one line each, independently adjustable.
# simple_text_display rows are 13 px apart starting at y = 3; each comment
# gives that line's neutral grid position as a fixed reference, and the
# literal is the actual position, so any line can be dialled without
# touching the others. Dir (row 1 = 16) and the accel values (row 17 = 224)
# stay on their grid rows and are not listed.
clue_display[TEMP_LOC].y = 40        # grid row 3 = 42
clue_display[TEMP_NUM_LOC].y = 53    # grid row 4 = 55
clue_display[HUM_LOC].y = 92         # grid row 8 = 107
clue_display[HUM_NUM_LOC].y = 105    # grid row 9 = 120
clue_display[PRESS_LOC].y = 143      # grid row 12 = 159
clue_display[LOUD_LOC].y = 164       # grid row 14 = 185
clue_display[BRIGHT_LOC].y = 183     # grid row 16 = 211
clue_display[ACC_HDR_LOC].y = 204    # grid row 15 = 198

# Ambient light: a second driver instance on the shared I2C bus, because the
# clue singleton does not expose its own APDS9960. clue.color / gesture /
# proximity must then stay unused. Property names per adafruit_apds9960 3.x.
apds = APDS9960(board.I2C())
apds.enable_color = True
apds.integration_time = LIGHT_INTEGRATION
apds.color_gain = LIGHT_GAIN

# Microphone: the loop pulls short blocks from a PDMIn instance. Some
# adafruit_clue versions claim the PDM pins themselves at import time, so
# own the instance when the pins are free and borrow the singleton's when
# they are not.
try:
    mic = audiobusio.PDMIn(
        board.MICROPHONE_CLOCK,
        board.MICROPHONE_DATA,
        sample_rate=16000,
        bit_depth=16,
    )
except ValueError:
    mic = clue._mic
mic_buf = array.array("H", [0] * SOUND_BLOCK)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
_last_text = {}
_last_color = {}


def set_text(idx, text):
    """Assign label text only if it changed. Returns True if it did."""
    if _last_text.get(idx) != text:
        _last_text[idx] = text
        clue_display[idx].text = text
        return True
    return False


def set_color(idx, color):
    """Assign label colour only if it changed. Returns True if it did."""
    if _last_color.get(idx) != color:
        _last_color[idx] = color
        clue_display[idx].color = color
        return True
    return False


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def acc_text(v):
    """One signed acceleration component, always six characters wide:
    three decimals below 10, two at or above. The switch sits at 9.9995,
    where the three-decimal form rounds to 10.000."""
    if -9.9995 < v < 9.9995:
        return "{:+.3f}".format(v)
    return "{:+.2f}".format(v)


def block_power(buf):
    """Mean-square power of one microphone block about its own mean."""
    if np is not None:
        a = np.array(buf)
        a = a - np.mean(a)
        return np.mean(a * a)
    mean = sum(buf) / len(buf)
    acc = 0.0
    for v in buf:
        d = v - mean
        acc += d * d
    return acc / len(buf)


def ramp_color(value, stops, colors=RAMP_COLORS):
    """Piecewise-linear colour ramp, gamma-correct blend, saturating ends."""
    if value <= stops[0]:
        return colors[0]
    if value >= stops[-1]:
        return colors[-1]
    i = 0
    while value >= stops[i + 1]:
        i += 1
    t = (value - stops[i]) / (stops[i + 1] - stops[i])
    c0 = colors[i]
    c1 = colors[i + 1]
    inv_g = 1.0 / RAMP_GAMMA
    out = []
    for k in range(3):
        lo = (c0[k] / 255.0) ** RAMP_GAMMA
        hi = (c1[k] / 255.0) ** RAMP_GAMMA
        out.append(int(255.0 * ((lo + (hi - lo) * t) ** inv_g) + 0.5))
    return tuple(out)


# Cardinal names for 30-degree sectors, indexed by int(heading // 30) % 12.
# Repeated entries give the four cardinals 60-degree bands and the
# intercardinals 30-degree bands.
CARDINALS = (
    "  North   ", " North-East", "  East    ", "  East    ",
    " South-East", "  South   ", "  South   ", " South-West",
    "  West    ", "  West    ", " North-West", "  North   ",
)

filt_mx = None
filt_my = 0.0
filt_mz = 0.0
grav_x = None
grav_y = 0.0
grav_z = 0.0


def get_heading(dt, ax, ay, az):
    """Tilt-compensated, screen-referenced compass heading.

    The gravity direction is a slow EMA of the accelerometer (GRAV_TAU),
    updated only while |a| is within GRAV_TOL of 1 g, so shakes and swings
    do not masquerade as tilt. The hard-iron corrected, filtered field
    vector is projected onto the plane perpendicular to gravity through
    east = m x u and north = u x east with u the unit up vector, and the
    heading is the bearing of the FWD axis in that plane, increasing
    clockwise like a compass. The displayed number is therefore the
    direction the reader faces, identical for a flat hold and an upright
    hold and smooth in between; at display rotation 90 with the board
    level it reduces exactly to atan2(-mx, my).
    The bearing is undefined only when FWD itself goes vertical, attitudes
    45 degrees beyond flat that lie outside any reading hold. Filtering
    the components rather than the angle avoids any 0/360 wrap artifact.
    """
    global filt_mx, filt_my, filt_mz, grav_x, grav_y, grav_z
    mx, my, mz = clue.magnetic
    mx -= MAG_OFFSET[0]
    my -= MAG_OFFSET[1]
    mz -= MAG_OFFSET[2]
    if filt_mx is None:
        filt_mx = mx
        filt_my = my
        filt_mz = mz
    else:
        k = dt / (HEADING_TAU + dt)
        filt_mx += k * (mx - filt_mx)
        filt_my += k * (my - filt_my)
        filt_mz += k * (mz - filt_mz)
    if grav_x is None:
        if sqrt(ax * ax + ay * ay + az * az) < 0.5 * ACC_G:
            grav_x, grav_y, grav_z = 0.0, 0.0, ACC_G   # implausible seed
        else:
            grav_x, grav_y, grav_z = ax, ay, az
    else:
        norm = sqrt(ax * ax + ay * ay + az * az)
        if ACC_G * (1.0 - GRAV_TOL) < norm < ACC_G * (1.0 + GRAV_TOL):
            k = dt / (GRAV_TAU + dt)
            grav_x += k * (ax - grav_x)
            grav_y += k * (ay - grav_y)
            grav_z += k * (az - grav_z)
    gn = sqrt(grav_x * grav_x + grav_y * grav_y + grav_z * grav_z)
    if gn < 1e-6:
        gn = 1e-6   # only reachable transiently mid-flip; avoids div by zero
    ux = grav_x / gn
    uy = grav_y / gn
    uz = grav_z / gn
    ex = filt_my * uz - filt_mz * uy
    ey = filt_mz * ux - filt_mx * uz
    ez = filt_mx * uy - filt_my * ux
    nx = uy * ez - uz * ey
    ny = uz * ex - ux * ez
    nz = ux * ey - uy * ex
    f_east = FWD[0] * ex + FWD[1] * ey + FWD[2] * ez
    f_north = FWD[0] * nx + FWD[1] * ny + FWD[2] * nz
    heading = (degrees(atan2(f_east, f_north)) + MAG_HEADING_OFFSET) % 360.0
    return CARDINALS[int(heading // 30) % 12], heading


def update_temp_labels():
    color = ramp_color(temperature, TEMP_STOPS)
    changed = set_color(TEMP_LOC, color)
    changed |= set_color(TEMP_NUM_LOC, color)
    changed |= set_text(TEMP_NUM_LOC, "   {:.1f}".format(temperature))
    return changed


def update_hum_labels():
    color = ramp_color(humidity, HUM_STOPS, HUM_PRESS_COLORS)
    changed = set_color(HUM_LOC, color)
    changed |= set_color(HUM_NUM_LOC, color)
    changed |= set_text(HUM_NUM_LOC, "   {:.1f}".format(humidity))
    return changed


def update_press_label():
    changed = set_color(PRESS_LOC, ramp_color(pressure, PRESS_STOPS, HUM_PRESS_COLORS))
    changed |= set_text(PRESS_LOC, "Pressure: {:.2f} kPa".format(pressure))
    return changed


def snap_brightness():
    """Jump the backlight to the current target immediately (button feel)."""
    global bright_now, last_set_bright
    bright_now = clamp(auto_bright + manual_offset, BRIGHTNESS_MIN, BRIGHTNESS_MAX)
    last_set_bright = bright_now
    display.brightness = bright_now


# ----------------------------------------------------------------------------
# Backlight state, needed before the first paint for the Brightness line.
# ----------------------------------------------------------------------------
BRIGHT_RANGE = BRIGHTNESS_MAX - BRIGHTNESS_MIN
BRIGHT_STEP = BRIGHT_RANGE / BRIGHT_BTN_STEPS

auto_bright = 0.25       # replaced by the first light reading
manual_offset = 0.0
bright_now = 0.25
last_set_bright = bright_now
display.brightness = bright_now
light_clear = 0

# ----------------------------------------------------------------------------
# First paint, strictly top to bottom in reading order. auto_refresh is still
# on here, so each line appears on screen as it is built. Colours are set
# before each line's text so nothing flashes in the default colour. This is
# also where the accel, heading, and loudness filters take their initial
# samples.
# ----------------------------------------------------------------------------
clue_display.show()

ax, ay, az = clue.acceleration
cardinal, heading = get_heading(0.0, ax, ay, az)
set_text(MAG_LOC, "  {} ({:.0f})".format(cardinal, heading))

temperature = clue.temperature + TEMP_OFFSET
set_color(TEMP_LOC, ramp_color(temperature, TEMP_STOPS))
clue_display[TEMP_LOC].text = "Tmp:        C"
update_temp_labels()

humidity = clue.humidity
set_color(HUM_LOC, ramp_color(humidity, HUM_STOPS, HUM_PRESS_COLORS))
clue_display[HUM_LOC].text = "Hum:        %"
update_hum_labels()

pressure = clue.pressure * PRESS_TO_KPA
update_press_label()

pct = bright_now * 100.0
fmt = ("Brightness: {:.3f} %" if pct < 9.9995 else
       "Brightness: {:.2f} %" if pct < 99.995 else "Brightness: {:.1f} %")
set_text(BRIGHT_LOC, fmt.format(pct))

mic.record(mic_buf, len(mic_buf))
sound_power = block_power(mic_buf)
sound_prev = time.monotonic()
loud_db = 10.0 * log(sound_power if sound_power > 1.0 else 1.0) / LN10 + SOUND_DB_OFFSET
set_text(LOUD_LOC, "Loudness: {:.3f} dB".format(loud_db))

filt_ax, filt_ay, filt_az = ax, ay, az
amag = sqrt(filt_ax * filt_ax + filt_ay * filt_ay + filt_az * filt_az)
fmt = "Acceleration ({:.2f})" if amag >= 9.9995 else "Acceleration ({:.3f})"
set_text(ACC_HDR_LOC, fmt.format(amag))
set_text(ACC_LOC, acc_text(filt_ax) + ";" + acc_text(filt_ay) + ";" + acc_text(filt_az))

display.auto_refresh = False

last_time = time.monotonic()
next_fast_disp = last_time
next_slow = last_time + SLOW_SENSOR_PERIOD / 3.0
next_light = last_time
next_sound = last_time
slow_phase = 0
prev_a = False
prev_b = False
btn_a_time = -1.0
btn_b_time = -1.0

# ----------------------------------------------------------------------------
# Main loop (no sleep: the loop is paced by the work itself)
# ----------------------------------------------------------------------------
while True:
    now = time.monotonic()
    dt = now - last_time
    last_time = now
    dirty = False

    # Buttons: edge triggered, one step per press, no hold-repeat.
    a_now = clue.button_a
    b_now = clue.button_b
    if a_now and b_now:
        if manual_offset != 0.0:
            manual_offset = 0.0   # both buttons: back to pure auto
            snap_brightness()
    else:
        if a_now and not prev_a and (now - btn_a_time) > BTN_LOCKOUT:
            btn_a_time = now
            manual_offset = clamp(manual_offset - BRIGHT_STEP, -BRIGHT_RANGE, BRIGHT_RANGE)
            snap_brightness()
        if b_now and not prev_b and (now - btn_b_time) > BTN_LOCKOUT:
            btn_b_time = now
            manual_offset = clamp(manual_offset + BRIGHT_STEP, -BRIGHT_RANGE, BRIGHT_RANGE)
            snap_brightness()
    prev_a = a_now
    prev_b = b_now

    # Ambient light: non-blocking, consume a sample only when one is ready.
    if now >= next_light:
        next_light = now + LIGHT_POLL_PERIOD
        if apds.color_data_ready:
            light_clear = apds.color_data[3]
            if light_clear <= LIGHT_DARK:
                auto_bright = BRIGHTNESS_MIN
            elif light_clear >= LIGHT_BRIGHT:
                auto_bright = BRIGHTNESS_MAX
            else:
                auto_bright = BRIGHTNESS_MIN + BRIGHT_RANGE * (
                    (light_clear - LIGHT_DARK) / (LIGHT_BRIGHT - LIGHT_DARK)
                )

    # Microphone: one short block per poll (SOUND_BLOCK / 16 kHz of blocking),
    # energy-averaged in the power domain with the dt-normalized LOUD_TAU.
    if now >= next_sound:
        next_sound = now + SOUND_POLL_PERIOD
        mic.record(mic_buf, len(mic_buf))
        dtp = now - sound_prev
        sound_prev = now
        k = dtp / (LOUD_TAU + dtp)
        sound_power += k * (block_power(mic_buf) - sound_power)
        loud_db = 10.0 * log(sound_power if sound_power > 1.0 else 1.0) / LN10 + SOUND_DB_OFFSET

    # Glide the backlight toward auto + manual (button presses jump instantly
    # in snap_brightness). Deadband so the PWM is not rewritten every pass.
    target = clamp(auto_bright + manual_offset, BRIGHTNESS_MIN, BRIGHTNESS_MAX)
    bright_now += (dt / (BRIGHT_TAU + dt)) * (target - bright_now)
    if abs(bright_now - last_set_bright) > 0.004:
        last_set_bright = bright_now
        display.brightness = bright_now

    # Fast sensors: read every pass so the filters see the full sample rate.
    # The filters are seeded during the first paint.
    ax, ay, az = clue.acceleration
    a = dt / (ACCEL_TAU + dt)
    filt_ax += a * (ax - filt_ax)
    filt_ay += a * (ay - filt_ay)
    filt_az += a * (az - filt_az)
    cardinal, heading = get_heading(dt, ax, ay, az)

    # Fast labels: rewritten at most every FAST_DISPLAY_PERIOD, and only when
    # the rendered string changed. Glyph re-rendering is the true rate limit.
    if now >= next_fast_disp:
        next_fast_disp = now + FAST_DISPLAY_PERIOD
        amag = sqrt(filt_ax * filt_ax + filt_ay * filt_ay + filt_az * filt_az)
        fmt = "Acceleration ({:.2f})" if amag >= 9.9995 else "Acceleration ({:.3f})" # from 9.9995 the 3 dp form rounds to "10.000" and would overflow
        dirty |= set_text(ACC_HDR_LOC, fmt.format(amag))
        dirty |= set_text(ACC_LOC, acc_text(filt_ax) + ";" + acc_text(filt_ay) + ";" + acc_text(filt_az))
        dirty |= set_text(MAG_LOC, "  {} ({:.0f})".format(cardinal, heading))
        pct = bright_now * 100.0
        fmt = ("Brightness: {:.3f} %" if pct < 9.9995 else
               "Brightness: {:.2f} %" if pct < 99.995 else "Brightness: {:.1f} %")
        dirty |= set_text(BRIGHT_LOC, fmt.format(pct))
        dirty |= set_text(LOUD_LOC, "Loudness: {:.3f} dB".format(loud_db))
        # To calibrate LIGHT_DARK / LIGHT_BRIGHT, swap the Brightness line
        # for this variant; the shorter prefix keeps the line inside the
        # 240 px panel width at scale 2:
        # dirty |= set_text(BRIGHT_LOC, "Bright: {:.2f} L:{}".format(bright_now, light_clear))

    # Slow sensors: one per sub-tick, each quantity every SLOW_SENSOR_PERIOD.
    if now >= next_slow:
        next_slow = now + SLOW_SENSOR_PERIOD / 3.0
        if slow_phase == 0:
            temperature = clue.temperature + TEMP_OFFSET
            dirty |= update_temp_labels()
        elif slow_phase == 1:
            humidity = clue.humidity
            dirty |= update_hum_labels()
        else:
            pressure = clue.pressure * PRESS_TO_KPA
            dirty |= update_press_label()
        slow_phase = (slow_phase + 1) % 3

    if dirty:
        display.refresh()
