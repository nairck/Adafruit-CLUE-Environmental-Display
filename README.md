# CLUE Environmental Display

A fast sensor dashboard for the [Adafruit CLUE](https://www.adafruit.com/product/4500), written in CircuitPython.
The 240 x 240 screen shows the environment around you: temperature, humidity, air
pressure, sound level, a working compass, motion, and brightness, all colour coded and updating smoothly.

<p align="center">
  <img src="assets/dashboard.png" alt="Dashboard in three conditions">
</p>
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
that file changes. The `dashboard/` and `calibration/` folders provide both programs; the top-level `code.py` is by default the same file as
`dashboard/code.py`.

```
CIRCUITPY/
  code.py               the program the CLUE runs, a copy of dashboard/code.py
  dashboard/code.py     the dashboard
  calibration/code.py   the compass calibration tool
  lib/                  the libraries from this repository
```

## What you need

* An Adafruit CLUE running CircuitPython 7.0 or newer (boards ship with it installed).
* The files and folders in the list above, all in this repository, libraries included.
* Optional: an editor with a serial console, such as Mu, to read the calibration printout.

## Setup

1. Open the CIRCUITPY drive and clear it. The board recreates its own
   housekeeping files, such as `boot_out.txt`; ignore those.
2. Copy the files and folders in the list above onto the drive.
3. The dashboard starts by itself. Calibrate the compass once (next
   section); until then, every reading except the compass is correct.

## Compass calibration

Every board carries a small constant magnetic field of its own, strong
enough to contaminate the Earth's field, so the compass needs a one-time
calibration before its readings mean anything.

<p align="center">
  <img src="assets/mag_cal.png" alt="Calibration converging">
</p>
<p align="center"><em>Left to right: the start of a tumble; part-way through; and converged with all three spans equal. Below: the offsets printed over serial as they settle.</em></p>

1. Copy `calibration/code.py` to the top level of CIRCUITPY, replacing the
   dashboard. The tool starts by itself.
2. Away from metal and cables, slowly tumble the board through every
   orientation. The three `s` numbers are the field span each axis has
   seen; you are done when all three roughly agree, around 95 to 110.
3. Press B to freeze. The three `o` numbers on screen are your offsets;
   a serial console shows the same values as a ready-to-paste
   `MAG_OFFSET = (...)` line, printed once per second.
4. Enter the offsets in `dashboard/code.py` under `MAG_OFFSET`, then copy
   that file to the top level, replacing the calibration tool.
5. Align the heading: point the CLUE and a phone compass in the same
   direction, and add the difference, phone reading minus CLUE reading,
   to `MAG_HEADING_OFFSET`.

Each board needs its own offsets; they unfortunately do not transfer.

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
| `MAG_OFFSET`, `MAG_HEADING_OFFSET` | Compass calibration and heading alignment |
| `LIGHT_DARK`, `LIGHT_BRIGHT` | Room-light levels for minimum and maximum backlight |
| `SOUND_DB_OFFSET` | Shifts the dB scale; trim against a reference meter |
| `TEMP_OFFSET` | Corrects the board's self-heating |
| `clue_display[...].y` block | The pixel position of every line |

## License

Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0): share and
adapt with credit, no commercial use. Everything in `lib/` remains MIT
licensed by Adafruit Industries. See `LICENSE`.
