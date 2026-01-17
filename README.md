# swingsaber v1.1

**Interactive lightsaber controller for Adafruit HalloWing M4 Express**

![CircuitPython](https://img.shields.io/badge/CircuitPython-10.x-blueviolet.svg)
![Version](https://img.shields.io/badge/version-1.1-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Originally by:** [John Park (Adafruit Industries)](https://learn.adafruit.com/hallowing-lightsaber)
**Enhanced by:** William C. Chesher

---

## What Is This?

An interactive lightsaber controller that turns the HalloWing M4 into a fully-functional lightsaber with:

- **Motion Detection**: Swing and hit detection via 3-axis accelerometer
- **LED Blade**: 60-pixel RGBW NeoPixel strip with color animations
- **Sound System**: 4 complete themes with PWM audio
- **Touch Controls**: Power, theme switching, battery status
- **Reliable**: Error handling and resource management

Based on the [Adafruit HalloWing Lightsaber guide](https://learn.adafruit.com/hallowing-lightsaber) by John Park.

---

## Quick Start

### Parts Needed

**Required:**
- [Adafruit HalloWing M4 Express](https://www.adafruit.com/product/4300)
- [NeoPixel Strip RGBW (60 pixels)](https://www.adafruit.com/product/2842) with 3-pin JST connector
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
| **RIGHT (D4)** | Long press | Cycle brightness presets (15%/25%/35%) |
| **LEFT (D3)** | Tap (OFF) | Cycle theme |
| **LEFT (D3)** | Tap (ON) | Power off, then cycle theme |
| **LEFT (D3)** | Long press | Cycle volume presets (30/50/70/100%) |
| **A3** | Tap | Show battery status |
| **A3** | Long press | Volume up (+10%) |
| **A4** | Tap | Show battery status |
| **A4** | Long press | Volume down (-10%) |

### Themes

1. **Jedi** (Blue) - Classic lightsaber
2. **Powerpuff** (Magenta) - Bubbly effects
3. **Rick & Morty** (Green) - Portal gun sounds
4. **SpongeBob** (Yellow) - Underwater saber

### Motion Detection

Uses delta-based acceleration (change between readings) for responsive detection:

- **Swing** (delta >15): Bright blade + swing sound
- **Hit** (delta >40): Flash white + clash sound
- **Idle**: Gentle breathing animation + hum loop

Watch console output to tune: `delta: 5.2 (swing>15 hit>40)`

---

## Features

✅ **Motion & LED System**
- 3-axis accelerometer motion detection
- 60-pixel RGBW NeoPixel blade animations
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
    # Themes - colors are RGBW format: (Red, Green, Blue, White)
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255, 0),   "hit_color": (255, 255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255, 0), "hit_color": (0, 200, 255, 0)},
        {"name": "ricknmorty", "color": (0, 255, 0, 0),   "hit_color": (255, 0, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0, 0), "hit_color": (255, 255, 255, 255)},
    ]

    # Motion sensitivity (delta-based, lower = more sensitive)
    SWING_THRESHOLD = 15            # Swing detection
    HIT_THRESHOLD = 40              # Hit/clash detection

    # Brightness presets (long-press RIGHT to cycle)
    BRIGHTNESS_PRESETS = [0.15, 0.25, 0.35]
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.25

class SaberConfig:
    NUM_PIXELS = 60                 # Match your NeoPixel strip
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
- Lower thresholds (try SWING_THRESHOLD = 10)
- Verify MSA311 library installed

### No Audio
- Verify sound files in `/sounds/` folder
- Check format: 22050Hz, 16-bit, mono WAV
- Verify speaker connections
- Check serial console for errors

### LEDs Not Working
- Verify `NUM_PIXELS = 60` matches your strip
- Check NeoPixel connector is plugged in
- Try changing `pixel_order` in code (GRBW for RGBW strips)
- Ensure adequate power (5V, ~1A for 60 RGBW pixels)

### Battery Percentage Wrong
- Check `BATTERY_MIN_VOLTAGE` and `BATTERY_MAX_VOLTAGE` in code
- Verify voltage divider matches your board
- Some boards don't have battery monitoring

---

## Project Structure

```
SwingSaber/
├── code.py                        # Main code (~1650 lines)
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

### v1.1 (2025-01-17)
- Upgraded to 60-pixel RGBW NeoPixel strips
- Added brightness presets (long-press RIGHT)
- Added volume presets (long-press LEFT)
- Added volume fine-tune (long-press A3/A4)
- Delta-based motion detection (more responsive)
- Onboard NeoPixel animations (breathing, chase, flash)
- Persistent settings (theme, volume, brightness saved to NVM)

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
4. Open issue: https://github.com/wchesher/SwingSaber/issues

---

**⚔️ May the Force be with you! ⚔️**
