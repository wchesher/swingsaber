# Investigation: DFR0768 (DFPlayer Pro) as Alternative Audio Engine

## Summary

This document evaluates the **DFRobot DFR0768 (Fermion: DFPlayer Pro)** as a
potential replacement for the current onboard audio approach in SwingSaber v3.0.
The current system uses the HalloWing M4's built-in DAC via CircuitPython's
`audioio.AudioOut` with DMA-based WAV playback.

> **Note:** "TeenyFX" does not appear to be an identifiable product. The closest
> matches are the Adafruit Audio FX Sound Board or the Teensy Saber open-source
> project. This investigation compares the DFR0768 against the **current onboard
> audio system** (`audioio.AudioOut` on the HalloWing M4 Express).

---

## What is the DFR0768?

The **Fermion: DFPlayer Pro** (SKU: DFR0768) is a mini MP3 player module by
DFRobot, retailing at ~$8.90 USD. It is the successor to the popular DFPlayer
Mini (DFR0299).

**Key specs:**
- 24-bit DAC (vs 12-bit on SAMD51)
- Supports MP3, WAV, WMA, FLAC, APE formats
- 128MB onboard flash storage (loaded via USB-C)
- Stereo dual-channel output (L+/L-, R+/R-)
- Built-in Class D amplifier (software-controllable)
- Hardware volume control (0-30 levels)
- UART control interface (AT commands, default 115200 baud)
- 3.3V-5V operating voltage
- Physical PLAY and KEY buttons

---

## Current Audio Architecture (code.py:455-574)

```
WAV File (22050Hz, 16-bit, mono)
    -> audiocore.WaveFile (CircuitPython)
    -> audioio.AudioOut (DMA to DAC)
    -> Onboard Class D amplifier
    -> 8-ohm 1W speaker via JST
```

**Characteristics:**
- Near-instant clip switching (stop DMA -> open file -> play)
- Zero CPU overhead during playback (hardware DMA)
- No volume control (removed in commits f2965cc / 3e137ed)
- One clip at a time
- WAV-only format, files stored on shared flash filesystem
- ~120 lines of code in `AudioEngine` class

---

## Feature Comparison

| Feature | Current (audioio.AudioOut) | DFPlayer Pro (DFR0768) |
|---|---|---|
| DAC resolution | 12-bit (SAMD51) | 24-bit |
| Audio formats | WAV only (16-bit PCM) | MP3, WAV, WMA, FLAC, APE |
| Sample rate | 22050 Hz mono | Up to 48kHz stereo |
| Storage | Shared with code on HalloWing flash | Dedicated 128MB flash |
| Volume control | **None** (removed, no mixer) | **0-30 levels via AT cmd** |
| CPU overhead | Zero (hardware DMA) | Zero (offloaded to module) |
| Play latency | ~1-5ms (DMA start) | **50-500ms** (UART + file lookup) |
| Clip switching | Instant (stop->open->play) | AT command round-trip delay |
| Looping | Native `loop=True`, gapless | Module-handled looping |
| Amplifier | Onboard (HalloWing M4) | Onboard (DFPlayer Pro) |
| Speaker | 8-ohm 1W via JST | Recommended 4-ohm 3W |
| Interface | Internal (DAC pin) | External UART (TX/RX) |
| Memory impact | WAV buffer in RAM | Zero RAM on MCU |
| Wiring | None (onboard) | 4 wires (TX, RX, VCC, GND) + speaker |
| BUSY detection | `audio.playing` property | No BUSY pin; must poll via UART |

---

## Implementation Feasibility

### UART Pin Availability

The HalloWing M4 has `board.TX` and `board.RX` available on SERCOM4. These
pins are **not currently used** by SwingSaber and are exposed on the
Feather-compatible headers.

Additionally, SERCOM0 and SERCOM3 are completely free on the HalloWing M4,
providing backup options for additional UART pairs if needed.

**Wiring (DFPlayer Pro -> HalloWing M4):**
```
DFPlayer TX  ->  board.RX (HalloWing)
DFPlayer RX  ->  board.TX (HalloWing)
DFPlayer VCC ->  3.3V
DFPlayer GND ->  GND
DFPlayer L+/L- -> Speaker (or external amp)
```

### CircuitPython Libraries Available

1. **mindwidgets-circuitpython-df1201s** (recommended)
   - Available via `circup install df1201s`
   - UART at 115200 baud
   - Volume control (normalized 0.0-1.0)
   - Play modes, next/prev track
   - Full API documentation on ReadTheDocs

2. **DFPlayerPro-CircuitPython** by eddiecarbin
   - Direct port of DFRobot Arduino library
   - Notes: "WAV files work better than MP3" for sound effects
   - **8-character filename limit**

### Code Changes Required

The `AudioEngine` class (code.py:455-574) would need a complete rewrite:

```python
# Conceptual replacement (not tested)
import busio

class AudioEngine:
    def __init__(self, speaker_enable):
        self._uart = busio.UART(board.TX, board.RX, baudrate=115200)
        # Initialize DFPlayer Pro library
        self._player = DF1201S(self._uart)
        self._player.switch_function(self._player.MUSIC)
        self._player.set_vol(20)  # 0-30
        self._player.set_play_mode(self._player.SINGLE)

    def play(self, theme_index, name, loop=False):
        filename = "{}{}.wav".format(theme_index, name)
        self._player.play_spec_file("/" + filename)
        if loop:
            self._player.set_play_mode(self._player.SINGLECYCLE)

    def stop(self):
        self._player.pause()

    @property
    def playing(self):
        # No BUSY pin — must poll via UART
        return self._player.is_playing()  # UART round-trip!

    def poll(self):
        pass  # Module handles its own file cleanup
```

### File Organization

Sound files would be loaded onto the DFPlayer Pro's 128MB flash via USB-C,
**separate** from the HalloWing M4's filesystem. Current naming:
```
sounds/0on.wav    sounds/0idle.wav    sounds/0swing.wav
sounds/0hit.wav   sounds/0off.wav     sounds/0switch.wav
(x4 themes = 24 files)
```

**Concern:** The DFPlayerPro-CircuitPython library documents an **8-character
filename limit**. Current names like `0switch.wav` (7 chars before extension)
are within limits, but this constrains future naming.

---

## Critical Concerns

### 1. Latency (HIGH RISK)

This is the most significant concern. The SwingSaber architecture doc
(code.py:11) states: **"Audio DMA is sacred - never starve it"**.

Current behavior:
- IDLE -> HIT transition: `audio.stop()` + `audio.play()` = **<5ms**
- IDLE -> SWING transition: same, **<5ms**

With DFPlayer Pro:
- Each AT command requires **50-200ms** UART round-trip
- File lookup + playback start adds **100-500ms**
- **Total estimated latency: 150-700ms per clip switch**

For a lightsaber, a 200-700ms delay between a swing motion and the swing sound
would be **perceptibly broken**. Hit sounds delayed by half a second would feel
unresponsive.

### 2. Non-Blocking Architecture Conflict (HIGH RISK)

The main loop runs on a 20ms frame budget (code.py, 50 FPS). Every UART AT
command that waits for a response blocks the loop. The `playing` property
(checked every frame in `poll()`, swing/hit state transitions at lines
1512-1536) would require a UART poll each time.

Options:
- **Blocking UART:** Violates architecture principle #3 ("Zero blocking in the
  main loop"). Each `is_playing()` check adds ~50ms of blocking.
- **Non-blocking UART:** Would require a custom async AT command parser with
  buffered reads. Significant complexity increase.

### 3. No BUSY Pin (MEDIUM RISK)

Unlike the DFPlayer Mini, the DFPlayer Pro **lacks a hardware BUSY pin**. The
only way to detect playback completion is via UART polling, which compounds the
latency and blocking issues above.

Current code checks `self.audio.playing` (a zero-cost DMA register read) at
least once per frame. Replacing this with a UART query is a fundamental
architectural mismatch.

### 4. Volume Control (BENEFIT)

This is the **primary advantage**. The current system explicitly has no volume
control (commits f2965cc, 3e137ed removed all volume code because
`audioio.AudioOut` without a mixer provides no volume adjustment). The DFPlayer
Pro offers 0-30 level hardware volume via `AT+VOL=N`.

### 5. Audio Quality (MINOR BENEFIT)

The 24-bit DAC and support for higher sample rates / stereo would improve audio
fidelity. However, for a lightsaber in a noisy environment, the practical
difference between 12-bit/22kHz and 24-bit/44.1kHz through a small 1W speaker
may be negligible.

### 6. Storage (MINOR BENEFIT)

128MB dedicated storage means more room for sound themes. Currently, sounds
share the HalloWing M4's flash with code and images. However, the current 24
WAV files at 22050Hz mono are small enough that storage hasn't been a reported
issue.

---

## Alternative Approaches

### A. Restore audiomixer for Volume Control

If volume control is the primary motivation, consider re-adding
`audiomixer.Mixer` (previously removed due to DMA issues):

```python
import audiomixer
mixer = audiomixer.Mixer(
    voice_count=1,
    sample_rate=22050,
    channel_count=1,
    bits_per_sample=16,
    samples_signed=True,
)
audio = audioio.AudioOut(board.SPEAKER)
audio.play(mixer)
mixer.voice[0].level = 0.5  # Volume control!
```

**Pros:** Native volume control, zero latency, no additional hardware.
**Cons:** Previously caused DMA starvation / crackling issues (reason it was
removed). May require careful buffer tuning.

### B. External I2S DAC + Amplifier

Use an I2S DAC board (e.g., Adafruit MAX98357A) for higher-quality audio
output while keeping `audioio` control on the MCU side. Preserves the
zero-latency DMA architecture while improving audio quality.

### C. DFPlayer Pro for Ambient/Background Only

Use the DFPlayer Pro **only** for non-latency-critical audio (idle hum loop)
while keeping the onboard `audioio.AudioOut` for swing/hit sounds that require
instant response. This hybrid approach adds complexity but could provide the
best of both worlds.

---

## Recommendation

**The DFR0768 is not recommended as a direct replacement for the current audio
system** due to the latency mismatch with SwingSaber's real-time requirements.

| Priority | Approach |
|---|---|
| If volume control is essential | Re-investigate `audiomixer` with careful buffer tuning |
| If audio quality is the goal | Consider an I2S DAC (keeps zero-latency architecture) |
| If storage is the bottleneck | DFPlayer Pro for background audio only (hybrid approach) |
| If current system works well | Keep the existing `audioio.AudioOut` approach |

The 150-700ms latency penalty of UART-based audio control is fundamentally
incompatible with the SwingSaber's real-time motion-to-sound feedback loop. The
benefits (volume control, audio quality, storage) do not outweigh the cost of
perceptible lag on swing and hit sounds.

---

## References

- [DFRobot DFR0768 Product Page](https://www.dfrobot.com/product-2232.html)
- [DFRobot Wiki - DFPlayer PRO](https://wiki.dfrobot.com/DFPlayer_PRO_SKU_DFR0768)
- [DFRobot_DF1201S Arduino Library](https://github.com/DFRobot/DFRobot_DF1201S)
- [Mindwidgets CircuitPython DF1201S Library](https://github.com/mindwidgets/Mindwidgets_CircuitPython_DF1201S)
- [DFPlayerPro-CircuitPython Port](https://github.com/eddiecarbin/DFPlayerPro-CircuitPython)
- [Adafruit HalloWing M4 Pinouts](https://learn.adafruit.com/adafruit-hallowing-m4/pinouts)
- [CircuitPython audioio Documentation](https://docs.circuitpython.org/en/latest/shared-bindings/audioio/index.html)
