# HalloWing M4 Lightsaber v1.0

**Interactive lightsaber controller for Adafruit HalloWing M4 Express**

![CircuitPython](https://img.shields.io/badge/CircuitPython-10.x-blueviolet.svg)
![Version](https://img.shields.io/badge/version-1.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Originally by:** [John Park (Adafruit Industries)](https://learn.adafruit.com/hallowing-lightsaber)
**Enhanced by:** William C. Chesher

---

## What Is This?

An interactive lightsaber controller that turns the HalloWing M4 into a fully-functional lightsaber with:

- **Motion Detection**: Swing and hit detection via 3-axis accelerometer
- **LED Blade**: 30-pixel NeoPixel strip with color animations
- **Sound System**: 4 complete themes with PWM audio
- **Touch Controls**: Power, theme switching, battery status
- **Reliable**: Error handling and resource management

Based on the [Adafruit HalloWing Lightsaber guide](https://learn.adafruit.com/hallowing-lightsaber) by John Park.

---

## Quick Start

### Parts Needed

**Required:**
- [Adafruit HalloWing M4 Express](https://www.adafruit.com/product/4300)
- [NeoPixel Strip 0.5m (30 pixels)](https://www.adafruit.com/product/1376) with 3-pin JST connector
- [Mini Oval Speaker (8Ω 1W)](https://www.adafruit.com/product/3923)
- [LiPo Battery 3.7V 500mAh](https://www.adafruit.com/product/1578) (or larger)
- USB-C cable for programming

**Optional:**
- PVC pipe or lightsaber hilt
- Mounting hardware
- Diffuser material for blade

**Total Cost:** ~$60-80 (excluding hilt)

### Installation

#### 1. Install CircuitPython

Download and install CircuitPython 10.x on your HalloWing M4:
- [CircuitPython for HalloWing M4](https://circuitpython.org/board/hallowing_m4_express/)

#### 2. Install Required Libraries

Download the [CircuitPython 10.x Library Bundle](https://circuitpython.org/libraries).

Copy these libraries to `/lib/` on your `CIRCUITPY` drive:
- `adafruit_msa3xx.mpy`
- `neopixel.mpy`
- `adafruit_display_text/` (folder)

#### 3. Deploy Code

Copy `code.py` to the root of your `CIRCUITPY` drive:
```bash
cp code.py /Volumes/CIRCUITPY/code.py
```

#### 4. Add Sound Files

Create a `/sounds/` folder and add WAV files for each theme (0-3):

**File naming:** `[theme]on.wav`, `[theme]off.wav`, `[theme]idle.wav`, `[theme]swing.wav`, `[theme]hit.wav`, `[theme]switch.wav`

Example for theme 0:
```
CIRCUITPY/
└── sounds/
    ├── 0on.wav      # Power on sound
    ├── 0off.wav     # Power off sound
    ├── 0idle.wav    # Idle hum (looped)
    ├── 0swing.wav   # Swing sound
    ├── 0hit.wav     # Clash sound
    └── 0switch.wav  # Theme change sound
```

Repeat for themes 1, 2, and 3 (24 files total).

**Audio specs:**
- Format: WAV (uncompressed PCM)
- Sample rate: 22050 Hz
- Bit depth: 16-bit signed
- Channels: Mono

#### 5. Add Theme Images (Optional)

Create an `/images/` folder and add BMP files:
```
CIRCUITPY/
└── images/
    ├── 0logo.bmp    # Theme 0 logo (128x128)
    ├── 1logo.bmp
    ├── 2logo.bmp
    └── 3logo.bmp
```

#### 6. Connect Hardware

1. Connect NeoPixel strip to HalloWing M4 NeoPixel connector (3-pin JST)
2. Connect speaker to speaker output terminals
3. Connect LiPo battery to battery JST connector
4. Power on!

---

## How to Use

### Touch Controls

| Button | Action | Function |
|--------|--------|----------|
| **RIGHT (D4)** | Tap | Power lightsaber ON/OFF |
| **LEFT (D3)** | Tap (OFF) | Cycle theme |
| **LEFT (D3)** | Tap (ON) | Power off, then cycle theme |
| **A3/A4** | Tap | Show battery status |

### Themes

1. **Jedi** (Blue) - Classic lightsaber
2. **Powerpuff** (Magenta) - Bubbly effects
3. **Rick & Morty** (Green) - Portal gun sounds
4. **SpongeBob** (Yellow) - Underwater saber

### Motion Detection

- **Swing** (>140 m²/s²): Bright blade + swing sound
- **Hit** (>220 m²/s²): Flash white + clash sound
- **Idle**: Gentle animation + hum loop

---

## Features

✅ **Motion & LED System**
- 3-axis accelerometer motion detection
- 30-pixel NeoPixel blade animations
- Power on/off animations
- Color blending during effects
- Adaptive brightness (idle vs. active)

✅ **Audio System**
- 4 complete themes
- Power on/off sounds
- Looping idle hum
- Swing and clash sounds
- Theme switch confirmation

✅ **Touch Interface**
- Power on/off
- Theme switching
- Battery status display
- Debounced inputs

✅ **Power Management**
- Battery monitoring
- USB detection
- Adaptive loop delays
- Display timeout
- Power saving modes

✅ **Reliability**
- Error handling
- State machine validation
- Memory management
- Resource cleanup
- Diagnostic logging

---

## Configuration

Edit `code.py` to customize:

```python
class UserConfig:
    DISPLAY_BRIGHTNESS = 0.3        # Display brightness
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3 # LED brightness
    ENABLE_DIAGNOSTICS = True       # Serial debug output

class SaberConfig:
    NUM_PIXELS = 30                 # NeoPixel count
    SWING_THRESHOLD = 140           # Swing sensitivity
    HIT_THRESHOLD = 220             # Hit sensitivity

    # Themes (add/modify as needed)
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255),   "hit_color": (255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255), "hit_color": (0, 200, 255)},
        {"name": "ricknmorty", "color": (0, 255, 0),   "hit_color": (255, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0), "hit_color": (255, 255, 255)},
    ]
```

---

## Troubleshooting

### Device Won't Boot
- Check battery charge
- Try USB power instead
- Verify CircuitPython 10.x installed correctly
- Boot into safe mode (hold button during power on)
- Check serial console for errors

### No Motion Detection
- Check serial console for "Accelerometer OK"
- Lower thresholds (try SWING_THRESHOLD = 80)
- Verify MSA311 library installed

### No Audio
- Verify sound files in `/sounds/` folder
- Check format: 22050Hz, 16-bit, mono WAV
- Verify speaker connections
- Check serial console for errors

### LEDs Not Working
- Verify `NUM_PIXELS = 30` matches your strip
- Check NeoPixel connector is plugged in
- Try changing `pixel_order` in code (GRB vs RGB)
- Ensure adequate power (5V, ~500mA for 30 pixels)

### Battery Percentage Wrong
- Check `BATTERY_MIN_VOLTAGE` and `BATTERY_MAX_VOLTAGE` in code
- Verify voltage divider matches your board
- Some boards don't have battery monitoring

---

## Project Structure

```
swingsaber/
├── code.py                        # Main code (1355 lines)
├── LICENSE                        # MIT License
├── README.md                      # This file
├── DEPLOYMENT.md                  # Deployment checklist
│
├── sounds/                        # User-provided WAV files
│   ├── 0on.wav                    # Theme 0 power on
│   ├── 0off.wav
│   ├── 0idle.wav
│   ├── 0swing.wav
│   ├── 0hit.wav
│   ├── 0switch.wav
│   └── ... (24 files total)
│
└── images/                        # Optional theme logos
    ├── 0logo.bmp
    ├── 1logo.bmp
    ├── 2logo.bmp
    └── 3logo.bmp
```

---

## Version History

### v1.0 (2025-01-02)
- Initial stable release
- 4 theme support
- Motion detection (swing/hit)
- Touch controls
- Battery monitoring
- Error handling & resource management

---

## Credits

**Original Code:** [John Park / Phillip Burgess (Adafruit Industries)](https://learn.adafruit.com/hallowing-lightsaber)
**v1.0 Enhancements:** William C. Chesher
**CircuitPython:** Adafruit Industries and contributors

---

## License

MIT License - See [LICENSE](LICENSE) file

Copyright (c) 2021 Phillip Burgess for Adafruit Industries
Copyright (c) 2024-2025 William C. Chesher

---

## Links

- **Original Guide**: https://learn.adafruit.com/hallowing-lightsaber
- **HalloWing M4**: https://www.adafruit.com/product/4300
- **CircuitPython**: https://circuitpython.org/
- **Library Bundle**: https://circuitpython.org/libraries

---

## Support

**Need help?**
1. Check troubleshooting section above
2. Connect to serial console for detailed errors
3. See original guide: https://learn.adafruit.com/hallowing-lightsaber
4. Open issue: https://github.com/wchesher/swingsaber/issues

---

**⚔️ May the Force be with you! ⚔️**
