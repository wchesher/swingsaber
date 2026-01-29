# =============================================================================
# SPDX-FileCopyrightText: 2021 John Park for Adafruit Industries
# SPDX-FileCopyrightText: © 2024-2025 William C. Chesher <wchesher@gmail.com>
# SPDX-License-Identifier: MIT
#
# SwingSaber v3.0 - Audio-First Firmware
# Target: Adafruit HalloWing M4 Express | CircuitPython 10.x
# Speaker: 2W 8-ohm via 1.25mm JST -> onboard Class D amplifier
#
# Architecture priorities:
#   1. Audio DMA is sacred - continuous mixer, never restart DMA mid-session
#   2. Real volume control - mixer voice level, not just a stored number
#   3. Fixed frame timing - all visuals on a steady cadence
#   4. Zero blocking in the main loop - everything is non-blocking
#   5. Single point of state change - no scattered transitions
#
# WAV file requirements (best quality):
#   Format:  16-bit signed PCM, 22050 Hz, mono
#   Convert: sox input.wav -b 16 -r 22050 -c 1 output.wav
#   Note:    8-bit/16kHz files work but sound noticeably worse
# =============================================================================

import time
import gc
import math
import array
import board
import busio
import neopixel
import audioio
import audiocore
import audiomixer
import adafruit_msa3xx
import touchio
import analogio
import supervisor
import displayio
import terminalio
import microcontroller
from digitalio import DigitalInOut
from adafruit_display_text import label

try:
    from watchdog import WatchDogMode
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False


# =============================================================================
# ANIMATION STYLES (for onboard NeoPixels)
# =============================================================================

ANIM_BREATHE = 0
ANIM_SPIN = 1
ANIM_LIGHTNING = 2
ANIM_PULSE = 3
ANIM_FIRE = 4
ANIM_SPARKLE = 5

_ANIM_NAMES = {
    ANIM_BREATHE: "breathe",
    ANIM_SPIN: "spin",
    ANIM_LIGHTNING: "lightning",
    ANIM_PULSE: "pulse",
    ANIM_FIRE: "fire",
    ANIM_SPARKLE: "sparkle",
}


# =============================================================================
# USER SETTINGS
# =============================================================================

class UserConfig:
    """All user-tunable parameters in one place."""

    # -- Themes ---------------------------------------------------------------
    # Each theme needs: {index}on.wav, {index}off.wav, {index}idle.wav,
    #                    {index}swing.wav, {index}hit.wav, {index}switch.wav
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255, 0),   "hit_color": (255, 255, 255, 255),
         "idle_anim": ANIM_BREATHE, "swing_anim": ANIM_SPIN, "hit_anim": ANIM_LIGHTNING},
        {"name": "powerpuff",  "color": (255, 0, 255, 0), "hit_color": (0, 200, 255, 0),
         "idle_anim": ANIM_PULSE, "swing_anim": ANIM_SPARKLE, "hit_anim": ANIM_FIRE},
        {"name": "ricknmorty", "color": (0, 255, 0, 0),   "hit_color": (255, 0, 0, 0),
         "idle_anim": ANIM_FIRE, "swing_anim": ANIM_LIGHTNING, "hit_anim": ANIM_SPARKLE},
        {"name": "spongebob",  "color": (255, 255, 0, 0), "hit_color": (255, 255, 255, 255),
         "idle_anim": ANIM_SPARKLE, "swing_anim": ANIM_PULSE, "hit_anim": ANIM_SPIN},
    ]

    # -- Motion ---------------------------------------------------------------
    # Force thresholds in m/s² of absolute acceleration above resting gravity.
    # Direction-independent: the same physical force triggers regardless of
    # which way the saber is moved.
    SWING_THRESHOLD = 4.0     # Sustained force to trigger swing (~0.4G)
    HIT_THRESHOLD = 15.0      # Impact spike to trigger hit (~1.5G)
    SMOOTHING_FACTOR = 0.4    # EMA alpha (0-1): higher = more responsive

    # -- Brightness -----------------------------------------------------------
    BRIGHTNESS_PRESETS = [0.15, 0.25, 0.35, 0.45]
    BRIGHTNESS_LABELS = [25, 50, 75, 100]  # User-facing percentages
    DEFAULT_BRIGHTNESS = 0.45
    IDLE_BRIGHTNESS = 0.05

    # -- Volume ---------------------------------------------------------------
    VOLUME_PRESETS = [30, 50, 70, 100]
    DEFAULT_VOLUME = 70
    VOLUME_STEP = 10
    MIN_VOLUME = 10
    MAX_VOLUME = 100

    # -- Display --------------------------------------------------------------
    DISPLAY_BRIGHTNESS = 0.3
    DISPLAY_TIMEOUT = 2.0

    # -- Diagnostics ----------------------------------------------------------
    ENABLE_DIAGNOSTICS = True
    ACCEL_OUTPUT_INTERVAL = 0.5

    # -- Touch ----------------------------------------------------------------
    LONG_PRESS_TIME = 1.0

    # -- Persistent storage ---------------------------------------------------
    ENABLE_PERSISTENT_SETTINGS = True
    NVM_THEME_OFFSET = 0
    NVM_VOLUME_OFFSET = 1
    NVM_BRIGHTNESS_OFFSET = 2
    NVM_MAGIC_OFFSET = 3
    NVM_MAGIC_VALUE = 0xAB

    # -- Battery --------------------------------------------------------------
    BATTERY_CHECK_INTERVAL = 30.0
    BATTERY_WARNING_THRESHOLD = 15
    BATTERY_CRITICAL_THRESHOLD = 5
    BATTERY_WARNING_INTERVAL = 60.0

    # -- Watchdog -------------------------------------------------------------
    ENABLE_WATCHDOG = True
    WATCHDOG_TIMEOUT = 8.0

    # -- Memory ---------------------------------------------------------------
    MAX_IMAGE_CACHE_SIZE = 4
    GC_INTERVAL = 10.0
    CRITICAL_MEMORY_THRESHOLD = 8192

    # -- Accelerometer recovery -----------------------------------------------
    MAX_ACCEL_ERRORS = 10
    ACCEL_RECOVERY_INTERVAL = 30.0


# =============================================================================
# HARDWARE CONSTANTS
# =============================================================================

class HWConfig:
    """Fixed hardware parameters — do not change unless hardware changes."""

    NUM_PIXELS = 55
    ONBOARD_PIXELS = 4
    ONBOARD_BRIGHTNESS = 0.3
    IDLE_COLOR_DIVISOR = 4

    # Audio (mixer buffer in bytes — ~93ms at 22050Hz/16-bit)
    MIXER_BUFFER_SIZE = 2048


    # Battery ADC
    BATTERY_VOLTAGE_SAMPLES = 10
    BATTERY_MIN_VOLTAGE = 3.3
    BATTERY_MAX_VOLTAGE = 4.2
    BATTERY_ADC_MAX = 65535
    BATTERY_VOLTAGE_DIVIDER = 2

    # Animation durations
    POWER_ON_DURATION = 1.7
    POWER_OFF_DURATION = 1.15
    SWING_DURATION_FALLBACK = 0.5
    HIT_DURATION_FALLBACK = 0.8

    # Display
    IMAGE_DISPLAY_DURATION = 3.0


# =============================================================================
# FRAME TIMING
# =============================================================================
#
# Everything visual runs locked to a fixed cadence.  Audio DMA runs
# independently in hardware; our job is to never starve it by doing long
# blocking operations.  LED strip.show() for 55 RGBW pixels takes ~3.5 ms
# at 800 kHz.  We budget a 20 ms frame (50 FPS) which leaves >16 ms of
# headroom per frame for everything else.
#
# The main loop measures how long each iteration took and sleeps only the
# remainder, so frame timing stays consistent regardless of workload.

FRAME_PERIOD = 0.020          # 20 ms = 50 FPS target
LED_MIN_INTERVAL = 0.018      # never push LED data faster than this
ACCEL_SAMPLE_INTERVAL = 0.015 # poll accelerometer every 15 ms


# =============================================================================
# STATE DEFINITIONS
# =============================================================================

STATE_OFF = 0
STATE_IDLE = 1
STATE_SWING = 2
STATE_HIT = 3
STATE_POWER_ON = 4
STATE_POWER_OFF = 5
STATE_ERROR = 6

_STATE_NAMES = {
    0: "OFF", 1: "IDLE", 2: "SWING", 3: "HIT",
    4: "PWR_ON", 5: "PWR_OFF", 6: "ERROR",
}

# Allowed transitions (from -> set of legal destinations)
_VALID_TRANSITIONS = {
    STATE_OFF:       {STATE_POWER_ON, STATE_ERROR},
    STATE_IDLE:      {STATE_SWING, STATE_HIT, STATE_POWER_OFF, STATE_ERROR},
    STATE_SWING:     {STATE_IDLE, STATE_POWER_OFF, STATE_ERROR},
    STATE_HIT:       {STATE_IDLE, STATE_POWER_OFF, STATE_ERROR},
    STATE_POWER_ON:  {STATE_IDLE, STATE_ERROR},
    STATE_POWER_OFF: {STATE_OFF, STATE_ERROR},
    STATE_ERROR:     {STATE_OFF},
}


# =============================================================================
# PERSISTENT SETTINGS (NVM)
# =============================================================================

class PersistentSettings:
    """Read/write settings to non-volatile memory."""

    @staticmethod
    def _valid():
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            return microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] == UserConfig.NVM_MAGIC_VALUE
        except Exception:
            return False

    @staticmethod
    def _write(offset, value):
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            microcontroller.nvm[offset] = value
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("NVM write error:", e)
            return False

    @staticmethod
    def load_theme():
        if not PersistentSettings._valid():
            return 0
        try:
            v = microcontroller.nvm[UserConfig.NVM_THEME_OFFSET]
            return v if v < len(UserConfig.THEMES) else 0
        except Exception:
            return 0

    @staticmethod
    def load_volume():
        if not PersistentSettings._valid():
            return UserConfig.DEFAULT_VOLUME
        try:
            v = microcontroller.nvm[UserConfig.NVM_VOLUME_OFFSET]
            return v if UserConfig.MIN_VOLUME <= v <= UserConfig.MAX_VOLUME else UserConfig.DEFAULT_VOLUME
        except Exception:
            return UserConfig.DEFAULT_VOLUME

    @staticmethod
    def load_brightness():
        if not PersistentSettings._valid():
            return 3
        try:
            v = microcontroller.nvm[UserConfig.NVM_BRIGHTNESS_OFFSET]
            return v if v < len(UserConfig.BRIGHTNESS_PRESETS) else 3
        except Exception:
            return 3

    @staticmethod
    def save_theme(idx):
        return PersistentSettings._write(UserConfig.NVM_THEME_OFFSET, idx)

    @staticmethod
    def save_volume(vol):
        return PersistentSettings._write(UserConfig.NVM_VOLUME_OFFSET, vol)

    @staticmethod
    def save_brightness(idx):
        return PersistentSettings._write(UserConfig.NVM_BRIGHTNESS_OFFSET, idx)


# =============================================================================
# HARDWARE LAYER
# =============================================================================

class Hardware:
    """Owns every physical peripheral.  Initializes once, provides accessors."""

    def __init__(self):
        print("HW init...")
        self.ok = {"strip": False, "touch": False, "accel": False, "battery": False}

        # Cap reference pin
        try:
            self.cap_pin = DigitalInOut(board.CAP_PIN)
            self.cap_pin.switch_to_output(value=False)
        except Exception:
            self.cap_pin = None

        # Speaker enable
        try:
            self.speaker_enable = DigitalInOut(board.SPEAKER_ENABLE)
            self.speaker_enable.switch_to_output(value=True)
        except Exception as e:
            print("  speaker enable err:", e)
            self.speaker_enable = None

        # Battery ADC
        try:
            self.battery_adc = analogio.AnalogIn(board.VOLTAGE_MONITOR)
            self.ok["battery"] = True
        except Exception:
            self.battery_adc = None

        # NeoPixel strip
        self.strip = None
        try:
            self.strip = neopixel.NeoPixel(
                board.EXTERNAL_NEOPIXEL, HWConfig.NUM_PIXELS,
                brightness=UserConfig.DEFAULT_BRIGHTNESS,
                auto_write=False, pixel_order=neopixel.GRBW,
            )
            self.strip.fill(0)
            self.strip.show()
            self.ok["strip"] = True
            print("  strip OK")
        except Exception as e:
            print("  strip err:", e)

        # Onboard pixels
        self.onboard = None
        try:
            self.onboard = neopixel.NeoPixel(
                board.NEOPIXEL, HWConfig.ONBOARD_PIXELS,
                brightness=HWConfig.ONBOARD_BRIGHTNESS,
                auto_write=False,
            )
            self.onboard.fill(0)
            self.onboard.show()
            print("  onboard OK")
        except Exception as e:
            print("  onboard err:", e)

        # Touch inputs
        self.touch_left = None
        self.touch_right = None
        self.touch_a3 = None
        self.touch_a4 = None
        try:
            self.touch_left = touchio.TouchIn(board.TOUCH1)
            self.touch_right = touchio.TouchIn(board.TOUCH4)
            self.touch_a3 = touchio.TouchIn(board.A3)
            self.touch_a4 = touchio.TouchIn(board.A4)
            self.ok["touch"] = True
            print("  touch OK")
        except Exception as e:
            print("  touch err:", e)

        # Accelerometer
        self.accel = None
        self.i2c = None
        self._init_accel()

        # Watchdog
        self.watchdog = None
        if UserConfig.ENABLE_WATCHDOG and _WATCHDOG_AVAILABLE:
            try:
                self.watchdog = microcontroller.watchdog
                self.watchdog.timeout = UserConfig.WATCHDOG_TIMEOUT
                self.watchdog.mode = WatchDogMode.RESET
                print("  watchdog OK ({}s)".format(UserConfig.WATCHDOG_TIMEOUT))
            except Exception as e:
                print("  watchdog err:", e)

        print("HW ready:", self.ok)

    def _init_accel(self):
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.accel = adafruit_msa3xx.MSA311(self.i2c)
            self.ok["accel"] = True
            print("  accel OK")
        except Exception as e:
            print("  accel err:", e)
            self.accel = None

    def reinit_accel(self):
        """Try to re-establish the accelerometer after errors."""
        if self.accel is not None:
            return True
        if self.i2c is not None:
            try:
                self.i2c.deinit()
            except Exception:
                pass
            self.i2c = None
        self._init_accel()
        return self.accel is not None

    def feed_watchdog(self):
        if self.watchdog is not None:
            try:
                self.watchdog.feed()
            except Exception:
                pass

    def read_battery_pct(self):
        """Return battery percentage (int) or the string 'USB'."""
        if supervisor.runtime.usb_connected:
            return "USB"
        if not self.battery_adc:
            return 0
        try:
            total = 0
            for _ in range(HWConfig.BATTERY_VOLTAGE_SAMPLES):
                total += self.battery_adc.value
                # 0.001 s × 10 = 10 ms total — acceptable, only runs every 30 s
                time.sleep(0.001)
            avg = total / HWConfig.BATTERY_VOLTAGE_SAMPLES
            voltage = (avg / HWConfig.BATTERY_ADC_MAX) * self.battery_adc.reference_voltage * HWConfig.BATTERY_VOLTAGE_DIVIDER
            pct = (voltage - HWConfig.BATTERY_MIN_VOLTAGE) / (HWConfig.BATTERY_MAX_VOLTAGE - HWConfig.BATTERY_MIN_VOLTAGE) * 100
            return min(max(int(pct), 0), 100)
        except Exception as e:
            print("batt err:", e)
            return 0

    def cleanup(self):
        if self.strip:
            try:
                self.strip.fill(0)
                self.strip.show()
            except Exception:
                pass
        if self.onboard:
            try:
                self.onboard.fill(0)
                self.onboard.show()
            except Exception:
                pass
        if self.speaker_enable:
            try:
                self.speaker_enable.value = False
            except Exception:
                pass
        if self.i2c:
            try:
                self.i2c.deinit()
            except Exception:
                pass
        if self.watchdog is not None:
            try:
                self.watchdog.mode = None
            except Exception:
                pass


# =============================================================================
# AUDIO ENGINE
# =============================================================================
#
# Continuous-DMA architecture using audiomixer
# ---------------------------------------------
# The mixer starts at boot and runs until shutdown.  DMA to the DAC never
# restarts during normal operation — this eliminates every pop and gap
# between clips.
#
# Audio chain:  WaveFile → Mixer voice 0 → AudioOut(DAC) → Class D amp → speaker
#
# Volume is real: mixer.voice[0].level maps directly to output amplitude.
# Transitions are seamless: voice.play(new_clip) atomically replaces the
# current clip without restarting DMA.
#
# The only time we tear down the chain is reinit() — reserved for error
# recovery, never called during normal power on/off.

class AudioEngine:
    """Audio with mixer for gapless playback, direct-AudioOut fallback.

    Two modes:
      MIXER  — audiomixer.Mixer fed to AudioOut.  Gapless transitions,
               real volume via voice level.  DMA never restarts.
      DIRECT — AudioOut.play(wav) like the original firmware.  Gaps
               between clips but guaranteed to work on any CircuitPython.

    If mixer init fails for any reason, we silently fall back to direct.
    """

    def __init__(self, speaker_enable):
        self._speaker_enable = speaker_enable
        self._audio = None       # audioio.AudioOut
        self._mixer = None       # audiomixer.Mixer (None = direct mode)
        self._silence_buf = None # array buffer backing the silence sample
        self._silence = None     # tiny RawSample used to release voice refs
        self._wave_file = None   # open file handle for current clip
        self._wav = None         # audiocore.WaveFile for current clip
        self.volume = UserConfig.DEFAULT_VOLUME
        self.volume_preset_index = 1

        # Enable amplifier first — leave on to avoid pops
        if self._speaker_enable:
            try:
                self._speaker_enable.value = True
            except Exception:
                pass

        self._init_chain()

    # -- chain setup ----------------------------------------------------------

    def _detect_format(self):
        """Probe first available WAV to configure mixer format."""
        for i in range(len(UserConfig.THEMES)):
            for name in ("idle", "on", "swing"):
                try:
                    f = open("sounds/{}{}.wav".format(i, name), "rb")
                    w = audiocore.WaveFile(f)
                    sr = w.sample_rate
                    bits = w.bits_per_sample
                    ch = w.channel_count
                    signed = bits == 16
                    f.close()
                    quality = "OK" if bits >= 16 and sr >= 22050 else "LOW"
                    print("WAV: {}Hz {}bit {}ch [{}]".format(
                        sr, bits, ch, quality))
                    if quality == "LOW":
                        print("  upgrade: sox in.wav -b 16 -r 22050 -c 1 out.wav")
                    return sr, bits, ch, signed
                except Exception:
                    continue
        return 22050, 16, 1, True

    def _init_chain(self):
        """Try mixer mode, fall back to direct AudioOut if anything fails."""

        # --- attempt 1: mixer mode ---
        sr, bits, ch, signed = self._detect_format()
        try:
            mixer = audiomixer.Mixer(
                voice_count=1,
                sample_rate=sr,
                channel_count=ch,
                bits_per_sample=bits,
                samples_signed=signed,
                buffer_size=HWConfig.MIXER_BUFFER_SIZE,
            )
            audio = audioio.AudioOut(board.SPEAKER)
            audio.play(mixer)
            self._mixer = mixer
            self._audio = audio
            self._silence_buf = array.array('h', [0])
            self._silence = audiocore.RawSample(
                self._silence_buf, sample_rate=sr)
            self._apply_volume()
            print("Audio: mixer ({}Hz {}bit)".format(sr, bits))
            return
        except Exception as e:
            print("Mixer failed: {} — falling back to direct".format(e))
            # clean up partial init
            try:
                audio.deinit()  # noqa: F821
            except Exception:
                pass

        # --- attempt 2: direct AudioOut (always worked before) ---
        try:
            self._audio = audioio.AudioOut(board.SPEAKER)
            self._mixer = None
            print("Audio: direct DAC (no mixer)")
        except Exception as e:
            print("Audio FAIL: {}".format(e))
            self._audio = None
            self._mixer = None

    def _apply_volume(self):
        """Push volume to mixer voice level (mixer mode only)."""
        if self._mixer is not None:
            try:
                self._mixer.voice[0].level = self.volume / 100.0
            except Exception:
                pass

    def _close_file(self):
        """Release current WAV file handle."""
        if self._wave_file is not None:
            try:
                self._wave_file.close()
            except Exception:
                pass
            self._wave_file = None
            self._wav = None

    # -- public API -----------------------------------------------------------

    def reinit(self):
        """Full teardown + rebuild.  Error recovery only."""
        self.stop()
        if self._audio is not None:
            try:
                self._audio.stop()
                self._audio.deinit()
            except Exception:
                pass
        self._audio = None
        self._mixer = None
        gc.collect()
        self._init_chain()

    def play(self, theme_index, name, loop=False):
        """Play sounds/{theme_index}{name}.wav.  Returns True on success."""
        if self._audio is None:
            return False

        filename = "sounds/{}{}.wav".format(theme_index, name)

        if self._mixer is not None:
            return self._play_mixer(filename, loop)
        else:
            return self._play_direct(filename, loop)

    def _play_mixer(self, filename, loop):
        """Mixer mode: swap to silence, free old clip, then play new clip.

        Memory on the M4 is too tight for two WaveFile objects to coexist.
        voice[0].stop() does NOT release the voice's internal C reference
        to the old WaveFile, so gc cannot reclaim it.  Instead we play a
        tiny silence sample — the atomic swap releases the old reference —
        then gc.collect() frees the old WaveFile *before* we allocate the
        new one.
        """
        # 1. Swap voice to silence placeholder.  This atomically replaces
        #    the voice's internal reference so the old WaveFile becomes
        #    unreferenced and eligible for gc.
        try:
            self._mixer.voice[0].play(self._silence, loop=True)
        except Exception:
            pass

        # 2. Drop Python refs and close old file handle.
        self._close_file()

        # 3. Free old WaveFile + buffer — only one WaveFile at a time.
        gc.collect()

        # 4. Open and play the new clip.
        try:
            new_file = open(filename, "rb")
        except OSError as e:
            print("open err:", filename, e)
            return False

        try:
            new_wav = audiocore.WaveFile(new_file)
        except Exception as e:
            print("wav err:", filename, e)
            try:
                new_file.close()
            except Exception:
                pass
            return False

        try:
            self._mixer.voice[0].play(new_wav, loop=loop)
        except Exception as e:
            print("play err:", filename, e)
            try:
                new_file.close()
            except Exception:
                pass
            return False

        # Re-apply volume — play() may reset the voice level.
        self._apply_volume()

        self._wave_file = new_file
        self._wav = new_wav
        return True

    def _play_direct(self, filename, loop):
        """Direct mode: stop → close → open → play (classic approach)."""
        try:
            self._audio.stop()
        except Exception:
            pass
        self._close_file()

        try:
            self._wave_file = open(filename, "rb")
            self._wav = audiocore.WaveFile(self._wave_file)
        except OSError:
            self._close_file()
            return False
        except Exception as e:
            print("wav err:", e)
            self._close_file()
            return False

        try:
            self._audio.play(self._wav, loop=loop)
            return True
        except Exception as e:
            print("play err:", e)
            self._close_file()
            return False

    @property
    def playing(self):
        if self._mixer is not None:
            try:
                return self._mixer.voice[0].playing
            except Exception:
                return False
        if self._audio is not None:
            try:
                return self._audio.playing
            except Exception:
                return False
        return False

    def stop(self):
        """Stop current playback."""
        if self._mixer is not None:
            try:
                self._mixer.voice[0].stop()
            except Exception:
                pass
        elif self._audio is not None:
            try:
                self._audio.stop()
            except Exception:
                pass
        self._close_file()

    def poll(self):
        """Call once per frame.  Closes file handles for finished clips."""
        if self._wave_file is not None and not self.playing:
            self._close_file()

    def mute(self):
        if self._speaker_enable:
            self._speaker_enable.value = False

    def unmute(self):
        if self._speaker_enable:
            self._speaker_enable.value = True

    def set_volume(self, pct):
        """Set volume 10-100%.  Applies to mixer if available."""
        self.volume = max(UserConfig.MIN_VOLUME, min(pct, UserConfig.MAX_VOLUME))
        self._apply_volume()
        print("Volume: {}%".format(self.volume))
        return self.volume

    def increase_volume(self):
        return self.set_volume(self.volume + UserConfig.VOLUME_STEP)

    def decrease_volume(self):
        return self.set_volume(self.volume - UserConfig.VOLUME_STEP)

    def cycle_volume_preset(self):
        self.volume_preset_index = (self.volume_preset_index + 1) % len(UserConfig.VOLUME_PRESETS)
        return self.set_volume(UserConfig.VOLUME_PRESETS[self.volume_preset_index])

    def cleanup(self):
        """Shut down audio chain."""
        self.stop()
        if self._audio is not None:
            try:
                self._audio.stop()
                self._audio.deinit()
            except Exception:
                pass
            self._audio = None
            self._mixer = None
        if self._speaker_enable:
            try:
                self._speaker_enable.value = False
            except Exception:
                pass


# =============================================================================
# DISPLAY MANAGER
# =============================================================================

class Display:
    """TFT display with LRU image cache and non-blocking timeout."""

    def __init__(self, battery_func):
        self._group = displayio.Group()
        self._get_battery = battery_func
        self._cache = {}
        self._cache_order = []
        self._active = False
        self._start = 0
        self._timeout = UserConfig.DISPLAY_TIMEOUT

        try:
            board.DISPLAY.auto_refresh = False
            board.DISPLAY.brightness = 0
        except Exception:
            pass

    # -- helpers --------------------------------------------------------------

    def _off(self):
        try:
            board.DISPLAY.brightness = 0
        except Exception:
            pass

    def _clear_group(self):
        while len(self._group):
            self._group.pop()

    def _show_bar(self, title, value, color, bar_w=None):
        try:
            self._clear_group()
            self._group.append(
                label.Label(terminalio.FONT, text=title, scale=2, color=color, x=10, y=30))
            if value is not None:
                w = bar_w if bar_w is not None else max(1, min(value, 100))
                grp = displayio.Group()
                bg_pal = displayio.Palette(1)
                bg_pal[0] = 0x444444
                bg_bmp = displayio.Bitmap(100, 14, 1)
                bg_bmp.fill(0)
                grp.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal, x=14, y=46))
                fg_pal = displayio.Palette(1)
                fg_pal[0] = color
                fg_bmp = displayio.Bitmap(w, 10, 1)
                fg_bmp.fill(0)
                grp.append(displayio.TileGrid(fg_bmp, pixel_shader=fg_pal, x=16, y=48))
                self._group.append(grp)
            board.DISPLAY.root_group = self._group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
            board.DISPLAY.refresh()
            self._start = time.monotonic()
            self._timeout = UserConfig.DISPLAY_TIMEOUT
            self._active = True
        except Exception as e:
            print("disp err:", e)

    # -- public ---------------------------------------------------------------

    def show_battery(self):
        b = self._get_battery()
        if b == "USB":
            self._show_bar("BATTERY: USB", None, 0xFFFFFF)
        else:
            self._show_bar("BATTERY: {}%".format(b), b, 0xFFFF00)

    def show_volume(self, vol):
        self._show_bar("VOLUME: {}%".format(vol), vol, 0x00FF00)

    def show_brightness(self, pct):
        bar_w = max(1, min(int(pct * 2.5), 100))
        self._show_bar("BRIGHT: {}%".format(pct), pct, 0xFFFF00, bar_w)

    def _load_image(self, theme_index, kind="logo"):
        key = "{}{}".format(theme_index, kind)
        if key in self._cache:
            self._cache_order.remove(key)
            self._cache_order.append(key)
            return self._cache[key]
        fname = "/images/{}{}.bmp".format(theme_index, kind)
        try:
            if len(self._cache) >= UserConfig.MAX_IMAGE_CACHE_SIZE:
                oldest = self._cache_order.pop(0)
                self._cache.pop(oldest, None)
                gc.collect()
            bmp = displayio.OnDiskBitmap(fname)
            tg = displayio.TileGrid(bmp, pixel_shader=bmp.pixel_shader)
            self._cache[key] = tg
            self._cache_order.append(key)
            return tg
        except OSError:
            return None
        except Exception as e:
            print("img err:", e)
            return None

    def show_image_async(self, theme_index, kind="logo", duration=None):
        """Show image without blocking — auto-clears via poll()."""
        if duration is None:
            duration = HWConfig.IMAGE_DISPLAY_DURATION
        try:
            self._clear_group()
            img = self._load_image(theme_index, kind)
            if img:
                self._group.append(img)
                board.DISPLAY.root_group = self._group
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
                board.DISPLAY.refresh()
            self._start = time.monotonic()
            self._timeout = duration
            self._active = True
        except Exception as e:
            print("img async err:", e)

    def poll(self):
        """Call once per frame — handles display timeout."""
        if self._active and time.monotonic() - self._start > self._timeout:
            self._clear_group()
            try:
                board.DISPLAY.root_group = self._group
            except Exception:
                pass
            self._off()
            self._active = False

    def cleanup(self):
        self._cache.clear()
        self._cache_order.clear()
        self._off()


# =============================================================================
# INPUT MANAGER (non-blocking)
# =============================================================================
#
# Every touch pad is polled once per frame.  Press/release edges and timing
# are tracked in a tiny state struct.  The main controller asks "did a tap
# happen?" or "did a long-press fire?" — never blocks.

class InputManager:
    """Non-blocking capacitive touch input with tap and long-press detection."""

    def __init__(self, hw):
        self._hw = hw
        self._state = {}
        for name in ("left", "right", "a3", "a4"):
            self._state[name] = {
                "start": 0,
                "is_long": False,
                "long_fired": False,
                "tap_ready": False,
            }

    def _pad(self, name):
        if name == "left":
            return self._hw.touch_left
        if name == "right":
            return self._hw.touch_right
        if name == "a3":
            return self._hw.touch_a3
        if name == "a4":
            return self._hw.touch_a4
        return None

    def poll(self):
        """Read all pads once per frame and update edge state."""
        now = time.monotonic()
        for name in ("left", "right", "a3", "a4"):
            pad = self._pad(name)
            if pad is None:
                continue
            st = self._state[name]
            try:
                pressed = pad.value
            except Exception:
                continue

            if pressed:
                if st["start"] == 0:
                    # rising edge
                    st["start"] = now
                    st["is_long"] = False
                    st["long_fired"] = False
                    st["tap_ready"] = False
                elif not st["is_long"] and now - st["start"] >= UserConfig.LONG_PRESS_TIME:
                    st["is_long"] = True
            else:
                # released
                if st["start"] > 0 and not st["is_long"]:
                    st["tap_ready"] = True
                st["start"] = 0
                st["is_long"] = False
                st["long_fired"] = False

    def tap(self, name):
        """Returns True once when a short press is released (tap)."""
        st = self._state.get(name)
        if st and st["tap_ready"]:
            st["tap_ready"] = False
            return True
        return False

    def long_press(self, name):
        """Returns True once when long-press threshold is reached."""
        st = self._state.get(name)
        if st and st["is_long"] and not st["long_fired"]:
            st["long_fired"] = True
            return True
        return False

    def is_pressed(self, name):
        st = self._state.get(name)
        return st is not None and st["start"] > 0


# =============================================================================
# MOTION ENGINE
# =============================================================================
#
# Direction-independent force detection using acceleration magnitude.
# Computes absolute force as the deviation from resting gravity (9.81 m/s²),
# so the same physical motion triggers regardless of saber orientation.
# Uses an exponential moving average (EMA) for swing detection (sustained
# motion) and raw magnitude for hit detection (impact spikes).

class MotionEngine:
    """Direction-independent force detection via acceleration magnitude.

    Instead of tracking per-axis deltas, we compute the magnitude of the
    full acceleration vector and subtract gravity.  This yields a single
    force value in m/s² that is identical regardless of orientation.

    Two signals are produced each sample:
      - smoothed: EMA-filtered force for swing detection (sustained motion)
      - raw:      instantaneous force for hit detection (impact spikes)
    """

    _GRAVITY = 9.81  # m/s² — magnitude at rest

    def __init__(self, hw):
        self._hw = hw
        self._error_count = 0
        self._enabled = hw.accel is not None
        self._disabled_time = 0
        self._last_recovery = 0
        self._last_sample = 0
        self._last_diag = 0
        self._smoothed = 0.0

        # Public diagnostics
        self.last_raw = 0.0
        self.last_smoothed = 0.0

    def poll(self, now):
        """Sample accelerometer if interval elapsed.

        Returns (smoothed_force, raw_force) or None.
          - smoothed_force: EMA-filtered, use for swing detection
          - raw_force: instantaneous, use for hit/impact detection
        """
        if not self._enabled:
            return None
        if now - self._last_sample < ACCEL_SAMPLE_INTERVAL:
            return None
        self._last_sample = now
        if self._hw.accel is None:
            return None
        try:
            ax, ay, az = self._hw.accel.acceleration

            # Magnitude of the full acceleration vector (direction-independent)
            mag = math.sqrt(ax * ax + ay * ay + az * az)

            # Absolute force above rest — gravity cancels out regardless of
            # which way the sensor is oriented
            raw = abs(mag - self._GRAVITY)

            # Exponential moving average for swing detection
            a = UserConfig.SMOOTHING_FACTOR
            self._smoothed = self._smoothed * (1.0 - a) + raw * a

            self.last_raw = raw
            self.last_smoothed = self._smoothed
            self._error_count = 0
            return (self._smoothed, raw)
        except Exception as e:
            self._error_count += 1
            if self._error_count >= UserConfig.MAX_ACCEL_ERRORS:
                print("accel disabled ({} errs)".format(self._error_count))
                self._enabled = False
                self._disabled_time = now
            elif self._error_count % 5 == 0:
                print("accel err {}: {}".format(self._error_count, e))
            time.sleep(0.01)
            return None

    def try_recover(self, now):
        """Attempt recovery if disabled.  Call from maintenance path."""
        if self._enabled:
            return
        if now - self._last_recovery < UserConfig.ACCEL_RECOVERY_INTERVAL:
            return
        self._last_recovery = now
        print("accel recovery...")
        if self._hw.reinit_accel():
            self._enabled = True
            self._error_count = 0
            self._smoothed = 0.0
            print("accel recovered")

    def print_diag(self, now):
        if not UserConfig.ENABLE_DIAGNOSTICS:
            return
        if now - self._last_diag < UserConfig.ACCEL_OUTPUT_INTERVAL:
            return
        self._last_diag = now
        print("force: raw={:.1f} smooth={:.1f} m/s² (swing>{:.1f} hit>{:.1f})".format(
            self.last_raw, self.last_smoothed,
            UserConfig.SWING_THRESHOLD, UserConfig.HIT_THRESHOLD))


# =============================================================================
# LED ENGINE
# =============================================================================
#
# All LED writes are rate-limited to prevent audio DMA starvation.
# strip.show() for 55 RGBW pixels takes ~3.5 ms; we never call it more
# than once per frame.

class LEDEngine:
    """Frame-rate-limited LED strip + onboard pixel control."""

    def __init__(self, hw):
        self._hw = hw
        self._last_strip_update = 0
        self._last_strip_color = None
        self._pending_color = None    # color deferred by rate limiting
        self._strip_dirty = False

    # -- color helpers --------------------------------------------------------

    @staticmethod
    def mix(c1, c2, t):
        """Linearly interpolate two RGBW tuples.  t=0 → c1, t=1 → c2."""
        t = max(0.0, min(t, 1.0))
        s = 1.0 - t
        return (
            int(c1[0] * s + c2[0] * t),
            int(c1[1] * s + c2[1] * t),
            int(c1[2] * s + c2[2] * t),
            int(c1[3] * s + c2[3] * t),
        )

    @staticmethod
    def dim(color, factor):
        """Scale an RGBW color by factor (0-1)."""
        return tuple(int(c * factor) for c in color)

    # -- strip ----------------------------------------------------------------

    def strip_fill(self, color, now):
        """Fill strip with a solid color, respecting rate limit."""
        if not self._hw.strip:
            return
        if color == self._last_strip_color:
            return  # no change
        if now - self._last_strip_update < LED_MIN_INTERVAL:
            self._pending_color = color
            self._strip_dirty = True
            return  # too soon — will catch on next frame
        try:
            self._hw.strip.fill(color)
            self._hw.strip.show()
            self._last_strip_color = color
            self._last_strip_update = now
            self._strip_dirty = False
            self._pending_color = None
        except Exception as e:
            print("strip err:", e)

    def strip_fill_force(self, color):
        """Bypass rate limit (for power animation frames and final states)."""
        if not self._hw.strip:
            return
        try:
            self._hw.strip.fill(color)
            self._hw.strip.show()
            self._last_strip_color = color
            self._last_strip_update = time.monotonic()
            self._strip_dirty = False
        except Exception as e:
            print("strip err:", e)

    def strip_progressive(self, threshold, color, reverse=False):
        """Fill strip progressively (for power on/off animation)."""
        if not self._hw.strip:
            return
        try:
            n = HWConfig.NUM_PIXELS
            if not reverse:
                for i in range(n):
                    self._hw.strip[i] = color if i <= threshold else 0
            else:
                cutoff = n - threshold
                for i in range(n):
                    self._hw.strip[i] = color if i < cutoff else 0
            self._hw.strip.show()
            self._last_strip_update = time.monotonic()
            self._last_strip_color = None  # mixed state
            self._strip_dirty = False
        except Exception as e:
            print("strip prog err:", e)

    def set_brightness(self, value):
        if self._hw.strip:
            try:
                if self._hw.strip.brightness != value:
                    self._hw.strip.brightness = value
                    self._hw.strip.show()
            except Exception:
                pass

    def flush_if_dirty(self, now):
        """If a rate-limited write was skipped, flush the pending color."""
        if self._strip_dirty and self._pending_color is not None:
            if now - self._last_strip_update >= LED_MIN_INTERVAL:
                self.strip_fill_force(self._pending_color)
                self._pending_color = None

    # -- onboard pixels -------------------------------------------------------

    def onboard_off(self):
        if self._hw.onboard:
            try:
                self._hw.onboard.fill(0)
                self._hw.onboard.show()
            except Exception:
                pass

    def onboard_breathe(self, color_idle, now):
        """Gentle sine-wave pulse in idle color."""
        if not self._hw.onboard:
            return
        try:
            pulse = 0.65 + 0.35 * math.sin(now * math.pi)
            r = int(color_idle[0] * pulse)
            g = int(color_idle[1] * pulse)
            b = int(color_idle[2] * pulse)
            self._hw.onboard.fill((r, g, b))
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_spin(self, color, now, speed=12):
        """Spinning chase with dim trail."""
        if not self._hw.onboard:
            return
        try:
            n = HWConfig.ONBOARD_PIXELS
            pos = int(now * speed) % n
            c3 = color[:3]
            for i in range(n):
                if i == pos:
                    self._hw.onboard[i] = c3
                else:
                    dist = (pos - i) % n
                    fade = max(0, 1.0 - dist * 0.4)
                    self._hw.onboard[i] = (
                        int(color[0] * fade * 0.3),
                        int(color[1] * fade * 0.3),
                        int(color[2] * fade * 0.3),
                    )
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_flash(self, color_hit, color_idle, elapsed):
        """White flash then fade to idle."""
        if not self._hw.onboard:
            return
        try:
            if elapsed < 0.1:
                self._hw.onboard.fill((255, 255, 255))
            else:
                t = min((elapsed - 0.1) * 2, 1.0)
                r = int(color_hit[0] * (1 - t) + color_idle[0] * t)
                g = int(color_hit[1] * (1 - t) + color_idle[1] * t)
                b = int(color_hit[2] * (1 - t) + color_idle[2] * t)
                self._hw.onboard.fill((r, g, b))
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_lightning(self, color, now):
        """Random electrical crackle — overlapping sine waves create
        chaotic flicker that simulates arcs jumping between pixels."""
        if not self._hw.onboard:
            return
        try:
            n = HWConfig.ONBOARD_PIXELS
            for i in range(n):
                # Two sine products at irrational-ish frequencies per pixel
                v = (math.sin(now * 17.3 + i * 2.5)
                     * math.sin(now * 23.1 + i * 4.1))
                v += math.sin(now * 31.7 + i * 1.3) * 0.5
                if v > 0.6:
                    # Bright arc
                    self._hw.onboard[i] = (
                        min(255, int(color[0] + 80)),
                        min(255, int(color[1] + 80)),
                        min(255, int(color[2] + 80)),
                    )
                elif v > 0.1:
                    self._hw.onboard[i] = (
                        int(color[0] * 0.3),
                        int(color[1] * 0.3),
                        int(color[2] * 0.3),
                    )
                else:
                    self._hw.onboard[i] = (
                        int(color[0] * 0.05),
                        int(color[1] * 0.05),
                        int(color[2] * 0.05),
                    )
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_pulse(self, color, now):
        """Heartbeat double-pulse: lub-dub … lub-dub.
        Two quick beats followed by a longer rest period."""
        if not self._hw.onboard:
            return
        try:
            cycle = now % 1.2
            if cycle < 0.08:
                pulse = cycle / 0.08
            elif cycle < 0.16:
                pulse = 1.0 - (cycle - 0.08) / 0.08
            elif cycle < 0.28:
                pulse = 0.1
            elif cycle < 0.36:
                pulse = (cycle - 0.28) / 0.08 * 0.7
            elif cycle < 0.44:
                pulse = 0.7 - (cycle - 0.36) / 0.08 * 0.6
            else:
                pulse = 0.1
            r = int(color[0] * pulse)
            g = int(color[1] * pulse)
            b = int(color[2] * pulse)
            self._hw.onboard.fill((r, g, b))
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_fire(self, color, now):
        """Flickering flame — each pixel independently flutters at
        different rates, producing an organic fire-like shimmer."""
        if not self._hw.onboard:
            return
        try:
            n = HWConfig.ONBOARD_PIXELS
            for i in range(n):
                flicker = (
                    0.3
                    + 0.4 * abs(math.sin(now * (4.7 + i * 3.1) + i * 0.9))
                    + 0.3 * abs(math.sin(now * (7.3 + i * 1.7) + i * 2.3))
                )
                if flicker > 1.0:
                    flicker = 1.0
                self._hw.onboard[i] = (
                    int(color[0] * flicker),
                    int(color[1] * flicker),
                    int(color[2] * flicker),
                )
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_sparkle(self, color, now):
        """Random sparkle/twinkle — pixels briefly flash bright then
        fade quickly, creating a glittering effect."""
        if not self._hw.onboard:
            return
        try:
            n = HWConfig.ONBOARD_PIXELS
            for i in range(n):
                phase = (now * (3.7 + i * 2.3) + i * 1.1) % 1.0
                if phase < 0.12:
                    bright = 0.3 + 0.7 * math.sin(phase / 0.12 * math.pi)
                else:
                    bright = 0.08
                self._hw.onboard[i] = (
                    int(color[0] * bright),
                    int(color[1] * bright),
                    int(color[2] * bright),
                )
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_white_flash(self):
        """Instant white flash on all onboard pixels (used for hit impact)."""
        if not self._hw.onboard:
            return
        try:
            self._hw.onboard.fill((255, 255, 255))
            self._hw.onboard.show()
        except Exception:
            pass

    def onboard_animate(self, style, color, now):
        """Dispatch to the named onboard animation style."""
        if style == ANIM_BREATHE:
            self.onboard_breathe(color, now)
        elif style == ANIM_SPIN:
            self.onboard_spin(color, now)
        elif style == ANIM_LIGHTNING:
            self.onboard_lightning(color, now)
        elif style == ANIM_PULSE:
            self.onboard_pulse(color, now)
        elif style == ANIM_FIRE:
            self.onboard_fire(color, now)
        elif style == ANIM_SPARKLE:
            self.onboard_sparkle(color, now)

    def onboard_spinner(self, color, now):
        """Fast spinner for power transitions."""
        if not self._hw.onboard:
            return
        try:
            n = HWConfig.ONBOARD_PIXELS
            pos = int(now * 8) % n
            for i in range(n):
                self._hw.onboard[i] = color[:3] if i == pos else (0, 0, 0)
            self._hw.onboard.show()
        except Exception:
            pass


# =============================================================================
# SABER CONTROLLER
# =============================================================================

class SaberController:
    """
    Top-level coordinator.

    Main loop cadence (per frame, ~20 ms target):
      1. Feed watchdog                   (< 0.01 ms)
      2. Poll audio engine               (< 0.01 ms)
      3. Poll inputs                     (< 0.5 ms)
      4. Handle input actions            (varies)
      5. Process state logic             (< 0.5 ms)
      6. Update LEDs (strip + onboard)   (< 4 ms)
      7. Poll display timeout            (< 0.01 ms)
      8. Periodic maintenance (GC/batt)  (< 1 ms, occasionally 10 ms for batt)
      9. Sleep remainder of frame        (adaptive)
    """

    def __init__(self):
        print("\n=== SwingSaber v3.0 ===")
        self.hw = Hardware()
        self.audio = AudioEngine(self.hw.speaker_enable)
        self.display = Display(self.hw.read_battery_pct)
        self.input = InputManager(self.hw)
        self.motion = MotionEngine(self.hw)
        self.led = LEDEngine(self.hw)

        # State
        self.state = STATE_OFF
        self._state_start = time.monotonic()

        # Theme / settings
        self.theme_index = PersistentSettings.load_theme()
        self.audio.set_volume(PersistentSettings.load_volume())
        self.brightness_index = PersistentSettings.load_brightness()
        self.brightness = UserConfig.BRIGHTNESS_PRESETS[self.brightness_index]

        # Derived colors + animation styles
        self.color_full = (0, 0, 0, 0)
        self.color_idle = (0, 0, 0, 0)
        self.color_hit = (0, 0, 0, 0)
        self.idle_anim = ANIM_BREATHE
        self.swing_anim = ANIM_SPIN
        self.hit_anim = ANIM_LIGHTNING
        self._apply_theme()

        # Timing
        self._last_gc = time.monotonic()
        self._last_battery_check = 0
        self._last_battery_warning = 0

        # Power animation state (non-blocking)
        self._power_anim_start = 0

        # Diagnostics
        self._loop_count = 0

        self.display._off()
        print("theme={} vol={}% bright={}%".format(
            self.theme_index, self.audio.volume,
            UserConfig.BRIGHTNESS_LABELS[self.brightness_index]))
        print()

    # -- theme ----------------------------------------------------------------

    def _apply_theme(self):
        t = UserConfig.THEMES[self.theme_index]
        self.color_full = t["color"]
        self.color_idle = tuple(c // HWConfig.IDLE_COLOR_DIVISOR for c in t["color"])
        self.color_hit = t["hit_color"]
        self.idle_anim = t.get("idle_anim", ANIM_BREATHE)
        self.swing_anim = t.get("swing_anim", ANIM_SPIN)
        self.hit_anim = t.get("hit_anim", ANIM_LIGHTNING)

    def _cycle_theme(self):
        self.theme_index = (self.theme_index + 1) % len(UserConfig.THEMES)
        self._apply_theme()
        PersistentSettings.save_theme(self.theme_index)

    def _cycle_brightness(self):
        self.brightness_index = (self.brightness_index + 1) % len(UserConfig.BRIGHTNESS_PRESETS)
        self.brightness = UserConfig.BRIGHTNESS_PRESETS[self.brightness_index]
        PersistentSettings.save_brightness(self.brightness_index)
        if self.hw.strip:
            self.hw.strip.brightness = self.brightness
            self.hw.strip.show()
        pct = UserConfig.BRIGHTNESS_LABELS[self.brightness_index]
        print("Brightness: {}%".format(pct))
        return pct

    # -- state transitions ----------------------------------------------------

    def _change_state(self, new_state):
        """Single point of state change with validation."""
        if new_state == self.state:
            return True
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            print("BAD: {}->{}".format(
                _STATE_NAMES.get(self.state, "?"), _STATE_NAMES.get(new_state, "?")))
            return False
        old = self.state
        self.state = new_state
        self._state_start = time.monotonic()
        # Log meaningful transitions
        if old not in (STATE_POWER_ON, STATE_POWER_OFF) and new_state not in (STATE_POWER_ON, STATE_POWER_OFF):
            print("[{}->{}]".format(_STATE_NAMES.get(old, "?"), _STATE_NAMES.get(new_state, "?")))
        return True

    def _state_elapsed(self):
        return time.monotonic() - self._state_start

    # -- power animations (semi-blocking, but with watchdog feeds) ------------
    #
    # These are the ONLY place where we do a tight loop outside the main loop.
    # They feed the watchdog and sleep LED_MIN_INTERVAL between frames to
    # keep audio DMA happy.  Total duration: 1.15-1.7 s.

    def _animate_power_on(self):
        """Progressive blade ignition with audio."""
        self.led.set_brightness(self.brightness)
        self.audio.play(self.theme_index, "on", loop=False)
        start = time.monotonic()
        dur = HWConfig.POWER_ON_DURATION
        n = HWConfig.NUM_PIXELS

        while True:
            self.hw.feed_watchdog()
            elapsed = time.monotonic() - start
            if elapsed >= dur:
                break
            frac = math.sqrt(min(elapsed / dur, 1.0))
            thresh = int(n * frac + 0.5)
            self.led.strip_progressive(thresh, self.color_idle, reverse=False)
            self.led.onboard_spinner(self.color_full, time.monotonic())
            time.sleep(LED_MIN_INTERVAL)

        # Final state: full idle color
        self.led.strip_fill_force(self.color_idle)

        # Wait for power-on sound to finish (with watchdog + timeout)
        wait_start = time.monotonic()
        while self.audio.playing:
            self.hw.feed_watchdog()
            time.sleep(0.03)
            if time.monotonic() - wait_start > 3.0:
                print("audio wait timeout (on)")
                break

    def _animate_power_off(self):
        """Progressive blade retraction with audio."""
        self.audio.play(self.theme_index, "off", loop=False)
        start = time.monotonic()
        dur = HWConfig.POWER_OFF_DURATION
        n = HWConfig.NUM_PIXELS

        while True:
            self.hw.feed_watchdog()
            elapsed = time.monotonic() - start
            if elapsed >= dur:
                break
            frac = math.sqrt(min(elapsed / dur, 1.0))
            thresh = int(n * frac + 0.5)
            self.led.strip_progressive(thresh, self.color_idle, reverse=True)
            self.led.onboard_spinner(self.color_full, time.monotonic())
            time.sleep(LED_MIN_INTERVAL)

        # Final state: all dark
        self.led.strip_fill_force(0)
        self.led.onboard_off()

        # Wait for power-off sound to finish (with timeout)
        wait_start = time.monotonic()
        while self.audio.playing:
            self.hw.feed_watchdog()
            time.sleep(0.03)
            if time.monotonic() - wait_start > 3.0:
                print("audio wait timeout (off)")
                break

    # -- input actions --------------------------------------------------------

    def _handle_inputs(self):
        """Process all input events.  Returns True if an action consumed this frame."""

        # -- A3/A4: battery tap, volume long-press ----------------------------
        if self.input.long_press("a3"):
            vol = self.audio.increase_volume()
            PersistentSettings.save_volume(vol)
            self.display.show_volume(vol)
            return True
        if self.input.long_press("a4"):
            vol = self.audio.decrease_volume()
            PersistentSettings.save_volume(vol)
            self.display.show_volume(vol)
            return True
        if self.input.tap("a3") or self.input.tap("a4"):
            self.display.show_battery()
            return True

        # -- LEFT: theme tap, volume-preset long-press ------------------------
        if self.input.long_press("left"):
            vol = self.audio.cycle_volume_preset()
            PersistentSettings.save_volume(vol)
            self.display.show_volume(vol)
            return True

        if self.input.tap("left"):
            if self.state == STATE_OFF:
                self._cycle_theme()
                print("theme: {}".format(self.theme_index))
                self.audio.play(self.theme_index, "switch")
                self.display.show_image_async(self.theme_index, "logo")
            else:
                # Theme switch while on: power off first
                self._change_state(STATE_POWER_OFF)
                self._animate_power_off()
                self._change_state(STATE_OFF)
                self._cycle_theme()
                print("theme (on): {}".format(self.theme_index))
                self.audio.play(self.theme_index, "switch")
                self.display.show_image_async(self.theme_index, "logo")
            return True

        # -- RIGHT: power tap, brightness long-press --------------------------
        if self.input.long_press("right"):
            pct = self._cycle_brightness()
            self.display.show_brightness(pct)
            return True

        if self.input.tap("right"):
            if self.state == STATE_OFF:
                print("POWER ON")
                self._change_state(STATE_POWER_ON)
                self._animate_power_on()
                self.audio.play(self.theme_index, "idle", loop=True)
                self._change_state(STATE_IDLE)
            elif self.state in (STATE_IDLE, STATE_SWING, STATE_HIT):
                print("POWER OFF")
                self._change_state(STATE_POWER_OFF)
                self._animate_power_off()
                self._change_state(STATE_OFF)
            return True

        return False

    # -- per-frame state updates ----------------------------------------------

    def _update_state(self, now):
        """Run state-specific logic once per frame."""

        if self.state == STATE_OFF:
            # Ensure LEDs stay dark (covers boot, error recovery, missed cleanup)
            self.led.onboard_off()

        elif self.state == STATE_IDLE:
            # Idle brightness scales with user setting but stays low to
            # limit current draw on battery (55 pixels at full brightness
            # can pull >1.5 A).  Range: ~0.02 at 25% up to ~0.07 at 100%.
            idle_bright = self.brightness * 0.15
            self.led.set_brightness(idle_bright)
            self.led.strip_fill(self.color_idle, now)
            self.led.onboard_animate(self.idle_anim, self.color_idle, now)

            # Check for motion
            sample = self.motion.poll(now)
            if sample is not None:
                smoothed, raw = sample
                self.motion.print_diag(now)

                # Hit: raw force spike (catches sharp impacts)
                if raw > UserConfig.HIT_THRESHOLD:
                    print(">>> HIT: {:.1f} m/s²".format(raw))
                    self.audio.play(self.theme_index, "hit")
                    self.led.set_brightness(self.brightness)
                    self._change_state(STATE_HIT)

                # Swing: sustained force above threshold (smoothed rejects noise)
                elif smoothed > UserConfig.SWING_THRESHOLD:
                    print(">> SWING: {:.1f} m/s²".format(smoothed))
                    self.audio.play(self.theme_index, "swing")
                    self.led.set_brightness(self.brightness)
                    self._change_state(STATE_SWING)

        elif self.state == STATE_SWING:
            elapsed = self._state_elapsed()
            # Blend from swing color → idle color
            t = min(elapsed * 2.0, 1.0)
            color = self.led.mix(self.color_full, self.color_idle, t)
            self.led.strip_fill(color, now)
            self.led.onboard_animate(self.swing_anim, self.color_full, now - self._state_start)

            # Done when audio finishes (or fallback duration)
            if not self.audio.playing and elapsed >= HWConfig.SWING_DURATION_FALLBACK:
                self.audio.play(self.theme_index, "idle", loop=True)
                self.led.strip_fill_force(self.color_idle)
                self._change_state(STATE_IDLE)
            elif not self.audio.playing:
                # Audio done but still in fallback window — keep blending
                pass

        elif self.state == STATE_HIT:
            elapsed = self._state_elapsed()
            # Blend from hit color → idle color
            t = min(elapsed, 1.0)
            color = self.led.mix(self.color_hit, self.color_idle, t)
            self.led.strip_fill(color, now)
            # White flash for first 0.1s (impact feedback), then
            # configured animation with blending color
            if elapsed < 0.1:
                self.led.onboard_white_flash()
            else:
                anim_t = min((elapsed - 0.1) * 2, 1.0)
                anim_color = self.led.mix(self.color_hit, self.color_idle, anim_t)
                self.led.onboard_animate(self.hit_anim, anim_color, now)

            # Done when audio finishes (or fallback duration)
            if not self.audio.playing and elapsed >= HWConfig.HIT_DURATION_FALLBACK:
                self.audio.play(self.theme_index, "idle", loop=True)
                self.led.strip_fill_force(self.color_idle)
                self._change_state(STATE_IDLE)

    # -- maintenance ----------------------------------------------------------

    def _maintenance(self, now):
        """GC, battery check, accel recovery.  Runs every frame but most
        checks exit immediately via time guards."""

        # Critical memory — always check
        try:
            free = gc.mem_free()
            if free < UserConfig.CRITICAL_MEMORY_THRESHOLD:
                gc.collect()
                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("CRIT GC: {}->{}".format(free, gc.mem_free()))
        except Exception:
            pass

        # Regular GC — only when audio is NOT playing.  gc.collect() can
        # stall the CPU long enough to starve the mixer's DMA refill.
        if self.state == STATE_OFF:
            if now - self._last_gc > UserConfig.GC_INTERVAL:
                gc.collect()
                self._last_gc = now
                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("GC: {} free".format(gc.mem_free()))

        # Battery
        if now - self._last_battery_check > UserConfig.BATTERY_CHECK_INTERVAL:
            batt = self.hw.read_battery_pct()
            self._last_battery_check = now
            if UserConfig.ENABLE_DIAGNOSTICS:
                print("batt: {}".format(batt))
            if batt != "USB" and isinstance(batt, int):
                if batt <= UserConfig.BATTERY_CRITICAL_THRESHOLD:
                    if now - self._last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_warning(critical=True)
                        self._last_battery_warning = now
                elif batt <= UserConfig.BATTERY_WARNING_THRESHOLD:
                    if now - self._last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_warning(critical=False)
                        self._last_battery_warning = now

        # Accel recovery
        self.motion.try_recover(now)

    def _battery_warning(self, critical=False):
        """Flash strip for battery warning (only when off)."""
        if not self.hw.strip or self.state != STATE_OFF:
            return
        color = (255, 0, 0, 0) if critical else (255, 255, 0, 0)
        flashes = 3 if critical else 2
        label_text = "CRITICAL" if critical else "LOW"
        print("BATT {}: low!".format(label_text))
        try:
            for _ in range(flashes):
                self.hw.feed_watchdog()
                self.hw.strip.fill(color)
                self.hw.strip.show()
                time.sleep(0.12)
                self.hw.strip.fill(0)
                self.hw.strip.show()
                time.sleep(0.12)
        except Exception:
            pass

    # -- main loop ------------------------------------------------------------

    def run(self):
        print("=== SABER READY ===")
        print("force thresholds: swing>{:.1f} hit>{:.1f} m/s²".format(
            UserConfig.SWING_THRESHOLD, UserConfig.HIT_THRESHOLD))
        print("RIGHT=power  LEFT=theme")
        print("long: RIGHT=bright  LEFT=vol  A3=vol+  A4=vol-")
        print()

        consecutive_errors = 0
        try:
            while True:
                try:
                    frame_start = time.monotonic()
                    self._loop_count += 1

                    # 1. Watchdog — absolute first thing
                    self.hw.feed_watchdog()

                    # 2. Audio housekeeping (close finished files)
                    self.audio.poll()

                    # 3. Read all inputs (non-blocking edge detection)
                    self.input.poll()

                    # 4. Handle input actions
                    self._handle_inputs()

                    # 5. State-specific updates (motion, LED, animation)
                    now = time.monotonic()
                    self._update_state(now)

                    # 6. Flush any rate-limited LED writes that were deferred
                    self.led.flush_if_dirty(now)

                    # 7. Display timeout
                    self.display.poll()

                    # 8. Periodic maintenance
                    self._maintenance(now)

                    # 9. Adaptive sleep — hold frame cadence steady
                    elapsed = time.monotonic() - frame_start
                    remaining = FRAME_PERIOD - elapsed
                    if remaining > 0:
                        time.sleep(remaining)

                    consecutive_errors = 0

                except MemoryError:
                    gc.collect()
                    print("MEM recovered: {} free".format(gc.mem_free()))
                    consecutive_errors += 1

                except Exception as e:
                    print("loop err:", e)
                    consecutive_errors += 1
                    self.hw.feed_watchdog()
                    time.sleep(0.05)

                if consecutive_errors >= 20:
                    print("too many errors, restarting controller")
                    break

        except KeyboardInterrupt:
            print("\nShutdown...")
            self.cleanup()

    def cleanup(self):
        print("cleanup...")
        try:
            self.audio.cleanup()
        except Exception:
            pass
        try:
            self.display.cleanup()
        except Exception:
            pass
        try:
            self.hw.cleanup()
        except Exception:
            pass
        print("done.")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    MAX_RESTARTS = 5
    restarts = 0

    while restarts < MAX_RESTARTS:
        ctrl = None
        try:
            ctrl = SaberController()
            ctrl.run()
            # run() only returns on consecutive error threshold or KeyboardInterrupt
            break
        except KeyboardInterrupt:
            if ctrl:
                ctrl.cleanup()
            break
        except MemoryError:
            gc.collect()
            print("RESTART (mem): {} free".format(gc.mem_free()))
        except Exception as e:
            print("RESTART ({}): {}".format(restarts + 1, e))
        finally:
            if ctrl:
                try:
                    ctrl.cleanup()
                except Exception:
                    pass

        restarts += 1
        gc.collect()
        time.sleep(1.0)

    if restarts >= MAX_RESTARTS:
        print("max restarts reached, halting")


if __name__ == "__main__":
    main()
