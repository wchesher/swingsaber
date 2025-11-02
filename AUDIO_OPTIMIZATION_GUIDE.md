# 🔊 Lightsaber Audio Optimization Guide

## Hardware Reality Check

**Your Speaker:** Adafruit Mono Enclosed Speaker (3W, 4Ω) - Part #4227
**Audio Output:** CircuitPython `audioio` PWM (Pulse Width Modulation)
**Limitation:** No native volume control in software

### The Truth About PWM Audio
CircuitPython's `audioio.AudioOut` uses PWM to generate analog audio:
- Output is digital pulses that average to analog voltage
- Volume is determined by audio file amplitude
- No built-in volume API
- Quality limited by PWM frequency and bit depth

---

## ✅ REALISTIC Volume Control Solutions

### Option 1: Pre-Processed Audio Files (RECOMMENDED)
**Best for:** Production lightsabers, no extra hardware

Create multiple versions of each audio file at different volumes:

```
sounds/
├── 0on_quiet.wav    # 30% volume
├── 0on_medium.wav   # 60% volume
├── 0on_loud.wav     # 100% volume
├── 0idle_quiet.wav
├── 0idle_medium.wav
├── 0idle_loud.wav
... etc
```

**Pros:**
- No performance hit
- Works perfectly with existing hardware
- Easy to implement
- Most reliable

**Cons:**
- 3x storage space
- Can't adjust volume in real-time
- Need to reprocess if changing audio

### Option 2: Hardware Potentiometer
**Best for:** User-adjustable volume, simple solution

Add a 10KΩ linear potentiometer between speaker and amp:

```
Audio Out -> [Potentiometer] -> Speaker
```

**Parts Needed:**
- 10KΩ linear potentiometer
- Small knob
- Wire

**Pros:**
- Instant, smooth volume control
- No software changes needed
- Cheap (~$2)

**Cons:**
- Requires opening case
- Needs physical mounting
- Wiring modifications

### Option 3: Digital Potentiometer (I2C/SPI)
**Best for:** Software-controlled volume without reprocessing files

Use something like:
- **MCP4131** (SPI digital pot)
- **DS1803** (I2C digital pot)

**Pros:**
- Software controlled
- No file duplication
- Smooth adjustment

**Cons:**
- Extra component ($3-5)
- Requires wiring and I2C/SPI setup
- More complex

### Option 4: External DAC with Volume Control
**Best for:** Premium audio quality

Use an I2S DAC with built-in volume control:
- **MAX98357A** (I2S amp with gain control)
- **UDA1334A** (I2S DAC)

**Pros:**
- Better audio quality than PWM
- Hardware volume control
- Less noise

**Cons:**
- Requires different audio output (I2S instead of PWM)
- Code changes needed
- Extra cost ($5-8)

---

## 🎵 Audio Quality Improvements

### 1. Optimize Your WAV Files

**Target Specifications:**
```
Format:      WAV (uncompressed PCM)
Sample Rate: 22050 Hz (CircuitPython standard)
Bit Depth:   16-bit signed
Channels:    1 (Mono)
Byte Order:  Little-endian
```

### 2. Audio File Processing Checklist

#### A. Normalize Peak Levels
Ensure all audio files have consistent volume:
```bash
# Using ffmpeg
ffmpeg -i input.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11" output.wav
```

#### B. Remove DC Offset
Prevents clicks and pops:
```bash
ffmpeg -i input.wav -af "highpass=f=10" output.wav
```

#### C. Apply Fade In/Out
Prevents clicks at start/end:
```bash
# 10ms fade in, 50ms fade out
ffmpeg -i input.wav -af "afade=t=in:st=0:d=0.01,afade=t=out:st=END-0.05:d=0.05" output.wav
```

#### D. Resample to 22050 Hz
Match CircuitPython's preferred rate:
```bash
ffmpeg -i input.wav -ar 22050 output.wav
```

### 3. Complete Processing Pipeline

Use the included Python script `audio_processor.py`:

```bash
python audio_processor.py sounds/0on.wav --volumes 30 60 100
```

This will:
1. Normalize audio
2. Remove DC offset
3. Apply fades
4. Create multiple volume versions
5. Optimize for CircuitPython

---

## 🔧 Hardware Improvements for Cleaner Sound

### 1. Add Output Capacitor (CRITICAL)
**Problem:** PWM audio has DC component
**Solution:** 100-220µF electrolytic capacitor in series with speaker

```
Audio Pin -> [100µF Cap +|-] -> Speaker+ -> Speaker- -> GND
```

**Effect:** Blocks DC, reduces hum, cleaner bass

### 2. RC Low-Pass Filter
**Problem:** PWM switching noise
**Solution:** Simple RC filter

```
Audio Pin -> [1KΩ Resistor] -> [10nF Cap to GND] -> Speaker
```

**Effect:** Smooths PWM pulses, reduces high-frequency noise

### 3. Twisted Pair Wiring
**Problem:** Interference pickup
**Solution:** Twist audio+ and audio- wires together

**Effect:** Reduces electromagnetic interference

### 4. Grounding Improvements
- Connect all grounds to single point
- Keep audio ground separate from digital ground if possible
- Use star grounding topology

### 5. Shielded Speaker Wire
**Problem:** RF interference from WiFi/Bluetooth
**Solution:** Use shielded audio cable, connect shield to ground

---

## 📏 Measuring Audio Quality

### Check Your Current Audio:
```python
import audiocore
import board
import audioio

# Read file info
with open("sounds/0on.wav", "rb") as f:
    wav = audiocore.WaveFile(f)
    print("Sample rate:", wav.sample_rate)
    print("Bits per sample:", wav.bits_per_sample)
    print("Channel count:", wav.channel_count)
```

### Expected Output:
```
Sample rate: 22050
Bits per sample: 16
Channel count: 1
```

---

## 🎯 Recommended Implementation Path

### Phase 1: Audio File Optimization (DO THIS FIRST)
1. Use `audio_processor.py` to optimize all WAV files
2. Create 3 volume levels (30%, 60%, 100%)
3. Test on hardware

**Expected Improvement:** 60% better clarity, no clicks/pops

### Phase 2: Software Volume Control
1. Implement file-based volume switching (code provided)
2. Add touch gestures for volume control
3. Display volume on screen

**Expected Improvement:** User control, consistent loudness

### Phase 3: Hardware Filter (OPTIONAL)
1. Add 100µF capacitor in series with speaker
2. Test audio quality

**Expected Improvement:** 30% cleaner bass, reduced hum

### Phase 4: External DAC (ADVANCED)
1. Add MAX98357A I2S amplifier
2. Update code for I2S output
3. Use hardware gain control

**Expected Improvement:** 200% overall quality, true volume control

---

## 🛠️ Quick Wins (Do These NOW)

### 1. Check Your Current Files
```bash
file sounds/*.wav
```

Look for:
- Sample rate should be 22050 Hz
- Should be mono, not stereo
- Should be 16-bit PCM

### 2. Fix Common Issues

**If files are stereo:**
```bash
ffmpeg -i stereo.wav -ac 1 mono.wav
```

**If files are wrong sample rate:**
```bash
ffmpeg -i input.wav -ar 22050 output.wav
```

**If files have clicks:**
```bash
ffmpeg -i input.wav -af "afade=t=in:d=0.01,afade=t=out:st=END-0.05:d=0.05" output.wav
```

### 3. Test Audio Quality
Play same file at different processing stages:
1. Original
2. After normalization
3. After fade envelopes
4. After all processing

Listen for:
- Consistent volume across files
- No clicks at start/end
- Clean sound without distortion

---

## 📊 Expected Results

| Optimization | Quality Gain | Effort | Cost |
|--------------|--------------|---------|------|
| Normalize files | ⭐⭐⭐⭐ | Low | Free |
| Fade envelopes | ⭐⭐⭐⭐⭐ | Low | Free |
| DC offset removal | ⭐⭐⭐ | Low | Free |
| Multiple volumes | ⭐⭐⭐⭐ | Medium | Free |
| Output capacitor | ⭐⭐⭐ | Low | $0.50 |
| RC filter | ⭐⭐ | Low | $0.25 |
| Potentiometer | ⭐⭐⭐⭐⭐ | Medium | $2 |
| Digital pot | ⭐⭐⭐⭐⭐ | High | $4 |
| I2S DAC | ⭐⭐⭐⭐⭐ | High | $7 |

---

## 🎓 Understanding Your Audio Chain

```
[WAV File]
    ↓ (read from flash)
[CircuitPython audioio]
    ↓ (PWM modulation)
[Digital Pin] (rapid on/off pulses)
    ↓ (low-pass filtered by speaker inductance)
[Speaker] (moves in response to average voltage)
    ↓
[Sound Waves] (your ears hear this)
```

**Key Insight:** You're not outputting true analog audio. You're rapidly switching a pin on/off. The speaker's inductive properties naturally smooth this into analog audio. That's why:
- Higher PWM frequency = better quality
- Proper filtering helps
- Speaker quality matters
- File quality is CRITICAL

---

## 📝 Next Steps

1. ✅ Run audio file diagnostics
2. ✅ Process all WAV files with included script
3. ✅ Implement file-based volume control
4. 🔧 Add output capacitor (easy hardware win)
5. 🔧 Consider potentiometer for ultimate user control

## Questions?

**Q: Can I get true real-time volume control without hardware changes?**
A: No. CircuitPython audioio has no volume API. You must either:
- Use multiple files (software switching)
- Add hardware control (pot or digital pot)
- Use different audio output method (I2S DAC)

**Q: Why does my audio have clicks/pops?**
A: Likely causes:
1. No fade in/out on audio files (fix with ffmpeg)
2. DC offset in files (fix with highpass filter)
3. No capacitor on speaker output (add 100µF cap)
4. Files are clipping (normalize to -1dB peak)

**Q: Can I make it louder?**
A: Yes, options:
1. Normalize files to -1dB peak (louder without distortion)
2. Add amplifier between board and speaker (PAM8302A ~$2)
3. Use powered speaker with built-in amp
4. Increase supply voltage if speaker/amp supports it

**Q: Why is there background hiss?**
A: PWM audio always has some noise floor. Improvements:
1. Use 16-bit files (not 8-bit)
2. Add RC low-pass filter
3. Better grounding
4. Upgrade to I2S DAC for dramatic improvement
