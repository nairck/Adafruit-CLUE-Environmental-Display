# CLUE Environmental Display

A fast sensor dashboard for the [Adafruit CLUE](https://www.adafruit.com/product/4500), written in CircuitPython.
The 240 x 240 screen shows the environment around you: temperature, humidity, air
pressure, sound level, a working compass, motion, and brightness, all colour coded and updating smoothly.

<p align="center">
  <img src="assets/dashboard.png" alt="Dashboard in three conditions">
<p align="center"><em>Left to right: a cold dry day at low pressure; typical indoor conditions; and a hot humid day at high pressure.</em></p>

## What is on screen

| Row | Meaning |
|---|---|
| Direction | The compass direction you are facing, with degrees |
| Tmp | Temperature in deg C, coloured from white through blue and yellow to red |
| Hum | Relative humidity in percent, coloured from yellow through white and blue to purple |
| Pressure | Air pressure in kPa, same palette with its own scale |
| Loudness | Sound level in dB from the microphone |
| Brightness | The screen backlight level, set automatically from measured ambient light |
| Acceleration | Motion readout in green: the overall magnitude, then the signed x;y;z values |

## How the CLUE runs code

Plugged into a computer, the CLUE appears as a small USB drive named
CIRCUITPY. There is no upload step: the board simply runs the file named
`code.py` at the top level of that drive, and restarts on its own whenever
that file changes. Since only one file can have that name, only one program
is ever installed at a time, and this repository ships both of its programs
already named `code.py`: the dashboard, kept both at the top level and in
`dashboard/`, and the calibration tool in `calibration/`. Copying one onto
the drive replaces the other, and nothing ever needs renaming. The
`dashboard/` and `calibration/` folders sit side by side so either program
is always one copy away; the top-level `code.py` is the same file as
`dashboard/code.py`.

```
CIRCUITPY/
  code.py      the program that runs: the dashboard or the calibration tool
  lib/         the libraries included in this repository
```

## What you need

* An Adafruit CLUE running CircuitPython 7.0 or newer.
* The libraries in this repository's `lib/` folder. They are the exact
  working set from Adafruit's MIT-licensed
  [library bundle](https://circuitpython.org/libraries), so nothing needs
  downloading; on a much newer CircuitPython, fetch the same libraries from
  the bundle built for that version.

## Setup

1. Copy this repository's `lib` folder to the top level of CIRCUITPY.
2. Copy this repository's `code.py` to the top level of CIRCUITPY. The
   dashboard starts by itself.
3. Calibrate the compass once (next section). Until then, every reading
   except the compass is already correct.

## Compass calibration

Every board carries a small constant magnetic field of its own, strong
enough to swamp the Earth's field, so the compass needs a one-minute
calibration before its readings mean anything.

<p align="center">
  <img src="assets/mag_cal.png" alt="Calibration converging">
<p align="center"><em>Left to right: the start of a tumble; part-way through; and converged with all three spans equal. Below: the offsets printed over serial as they settle.</em></p>

1. Copy `calibration/code.py` to the top level of CIRCUITPY. It replaces
   the dashboard, since the two share the name, and starts by itself.
2. Away from metal and cables, slowly tumble the board through every
   orientation. The three `s` numbers show how much of the field each axis
   has seen; you are done when they roughly agree, around 95 to 110.
3. Press B to freeze, and note the three `o` numbers on the screen: those
   are your offsets. Over a serial console the tool also prints them as a
   ready-to-paste `MAG_OFFSET = (...)` line.
4. In your copy of the dashboard `code.py`, set `MAG_OFFSET` to those three
   numbers, then copy the file back onto the drive. It replaces the
   calibration tool, and the compass now reads correctly. Optional: set
   `MAG_HEADING_OFFSET` to your local magnetic declination so it shows true
   north rather than magnetic north.

Each board needs its own offsets; numbers from one unit are likely incorrect
on another.

## How the compass works

The heading combines the magnetometer with the accelerometer, so tilting the
board does not swing the number, and the forward direction is taken from the
screen itself rather than from the sensor chip. Whatever `display.rotation`
is set to, the display shows the direction a person reading the screen is
facing. If a future board revision ever reads a constant quarter turn off,
adjust the single constant `SCREEN_UP_R0` in `code.py`.

## Tuning

The main knobs, all named constants at the top of `code.py`:

| Constant | What it does |
|---|---|
| `TEMP_STOPS`, `HUM_STOPS`, `PRESS_STOPS` | The values where each colour sits |
| `RAMP_COLORS`, `HUM_PRESS_COLORS` | The colours themselves, any RGB values, any count |
| `MAG_OFFSET`, `MAG_HEADING_OFFSET` | Compass calibration and declination |
| `LIGHT_DARK`, `LIGHT_BRIGHT` | Room-light levels for minimum and maximum backlight |
| `SOUND_DB_OFFSET` | Shifts the dB scale; trim against a reference meter |
| `TEMP_OFFSET` | Corrects the board's self-heating |
| `clue_display[...].y` block | The pixel position of every line |

## License

MIT, based on the original Adafruit CLUE example by ladyada for Adafruit
Industries. The `lib/` folder contains unmodified libraries from the Adafruit
CircuitPython bundle, which are also MIT licensed. See `LICENSE`.
