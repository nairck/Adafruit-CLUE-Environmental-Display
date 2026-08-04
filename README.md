# CLUE Environmental Display

A fast sensor dashboard for the [Adafruit CLUE](https://www.adafruit.com/product/4500), written in CircuitPython.
The 240 x 240 screen shows the room around you: temperature, humidity, air
pressure, sound level, a working compass, motion, and the screen's own
brightness, all colour coded and updating smoothly.

![Dashboard in three conditions](assets/dashboard.png)
*Left to right: a cold dry day at low pressure, typical indoor conditions, and
a hot humid day at high pressure. All three screens are simulated with this
repository's own display code.*

## What is on screen

| Row | Meaning |
|---|---|
| Direction | The compass direction you are facing, with degrees |
| Tmp | Temperature in deg C, coloured from white through blue and yellow to red |
| Hum | Relative humidity in percent, coloured from yellow through white and blue to purple |
| Pressure | Air pressure in kPa, same palette with its own scale |
| Loudness | Sound level in dB from the microphone |
| Brightness | The screen backlight level, set automatically from room light |
| Acceleration | Motion readout in green: the overall strength, then the signed x;y;z values |

## How the CLUE runs code

Plugged into a computer, the CLUE appears as a small USB drive named
CIRCUITPY. There is no upload step: the board simply runs the file named
`code.py` at the top level of that drive, and restarts on its own whenever
that file changes. Since only one file can have that name, only one program
is ever installed at a time, and this repository ships both of its programs
already named `code.py` (the dashboard at the top level, the calibration
tool in `calibration/`). Copying one onto the drive replaces the other, and
nothing ever needs renaming.

```
CIRCUITPY/
  code.py      the program that runs: the dashboard or the calibration tool
  lib/         the libraries listed below
```

## What you need

* An Adafruit CLUE with CircuitPython 7.0 or newer.
* These libraries from the [CircuitPython bundle](https://circuitpython.org/libraries),
  copied into `CIRCUITPY/lib`: `adafruit_clue`, `adafruit_apds9960`,
  `adafruit_bmp280`, `adafruit_sht31d`, `adafruit_lis3mdl`, `adafruit_lsm6ds`,
  `adafruit_display_text`, `adafruit_register`, `adafruit_bus_device`,
  `neopixel`.

## Setup

1. Copy the libraries above into `CIRCUITPY/lib`.
2. Copy this repository's `code.py` to the top level of CIRCUITPY. The
   dashboard starts by itself.
3. Calibrate the compass once (next section). Until then, every reading
   except the compass is already correct.

## Compass calibration

Every board carries a small constant magnetic field of its own, strong
enough to swamp the Earth's field, so the compass needs a one-minute
calibration before its numbers mean anything.

![Calibration converging](assets/mag_cal.png)
*Left to right: the start of a tumble, part-way through, and converged with
all three spans equal. Below: the offsets printed over serial as they settle.*

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

Each board needs its own offsets; numbers from one unit will not be right
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
Industries. See `LICENSE`.
