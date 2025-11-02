# Deployment Checklist

Complete deployment guide for swingsaber v1.0

---

## Prerequisites

### Hardware
- [ ] Adafruit HalloWing M4 Express
- [ ] NeoPixel Strip (30 pixels, 0.5m) with 3-pin JST connector
- [ ] Mini Oval Speaker (8Ω 1W)
- [ ] LiPo Battery (3.7V, 500mAh or larger)
- [ ] USB-C cable

---

## Step 1: Install CircuitPython

- [ ] Download CircuitPython 10.x from https://circuitpython.org/board/hallowing_m4_express/
- [ ] Connect HalloWing M4 via USB
- [ ] Double-click reset button to enter bootloader mode
  - Board appears as `HALOBOOT` drive
- [ ] Copy CircuitPython UF2 file to `HALOBOOT` drive
- [ ] Wait for board to reboot
- [ ] Verify `CIRCUITPY` drive appears

---

## Step 2: Install Libraries

- [ ] Download CircuitPython 10.x Library Bundle from https://circuitpython.org/libraries
- [ ] Extract library bundle ZIP file
- [ ] Create `/lib/` folder on `CIRCUITPY` drive (if it doesn't exist)
- [ ] Copy required libraries to `/lib/`:
  - [ ] `adafruit_msa3xx.mpy`
  - [ ] `neopixel.mpy`
  - [ ] `adafruit_display_text/` (entire folder)

**Verify:**
```
CIRCUITPY/
└── lib/
    ├── adafruit_msa3xx.mpy
    ├── neopixel.mpy
    └── adafruit_display_text/
        ├── __init__.py
        ├── bitmap_label.mpy
        ├── label.mpy
        └── ... (other files)
```

---

## Step 3: Deploy Code

- [ ] Clone or download this repository
- [ ] Copy `code.py` to root of `CIRCUITPY` drive
  ```bash
  cp code.py /Volumes/CIRCUITPY/code.py
  ```
- [ ] Verify file appears on device
- [ ] Wait for board to auto-reload
- [ ] Check serial console for "Booting SaberController..." message

**Expected output:**
```
Booting SaberController...
Initializing Saber Hardware...
  NeoPixel strip OK.
  Touch inputs OK.
  Accelerometer OK.
Hardware init complete.
Status: {'strip': True, 'touch': True, 'accel': True, 'battery': True}

Audio system OK.
SaberController init complete.

=== SABER READY ===
```

---

## Step 4: Add Sound Files

- [ ] Create `/sounds/` folder on `CIRCUITPY` drive
- [ ] Copy your WAV files (must be 22050Hz, 16-bit, mono)
- [ ] Name files: `[theme]on.wav`, `[theme]off.wav`, etc.

Example:
```
CIRCUITPY/
└── sounds/
    ├── 0on.wav      # Theme 0 (Jedi) power on
    ├── 0off.wav
    ├── 0idle.wav
    ├── 0swing.wav
    ├── 0hit.wav
    ├── 0switch.wav
    ├── 1on.wav      # Theme 1 (Powerpuff) power on
    └── ... (24 files total for 4 themes)
```

**Audio Requirements:**
- Format: WAV (uncompressed PCM)
- Sample rate: 22050 Hz
- Bit depth: 16-bit signed
- Channels: Mono (1 channel)

---

## Step 5: Add Theme Images (Optional)

- [ ] Create `/images/` folder on `CIRCUITPY` drive
- [ ] Add BMP images (128x128 pixels, 24-bit or 16-bit color)
- [ ] Name files: `0logo.bmp`, `1logo.bmp`, `2logo.bmp`, `3logo.bmp`

```
CIRCUITPY/
└── images/
    ├── 0logo.bmp
    ├── 1logo.bmp
    ├── 2logo.bmp
    └── 3logo.bmp
```

---

## Step 6: Hardware Assembly

- [ ] Connect NeoPixel strip to HalloWing M4 NeoPixel JST connector
  - Verify polarity (connector is keyed)
  - Ensure strip has 30 pixels (or adjust `NUM_PIXELS` in code)

- [ ] Connect speaker to speaker terminals
  - Polarity doesn't matter for mono speaker
  - Ensure secure connections

- [ ] Connect LiPo battery to battery JST connector
  - **CAUTION:** Verify polarity! Connector should be keyed
  - Use 500mAh or larger battery

---

## Step 7: Testing

### Power On Test
- [ ] Power on device (via battery or USB)
- [ ] Verify display lights up
- [ ] Check serial console for boot messages
- [ ] Verify no error messages

### Touch Test
- [ ] Tap RIGHT button → lightsaber should power on
- [ ] LEDs should animate (progressive ignition)
- [ ] Audio should play power-on sound
- [ ] Tap RIGHT again → lightsaber should power off

### Motion Test
- [ ] Power on lightsaber
- [ ] Swing device → should hear swing sound, LEDs brighten
- [ ] Hit/shake device harder → should hear clash sound, LEDs flash
- [ ] Check serial console for "SWING:" and "HIT:" messages

### Theme Test
- [ ] With lightsaber OFF, tap LEFT button
- [ ] Display should show new theme logo
- [ ] Sound should play theme switch sound
- [ ] Repeat to cycle through all 4 themes

### Battery Test
- [ ] Tap A3 or A4 button
- [ ] Display should show battery percentage or "USB"
- [ ] Battery bar should display (if on battery)

---

## Step 8: Configuration (Optional)

Edit `code.py` to customize:

### Adjust Motion Sensitivity
```python
class SaberConfig:
    SWING_THRESHOLD = 140  # Lower = more sensitive
    HIT_THRESHOLD = 220    # Lower = more sensitive
```

### Change LED Count
```python
class SaberConfig:
    NUM_PIXELS = 30  # Match your NeoPixel strip length
```

### Adjust Brightness
```python
class UserConfig:
    NEOPIXEL_IDLE_BRIGHTNESS = 0.05   # 5% when idle
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3  # 30% when active
```

### Enable/Disable Diagnostics
```python
class UserConfig:
    ENABLE_DIAGNOSTICS = True  # False to reduce serial output
```

### Modify Themes
```python
class SaberConfig:
    THEMES = [
        {"name": "jedi", "color": (0, 0, 255), "hit_color": (255, 255, 255)},
        # Add your own themes here!
    ]
```

---

## Step 9: Troubleshooting

### Device Won't Boot
- [ ] Check battery charge
- [ ] Try USB power instead
- [ ] Verify CircuitPython 10.x installed correctly
- [ ] Boot into safe mode (hold button during power on)
- [ ] Check serial console for errors

### No Motion Detection
- [ ] Verify accelerometer initialized (check serial console)
- [ ] Lower thresholds in code
- [ ] Check library installed: `adafruit_msa3xx.mpy`

### No Audio
- [ ] Verify sound files in `/sounds/` folder
- [ ] Check file format: 22050Hz, 16-bit, mono
- [ ] Verify speaker connections
- [ ] Check serial console for errors

### LEDs Not Working
- [ ] Check `NUM_PIXELS` matches your strip
- [ ] Verify NeoPixel connector is plugged in
- [ ] Try changing `pixel_order` in code (GRB vs RGB)
- [ ] Ensure adequate power (5V, ~500mA for 30 pixels)

---

## Step 10: Final Verification

- [ ] All 4 themes work
- [ ] Motion detection responds correctly
- [ ] Audio plays without clicks/pops
- [ ] LEDs display correct colors
- [ ] Battery monitoring works
- [ ] No errors in serial console
- [ ] Device can run for extended period without crashes

---

## Post-Deployment

### Performance Monitoring
- [ ] Connect to serial console
- [ ] Monitor for error messages
- [ ] Check memory warnings (< 10KB free)
- [ ] Watch for accelerometer errors

### Hardware Enhancements
Consider upgrades:
- [ ] Install in custom lightsaber hilt
- [ ] Add diffuser material for blade
- [ ] Larger battery for extended runtime

---

## Documentation

Refer to these files for detailed information:

- **README.md** - Main documentation
- **LICENSE** - MIT License and attribution

---

## Support

If you encounter issues:

1. Check troubleshooting section above
2. Review serial console output
3. See original guide: https://learn.adafruit.com/hallowing-lightsaber
4. Open issue: https://github.com/wchesher/swingsaber/issues

---

## Deployment Complete! ✅

Your HalloWing M4 lightsaber is ready for action!

**⚔️ May the Force be with you! ⚔️**
