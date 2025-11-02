# HalloWing M4 Lightsaber v4.0

**Production-grade lightsaber controller for Adafruit HalloWing M4 Express**

![CircuitPython](https://img.shields.io/badge/CircuitPython-7.x--9.x-blueviolet.svg)
![Version](https://img.shields.io/badge/version-4.0-green.svg)
![Status](https://img.shields.io/badge/status-production-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Originally by:** [John Park (Adafruit Industries)](https://learn.adafruit.com/hallowing-lightsaber)
**Enhanced by:** William C. Chesher

---

## What Is This?

An interactive lightsaber controller that turns the HalloWing M4 into a fully-functional lightsaber with:

- **Motion Detection**: Swing and hit detection via 3-axis accelerometer
- **LED Blade**: 30-pixel NeoPixel strip with color animations
- **Sound System**: 4 complete themes with PWM audio
- **Touch Controls**: Power, theme switching, battery/volume
- **Bulletproof**: Production-grade error handling and resource management

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

Download and install CircuitPython 7.x, 8.x, or 9.x on your HalloWing M4:
- [CircuitPython for HalloWing M4](https://circuitpython.org/board/hallowing_m4_express/)

#### 2. Install Required Libraries

Download the [CircuitPython Library Bundle](https://circuitpython.org/libraries) matching your CircuitPython version.

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

**Need help optimizing audio?** See `README_AUDIO.md`

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
| **LEFT (D3)** | Hold 1s | Cycle volume preset |
| **A3/A4** | Tap | Show battery status |
| **A3** | Hold 1s | Increase volume |
| **A4** | Hold 1s | Decrease volume |

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

### v4.0 Titanium Edition

✅ **Bulletproof Reliability**
- Fixed critical acceleration bug (3D magnitude)
- Proper file handle management (no leaks)
- Non-blocking audio fade
- Comprehensive error handling
- State machine validation
- Memory management (LRU cache, GC)

✅ **Premium Audio System**
- Software volume control (10-100%)
- Volume presets & gestures
- Crossfade support (50ms)
- Click/pop prevention
- Audio optimization tools
- Hardware upgrade guides

✅ **Power Management**
- Battery monitoring
- Adaptive brightness
- Idle mode (50ms loop delay)
- Display timeout
- Periodic garbage collection

✅ **Production Quality**
- 1355 lines of code
- 20+ error handlers
- 43 named constants
- Comprehensive documentation
- Diagnostic logging
- Hardware status reporting

---

## Configuration

Edit `code.py` to customize:

```python
class UserConfig:
    DISPLAY_BRIGHTNESS = 0.3        # Display brightness
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3 # LED brightness
    DEFAULT_VOLUME = 70             # Audio volume (10-100%)
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

## Audio Optimization

### Quick Audio Setup

```bash
# Install dependencies
pip install pydub numpy

# Optimize audio files (creates 3 volume levels)
python audio_processor.py sounds/ --all --volumes 30 60 100
```

**Result:** Clean, consistent audio with no clicks/pops

### Volume Control Options

| Method | Cost | Real-time | Quality |
|--------|------|-----------|---------|
| **File-based** (current) | Free | ❌ | ⭐⭐⭐⭐ |
| **Hardware pot** | $2 | ✅ | ⭐⭐⭐⭐⭐ |
| **I2S DAC** | $7 | ✅ | ⭐⭐⭐⭐⭐ |

See `README_AUDIO.md` and `AUDIO_OPTIMIZATION_GUIDE.md` for complete details.

---

## Troubleshooting

**No motion detection?**
- Check serial console for "Accelerometer OK"
- Lower thresholds (try SWING_THRESHOLD = 80)
- Verify MSA311 library installed

**No audio?**
- Verify sound files in `/sounds/` folder
- Check format: 22050Hz, 16-bit, mono WAV
- Run `python audio_processor.py sounds/ --all`
- Verify speaker connections

**LEDs wrong color?**
- Verify `NUM_PIXELS = 30` matches your strip
- Try changing `pixel_order=neopixel.RGB` in code
- Check NeoPixel power (needs 5V)

**Volume doesn't change?**
- This is expected! PWM audio has no native volume control
- Process audio files: `python audio_processor.py sounds/ --all --volumes 30 60 100`
- Update code to load volume-specific files (see README_AUDIO.md)
- Or add hardware potentiometer ($2)

See comprehensive troubleshooting in main README.

---

## Project Structure

```
swingsaber/
├── code.py                        # Main firmware (1355 lines)
├── LICENSE                        # MIT License
├── README.md                      # This file
├── DEPLOYMENT.md                  # Deployment checklist
├── README_AUDIO.md                # Audio quick reference
├── AUDIO_OPTIMIZATION_GUIDE.md    # Complete audio guide
├── audio_processor.py             # Audio optimization tool
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

### v4.0 Titanium Edition + Premium Audio (2025-01-02)
- Premium audio system with volume control
- Audio processor tool for optimization
- Comprehensive audio documentation
- Hardware upgrade recommendations

### v3.0 Titanium Edition (2025-01-02)
- Fixed critical acceleration bug
- Bulletproof error handling
- Memory management (LRU cache, GC)
- State machine validation
- Performance optimizations

### v2.0 (2024-12-30)
- Original enhancements by William C. Chesher
- 4 theme support
- Enhanced touch controls
- Battery monitoring

### v1.0
- Original by John Park / Phillip Burgess
- Basic lightsaber functionality

---

## Credits

**Original Code:** [John Park / Phillip Burgess (Adafruit Industries)](https://learn.adafruit.com/hallowing-lightsaber)
**v3.0-v4.0 Enhancements:** William C. Chesher
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
