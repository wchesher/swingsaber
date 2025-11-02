# 🔊 Lightsaber Audio System

## Quick Start

Your lightsaber uses the **Adafruit 3W 4Ω Mono Speaker** with **PWM audio output**.

### The Volume Control Reality

**❌ NOT POSSIBLE (without hardware changes):**
- Real-time software volume control
- Smooth volume fading via code
- Native audioio volume API

**✅ WHAT ACTUALLY WORKS:**
1. **File-Based Volume** (RECOMMENDED - Already Implemented)
   - Use pre-processed audio files at different volumes
   - Switch between volume levels in code
   - Zero performance cost, works perfectly

2. **Hardware Potentiometer** ($2 solution)
   - Add physical knob for instant volume control
   - No software changes needed
   - See AUDIO_OPTIMIZATION_GUIDE.md

3. **Digital Potentiometer** ($4 solution)
   - Software-controlled via I2C
   - Adjust volume programmatically
   - Requires wiring and code changes

## Current Implementation

The firmware is set up for **file-based volume control**. The code tracks volume level, but to actually change volume, you need:

### Step 1: Process Your Audio Files

```bash
# Install dependencies
pip install pydub numpy

# Process all sound files at 3 volume levels
python audio_processor.py sounds/ --all --volumes 30 60 100
```

This creates:
```
sounds/optimized/
├── 0on_quiet.wav      # 30% volume
├── 0on_medium.wav     # 60% volume
├── 0on_loud.wav       # 100% volume
├── 0idle_quiet.wav
├── 0idle_medium.wav
... etc
```

### Step 2: Update Filename Logic

Modify `AudioManager.play_audio_clip()` to select files based on volume level:

```python
def play_audio_clip(self, theme_index, name, loop=False):
    # Determine volume suffix
    if self.volume <= 40:
        volume_suffix = "_quiet"
    elif self.volume <= 70:
        volume_suffix = "_medium"
    else:
        volume_suffix = "_loud"

    filename = "sounds/{}{}{}.wav".format(theme_index, name, volume_suffix)
    # ... rest of code
```

## Volume Controls

**Current Controls:**
- **Long press A3:** Increase volume  (+10%)
- **Long press A4:** Decrease volume (-10%)
- **Long press LEFT:** Cycle presets (30%, 50%, 70%, 100%)

**Range:** 10%-100% (prevents accidental muting)

## Audio Quality Checklist

### ✅ Optimize Your Files (DO THIS FIRST)

```bash
# Check current file specs
python audio_processor.py sounds/0on.wav --analyze

# Process and optimize
python audio_processor.py sounds/ --all --volumes 30 60 100
```

**Expected Results:**
- 22050 Hz sample rate
- 16-bit mono WAV
- Normalized to -1 dBFS
- No clicks/pops (fade in/out applied)
- DC offset removed

### 🔧 Hardware Improvements (OPTIONAL)

**Easy Wins:**
1. Add 100µF capacitor in series with speaker (blocks DC, cleaner sound)
2. Use twisted pair wire for speaker connection (reduces interference)
3. Star grounding topology (reduces noise)

**For Best Quality:**
- Upgrade to I2S DAC with hardware volume control (MAX98357A ~$7)
- See detailed guide: `AUDIO_OPTIMIZATION_GUIDE.md`

## File Structure

```
sounds/
├── 0on.wav          # Original files (unused after optimization)
├── 0off.wav
├── 0idle.wav
├── 0swing.wav
├── 0hit.wav
├── 0switch.wav
└── optimized/       # Processed files (use these!)
    ├── 0on_quiet.wav
    ├── 0on_medium.wav
    ├── 0on_loud.wav
    ├── 0off_quiet.wav
    ├── 0off_medium.wav
    ├── 0off_loud.wav
    └── ... (etc for all themes)
```

## Troubleshooting

### Audio is Quiet
- ✅ Run `audio_processor.py` to normalize files
- ✅ Check volume level (long press A3/A4)
- 🔧 Add amplifier (PAM8302A ~$2)

### Audio has Clicks/Pops
- ✅ Process files with `audio_processor.py` (adds fades)
- 🔧 Add 100µF capacitor in series with speaker

### Audio has Background Hiss
- ✅ Use 16-bit files (not 8-bit)
- 🔧 Add RC low-pass filter
- 🔧 Upgrade to I2S DAC for dramatic improvement

### Volume Control Doesn't Work
- ⚠️ Volume tracking works, but files must exist
- ✅ Run `audio_processor.py` to create volume variants
- ✅ Update code to use volume-suffixed filenames

## More Information

📖 **Comprehensive Guide:** See `AUDIO_OPTIMIZATION_GUIDE.md` for:
- Detailed hardware explanations
- All volume control options
- Audio processing techniques
- Hardware modification instructions
- Troubleshooting guide

🛠️ **Audio Processor:** Run `python audio_processor.py --help` for usage

## Summary

✅ **What Works Now:**
- Volume level tracking in software
- Touch controls for volume adjustment
- Display shows volume level

⚠️ **What You Need To Do:**
1. Process audio files with `audio_processor.py`
2. Update code to load correct volume variant
3. Copy optimized files to device

🎯 **Result:**
- Full volume control
- Better audio quality
- No clicks or pops
- Consistent loudness across all sounds
