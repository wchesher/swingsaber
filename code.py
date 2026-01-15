# =============================================================================
# SPDX-FileCopyrightText: 2021 John Park for Adafruit Industries
# SPDX-FileCopyrightText: © 2024-2025 William C. Chesher <wchesher@gmail.com>
# SPDX-License-Identifier: MIT
#
# SwingSaber v1.1 - Interactive Lightsaber Controller
# Target: Adafruit HalloWing M4 Express | CircuitPython 10.x
# =============================================================================
#
# PROJECT OVERVIEW:
# Firmware for a motion-controlled lightsaber toy. Detects movement via
# accelerometer and responds with LED animations and sound effects.
#
# HARDWARE: HalloWing M4 (ATSAMD51 processor, MSA311 accelerometer, 1.44" TFT,
# speaker, 4 touch pads, NeoPixel port, LiPo battery connector)
#
# KEY CONCEPTS:
# - State Machine: System is always in one state (OFF/IDLE/SWING/HIT/etc.)
# - Debouncing: Prevents multiple triggers from a single button press
# - Watchdog: Auto-resets device if code gets stuck
# =============================================================================

# === IMPORTS ===
# Libraries provide pre-built functionality (like tools from a toolbox)

import time      # Timing: sleep(), monotonic()
import gc        # Garbage Collector - frees unused memory
import math      # Math functions (sqrt, etc.)
import board     # Hardware pin definitions
import busio     # I2C/SPI communication buses
import neopixel  # Addressable RGB LED control
import audioio   # Audio output
import audiocore # WAV file handling
import adafruit_msa3xx  # Accelerometer driver
import touchio   # Capacitive touch input
import analogio  # Analog voltage reading
import supervisor  # System supervisor (USB detection, etc.)
import displayio  # Display/graphics management
import terminalio  # Built-in font
import microcontroller  # Low-level MCU access (NVM storage)
from digitalio import DigitalInOut
from adafruit_display_text import label
import array     # Efficient numeric arrays

# Watchdog: Hardware timer that resets device if code hangs
# Must be "fed" regularly to prove code is running
try:
    from watchdog import WatchDogMode
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# =============================================================================
# USER CONFIGURATION - Adjustable settings
# =============================================================================

class UserConfig:
    """User-adjustable settings. Modify these to customize behavior."""

    # Display (0.0-1.0 brightness)
    DISPLAY_BRIGHTNESS = 0.3
    DISPLAY_BRIGHTNESS_SAVER = 0.1
    DISPLAY_TIMEOUT_NORMAL = 2.0   # Seconds before auto-off
    DISPLAY_TIMEOUT_SAVER = 1.0

    # NeoPixel brightness (lower = less power, longer battery)
    # Max safe brightness ~40% with 1781 battery (1A limit)
    NEOPIXEL_IDLE_BRIGHTNESS = 0.05   # 5% when idle
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.25 # 25% default (middle preset)
    BRIGHTNESS_PRESETS = [0.15, 0.25, 0.35]  # 15%, 25%, 35%
    # LED update rate limiting (prevents audio lag from NeoPixel blocking)
    # 60 RGBW LEDs @ 800kHz = ~2.4ms blocking per update
    LED_UPDATE_INTERVAL = 0.05  # 50ms = 20 FPS max (gives audio DMA breathing room)

    # Main loop timing (balance responsiveness vs audio quality)
    # Faster loops can interfere with audio DMA on SAMD51
    IDLE_LOOP_DELAY = 0.05    # 50ms idle (20 Hz)
    ACTIVE_LOOP_DELAY = 0.025 # 25ms active (40 Hz) - gives audio DMA more time

    # Audio
    STOP_AUDIO_WHEN_IDLE = True
    DEFAULT_VOLUME = 70        # 0-100%
    VOLUME_STEP = 10
    MIN_VOLUME = 10
    MAX_VOLUME = 100
    # Audio fade duration for smooth transitions
    FADE_TRANSITION_DURATION = 0.1  # 100ms fade for smoother transitions
    VOLUME_PRESETS = [30, 50, 70, 100]
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_BITS_PER_SAMPLE = 8  # 8-bit unsigned for less CPU load

    # Motion detection
    NEAR_SWING_RATIO = 0.8  # 80% threshold for "almost" detection

    # Touch input
    TOUCH_DEBOUNCE_TIME = 0.02  # 20ms - ignore rapid re-triggers
    LONG_PRESS_TIME = 1.0       # 1 second hold = long press

    # Memory management
    MAX_IMAGE_CACHE_SIZE = 4
    GC_INTERVAL = 10.0              # Garbage collection interval
    CRITICAL_MEMORY_THRESHOLD = 8192  # Force GC below 8KB free

    # Monitoring
    ENABLE_DIAGNOSTICS = True
    ACCEL_OUTPUT_INTERVAL = 0.5     # Show accel values every 0.5s for tuning
    BATTERY_CHECK_INTERVAL = 30.0
    BATTERY_WARNING_THRESHOLD = 15   # Warn at 15%
    BATTERY_CRITICAL_THRESHOLD = 5   # Critical at 5%
    BATTERY_WARNING_INTERVAL = 60.0

    # Error recovery
    MAX_ACCEL_ERRORS = 10
    ERROR_RECOVERY_DELAY = 0.1
    ACCEL_RECOVERY_INTERVAL = 30.0  # Try to recover accelerometer

    # Watchdog
    ENABLE_WATCHDOG = True
    WATCHDOG_TIMEOUT = 8.0  # Reset if stuck for 8 seconds

    # Persistent settings (NVM - survives power-off)
    # Magic byte validates stored data isn't garbage
    ENABLE_PERSISTENT_SETTINGS = True
    NVM_THEME_OFFSET = 0
    NVM_VOLUME_OFFSET = 1
    NVM_BRIGHTNESS_OFFSET = 2
    NVM_MAGIC_OFFSET = 3
    NVM_MAGIC_VALUE = 0xAB


# =============================================================================
# HARDWARE CONFIGURATION - Physical constants
# =============================================================================

class SaberConfig:
    """Hardware configuration constants. Generally don't modify."""

    # Pin definitions
    CAP_PIN = board.CAP_PIN
    SPEAKER_ENABLE_PIN = board.SPEAKER_ENABLE
    VOLTAGE_MONITOR_PIN = board.VOLTAGE_MONITOR

    # NeoPixel (Adafruit 4914: RGBW strip, 60 LEDs/m)
    NUM_PIXELS = 60

    # Motion thresholds (magnitude squared to avoid slow sqrt)
    # At rest with gravity: ~96 (9.8²). Lower = more sensitive.
    SWING_THRESHOLD = 105   # ~10.2 m/s² (~1.04g) - lowered for better detection
    HIT_THRESHOLD = 135     # ~11.6 m/s² (~1.18g) - lowered for better detection

    # State machine states
    STATE_OFF = 0
    STATE_IDLE = 1
    STATE_SWING = 2
    STATE_HIT = 3
    STATE_TRANSITION = 4
    STATE_ERROR = 5

    # State names for console output
    STATE_NAMES = {
        0: "OFF",
        1: "IDLE",
        2: "SWING",
        3: "HIT",
        4: "TRANS",
        5: "ERROR",
    }

    # Valid state transitions (prevents invalid states)
    VALID_TRANSITIONS = {
        STATE_OFF: [STATE_TRANSITION, STATE_ERROR],
        STATE_IDLE: [STATE_SWING, STATE_HIT, STATE_TRANSITION, STATE_ERROR],
        STATE_SWING: [STATE_IDLE, STATE_TRANSITION, STATE_ERROR],  # Allow power-off from swing
        STATE_HIT: [STATE_IDLE, STATE_TRANSITION, STATE_ERROR],    # Allow power-off from hit
        STATE_TRANSITION: [STATE_OFF, STATE_IDLE, STATE_SWING, STATE_HIT, STATE_ERROR],
        STATE_ERROR: [STATE_OFF],
    }

    # Display timing
    DISPLAY_TIMEOUT_SAVER_ON = UserConfig.DISPLAY_TIMEOUT_SAVER
    DISPLAY_TIMEOUT_SAVER_OFF = UserConfig.DISPLAY_TIMEOUT_NORMAL
    IMAGE_DISPLAY_DURATION_SAVER_ON = 1.5
    IMAGE_DISPLAY_DURATION_SAVER_OFF = 3.0

    # Animation timing
    POWER_ON_DURATION = 1.7
    POWER_OFF_DURATION = 1.15
    FADE_OUT_DURATION = 0.5
    SWING_BLEND_MIDPOINT = 0.5
    SWING_BLEND_SCALE = 2.0

    # Battery (LiPo: 3.3V empty, 4.2V full)
    BATTERY_VOLTAGE_SAMPLES = 10
    BATTERY_MIN_VOLTAGE = 3.3
    BATTERY_MAX_VOLTAGE = 4.2
    BATTERY_ADC_MAX = 65535
    BATTERY_VOLTAGE_DIVIDER = 2

    # Audio buffer settings (larger buffer = smoother audio, more latency)
    SILENCE_SAMPLE_SIZE = 1024
    AUDIO_STOP_CHECK_INTERVAL = 0.03
    AUDIO_BUFFER_SIZE = 8192  # Increased for cleaner audio on SAMD51
    FADE_IN_SAMPLES = 100
    FADE_OUT_SAMPLES = 100

    # Themes: name, blade color (RGBW), hit/clash color
    # RGBW format: (Red, Green, Blue, White) - White channel adds brightness
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255, 0),   "hit_color": (255, 255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255, 0), "hit_color": (0, 200, 255, 0)},
        {"name": "ricknmorty", "color": (0, 255, 0, 0),   "hit_color": (255, 0, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0, 0), "hit_color": (255, 255, 255, 255)},
    ]

    IDLE_COLOR_DIVISOR = 4  # Dim idle color to 25%


# =============================================================================
# AUDIO UTILITIES
# =============================================================================

class AudioUtils:
    """Static audio processing helpers."""

    @staticmethod
    def scale_sample(sample, volume_percent):
        """Scale audio sample by volume (0-100). Clamps to 16-bit range."""
        if volume_percent >= 100:
            return sample
        if volume_percent <= 0:
            return 0
        scaled = int(sample * volume_percent / 100)
        return max(-32768, min(32767, scaled))

    @staticmethod
    def apply_fade_envelope(samples, fade_in_samples=100, fade_out_samples=100):
        """Apply fade in/out to prevent audio clicks. Modifies in place."""
        sample_count = len(samples)

        # Fade in
        for i in range(min(fade_in_samples, sample_count)):
            samples[i] = int(samples[i] * (i / fade_in_samples))

        # Fade out
        start_fade_out = max(0, sample_count - fade_out_samples)
        for i in range(start_fade_out, sample_count):
            samples[i] = int(samples[i] * ((sample_count - i) / fade_out_samples))

        return samples

    @staticmethod
    def create_silence(duration_ms, sample_rate=22050):
        """Create silent audio buffer."""
        num_samples = int((duration_ms / 1000.0) * sample_rate)
        silence = array.array("h", [0] * num_samples)
        return audiocore.RawSample(silence, sample_rate=sample_rate)


# =============================================================================
# PERSISTENT SETTINGS (NVM Storage)
# =============================================================================

class PersistentSettings:
    """Save/load settings to Non-Volatile Memory (survives power-off)."""

    @staticmethod
    def is_valid():
        """Check if NVM contains valid data (magic byte matches)."""
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            return microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] == UserConfig.NVM_MAGIC_VALUE
        except Exception:
            return False

    @staticmethod
    def load_theme():
        """Load theme index from NVM (returns 0 if invalid)."""
        if not PersistentSettings.is_valid():
            return 0
        try:
            theme = microcontroller.nvm[UserConfig.NVM_THEME_OFFSET]
            if theme < len(SaberConfig.THEMES):
                return theme
        except Exception:
            pass
        return 0

    @staticmethod
    def load_volume():
        """Load volume from NVM (returns default if invalid)."""
        if not PersistentSettings.is_valid():
            return UserConfig.DEFAULT_VOLUME
        try:
            volume = microcontroller.nvm[UserConfig.NVM_VOLUME_OFFSET]
            if UserConfig.MIN_VOLUME <= volume <= UserConfig.MAX_VOLUME:
                return volume
        except Exception:
            pass
        return UserConfig.DEFAULT_VOLUME

    @staticmethod
    def save_theme(theme_index):
        """Save theme to NVM."""
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            microcontroller.nvm[UserConfig.NVM_THEME_OFFSET] = theme_index
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("Error saving theme:", e)
            return False

    @staticmethod
    def save_volume(volume):
        """Save volume to NVM."""
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            microcontroller.nvm[UserConfig.NVM_VOLUME_OFFSET] = volume
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("Error saving volume:", e)
            return False

    @staticmethod
    def load_brightness():
        """Load brightness preset index from NVM (returns 1 if invalid)."""
        if not PersistentSettings.is_valid():
            return 1  # Default to middle preset (25%)
        try:
            index = microcontroller.nvm[UserConfig.NVM_BRIGHTNESS_OFFSET]
            if index < len(UserConfig.BRIGHTNESS_PRESETS):
                return index
        except Exception:
            pass
        return 1

    @staticmethod
    def save_brightness(brightness_index):
        """Save brightness preset index to NVM."""
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False
        try:
            microcontroller.nvm[UserConfig.NVM_BRIGHTNESS_OFFSET] = brightness_index
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("Error saving brightness:", e)
            return False


# =============================================================================
# HARDWARE SETUP
# =============================================================================

class SaberHardware:
    """Initialize and manage all hardware components."""

    def __init__(self):
        print("Initializing Saber Hardware...")

        self.hardware_status = {
            "strip": False, "touch": False, "accel": False, "battery": False
        }

        # Capacitive touch reference pin
        try:
            self.cap_pin = DigitalInOut(SaberConfig.CAP_PIN)
            self.cap_pin.switch_to_output(value=False)
        except Exception as e:
            print("  CAP_PIN error:", e)
            self.cap_pin = None

        # Speaker enable
        try:
            self.speaker_enable = DigitalInOut(SaberConfig.SPEAKER_ENABLE_PIN)
            self.speaker_enable.switch_to_output(value=True)
        except Exception as e:
            print("  SPEAKER_ENABLE error:", e)
            self.speaker_enable = None

        # Battery voltage monitor
        try:
            self.battery_voltage = analogio.AnalogIn(SaberConfig.VOLTAGE_MONITOR_PIN)
            self.hardware_status["battery"] = True
        except Exception as e:
            print("  VOLTAGE_MONITOR error:", e)
            self.battery_voltage = None

        self.strip = self._init_strip()
        self.touch_left = None
        self.touch_right = None
        self.touch_batt_a3 = None
        self.touch_batt_a4 = None
        self._init_touch()
        self.accel = self._init_accel()
        self.accel_error_count = 0

        print("Hardware init complete.")
        print("Status:", self.hardware_status)
        print()

    def _init_strip(self):
        """Initialize NeoPixel LED strip."""
        try:
            strip = neopixel.NeoPixel(
                board.EXTERNAL_NEOPIXEL,
                SaberConfig.NUM_PIXELS,
                brightness=UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS,
                auto_write=False,
                pixel_order=neopixel.GRBW
            )
            strip.fill(0)
            strip.show()
            print("  NeoPixel strip OK.")
            self.hardware_status["strip"] = True
            return strip
        except Exception as e:
            print("  NeoPixel error:", e)
            return None

    def _init_touch(self):
        """Initialize capacitive touch inputs."""
        try:
            self.touch_left = touchio.TouchIn(board.TOUCH1)
            self.touch_right = touchio.TouchIn(board.TOUCH4)
            self.touch_batt_a3 = touchio.TouchIn(board.A3)
            self.touch_batt_a4 = touchio.TouchIn(board.A4)
            print("  Touch inputs OK.")
            self.hardware_status["touch"] = True
        except Exception as e:
            print("  Touch error:", e)

    def _init_accel(self):
        """Initialize accelerometer. Store I2C bus reference to prevent GC."""
        try:
            self.i2c_bus = busio.I2C(board.SCL, board.SDA)
            accel = adafruit_msa3xx.MSA311(self.i2c_bus)
            print("  Accelerometer OK.")
            self.hardware_status["accel"] = True
            return accel
        except Exception as e:
            print("  Accel error:", e)
            self.i2c_bus = None
            return None

    def try_reinit_accel(self):
        """Attempt to recover failed accelerometer."""
        if self.accel is not None:
            return True
        try:
            if hasattr(self, 'i2c_bus') and self.i2c_bus is not None:
                try:
                    self.i2c_bus.deinit()
                except Exception:
                    pass
            self.i2c_bus = busio.I2C(board.SCL, board.SDA)
            self.accel = adafruit_msa3xx.MSA311(self.i2c_bus)
            self.hardware_status["accel"] = True
            self.accel_error_count = 0
            print("  Accelerometer recovered!")
            return True
        except Exception as e:
            print("  Accel reinit failed:", e)
            return False

    def cleanup(self):
        """Clean up hardware resources."""
        if self.strip:
            try:
                self.strip.fill(0)
                self.strip.show()
            except Exception:
                pass
        if self.speaker_enable:
            try:
                self.speaker_enable.value = False
            except Exception:
                pass
        if hasattr(self, 'i2c_bus') and self.i2c_bus is not None:
            try:
                self.i2c_bus.deinit()
            except Exception:
                pass


# =============================================================================
# AUDIO MANAGER
# =============================================================================

class AudioManager:
    """Handle audio playback with direct audioio (no mixer)."""

    def __init__(self, speaker_enable=None):
        self.speaker_enable = speaker_enable
        self.audio = None

        # Enable speaker output (required for HalloWing M4)
        if self.speaker_enable:
            self.speaker_enable.value = True
            print("  Speaker enabled.")

        try:
            self.audio = audioio.AudioOut(board.SPEAKER)
            print("Audio system OK (direct mode).")
        except Exception as e:
            print("Audio init error:", e)
            self.audio = None

        self.current_wave_file = None
        self.current_wav = None
        self.volume = UserConfig.DEFAULT_VOLUME
        self.volume_preset_index = 1

        # Fade state
        self.fade_start_time = None
        self.fade_duration = 0
        self.is_fading = False

        print("  Audio volume: {}%".format(self.volume))

    def _close_current_file(self):
        """Close current audio file (important for resource management)."""
        if self.current_wave_file is not None:
            try:
                self.current_wave_file.close()
            except Exception as e:
                print("Error closing audio file:", e)
            finally:
                self.current_wave_file = None
                self.current_wav = None

    def set_volume(self, volume_percent):
        self.volume = max(UserConfig.MIN_VOLUME, min(volume_percent, UserConfig.MAX_VOLUME))
        print("Volume: {}%".format(self.volume))
        return self.volume

    def increase_volume(self):
        return self.set_volume(self.volume + UserConfig.VOLUME_STEP)

    def decrease_volume(self):
        return self.set_volume(self.volume - UserConfig.VOLUME_STEP)

    def cycle_volume_preset(self):
        self.volume_preset_index = (self.volume_preset_index + 1) % len(UserConfig.VOLUME_PRESETS)
        return self.set_volume(UserConfig.VOLUME_PRESETS[self.volume_preset_index])

    def _load_and_process_wav(self, filename):
        try:
            wave_file = open(filename, "rb")
            wav = audiocore.WaveFile(wave_file)
            print("  WAV: {}Hz, {}ch, {}bit".format(
                wav.sample_rate, wav.channel_count, wav.bits_per_sample))
            return (wave_file, wav)
        except OSError:
            print("Audio file not found:", filename)
            return (None, None)
        except Exception as e:
            print("Error loading audio:", e)
            return (None, None)

    def play_audio_clip(self, theme_index, name, loop=False):
        """Play audio clip directly. File naming: sounds/[theme][name].wav"""
        if not self.audio:
            print("No audio available!")
            return False

        # Stop current playback and let DMA settle
        if self.audio.playing:
            self.audio.stop()
            time.sleep(0.01)  # Let audio DMA fully stop
        self._close_current_file()

        # Force GC before allocating new audio buffer
        gc.collect()

        filename = "sounds/{}{}.wav".format(theme_index, name)
        print("Playing:", filename)
        self.current_wave_file, self.current_wav = self._load_and_process_wav(filename)

        if self.current_wav is None:
            return False

        try:
            self.audio.play(self.current_wav, loop=loop)
            print("  Playing! loop={}".format(loop))
            return True
        except Exception as e:
            print("Error playing audio:", e)
            self._close_current_file()
            return False

    def stop_audio(self):
        if self.audio and self.audio.playing:
            self.audio.stop()

    def check_audio_done(self):
        if self.audio and not self.audio.playing and self.current_wave_file is not None:
            self._close_current_file()

    def start_fade_out(self, duration=None):
        if duration is None:
            duration = SaberConfig.FADE_OUT_DURATION
        self.fade_start_time = time.monotonic()
        self.fade_duration = duration
        self.is_fading = True

    def update_fade(self):
        """Update fade - stops audio after duration (no real fade without mixer)."""
        if not self.is_fading:
            return False

        elapsed = time.monotonic() - self.fade_start_time
        if elapsed >= self.fade_duration:
            self.stop_audio()
            self._close_current_file()
            self.is_fading = False
            return True
        return False

    def mute(self):
        """Temporarily mute audio (for display operations)."""
        if self.speaker_enable:
            self.speaker_enable.value = False

    def unmute(self):
        """Restore audio after mute."""
        if self.speaker_enable:
            self.speaker_enable.value = True

    def cleanup(self):
        self.stop_audio()
        self._close_current_file()
        if self.audio:
            self.audio.stop()


# =============================================================================
# DISPLAY MANAGER
# =============================================================================

class SaberDisplay:
    """Manage TFT display with LRU image caching."""

    def __init__(self, battery_voltage_ref, audio_manager=None):
        self.main_group = displayio.Group()
        self.audio_manager = audio_manager  # For muting during display ops

        try:
            board.DISPLAY.auto_refresh = True
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
        except Exception as e:
            print("Display init error:", e)

        # LRU cache: keeps recent images in memory for fast access
        self.image_cache = {}
        self.image_cache_order = []

        self.display_start_time = 0
        self.display_active = False
        self.display_timeout = SaberConfig.DISPLAY_TIMEOUT_SAVER_OFF
        self.get_battery_voltage_pct = battery_voltage_ref
        self.image_display_duration = SaberConfig.IMAGE_DISPLAY_DURATION_SAVER_OFF

        self.turn_off_screen()

    def turn_off_screen(self):
        try:
            board.DISPLAY.brightness = 0
        except Exception as e:
            print("Error turning off screen:", e)

    def update_display_timeout(self, timeout):
        self.display_timeout = timeout

    def update_image_display_duration(self, duration):
        self.image_display_duration = duration

    def update_power_saver_settings(self, saver_on):
        try:
            if saver_on:
                self.update_display_timeout(UserConfig.DISPLAY_TIMEOUT_SAVER)
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS_SAVER
            else:
                self.update_display_timeout(UserConfig.DISPLAY_TIMEOUT_NORMAL)
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
        except Exception as e:
            print("Error updating power saver settings:", e)

    def show_battery_status(self):
        """Show battery percentage with progress bar."""
        try:
            while len(self.main_group):
                self.main_group.pop()

            battery_percent = self.get_battery_voltage_pct()
            battery_text = "BATTERY: {}".format(
                "USB" if battery_percent == "USB" else "{}%".format(battery_percent))

            battery_label = label.Label(
                terminalio.FONT, text=battery_text, scale=2,
                color=0xFFFFFF, x=10, y=30)
            self.main_group.append(battery_label)

            if battery_percent != "USB":
                battery_bar_width = max(1, min(battery_percent, 100))
                battery_group = displayio.Group()

                bg_palette = displayio.Palette(1)
                bg_palette[0] = 0x444444
                bat_bg_bitmap = displayio.Bitmap(100, 14, 1)
                bat_bg_bitmap.fill(0)
                bg_tile = displayio.TileGrid(bat_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
                battery_group.append(bg_tile)

                bat_palette = displayio.Palette(1)
                bat_palette[0] = 0xFFFF00
                bat_bitmap = displayio.Bitmap(battery_bar_width, 10, 1)
                bat_bitmap.fill(0)
                bat_tile = displayio.TileGrid(bat_bitmap, pixel_shader=bat_palette, x=16, y=48)
                battery_group.append(bat_tile)
                self.main_group.append(battery_group)

            board.DISPLAY.root_group = self.main_group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing battery status:", e)

    def show_volume_status(self, volume_percent):
        """Show volume with progress bar."""
        try:
            while len(self.main_group):
                self.main_group.pop()

            volume_label = label.Label(
                terminalio.FONT, text="VOLUME: {}%".format(volume_percent),
                scale=2, color=0x00FF00, x=10, y=30)
            self.main_group.append(volume_label)

            volume_bar_width = max(1, min(volume_percent, 100))
            volume_group = displayio.Group()

            bg_palette = displayio.Palette(1)
            bg_palette[0] = 0x444444
            vol_bg_bitmap = displayio.Bitmap(100, 14, 1)
            vol_bg_bitmap.fill(0)
            bg_tile = displayio.TileGrid(vol_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
            volume_group.append(bg_tile)

            vol_palette = displayio.Palette(1)
            vol_palette[0] = 0x00FF00
            vol_bitmap = displayio.Bitmap(volume_bar_width, 10, 1)
            vol_bitmap.fill(0)
            vol_tile = displayio.TileGrid(vol_bitmap, pixel_shader=vol_palette, x=16, y=48)
            volume_group.append(vol_tile)
            self.main_group.append(volume_group)

            board.DISPLAY.root_group = self.main_group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing volume status:", e)

    def show_brightness_status(self, brightness_percent):
        """Show brightness with progress bar."""
        try:
            while len(self.main_group):
                self.main_group.pop()

            brightness_label = label.Label(
                terminalio.FONT, text="BRIGHT: {}%".format(brightness_percent),
                scale=2, color=0xFFFF00, x=10, y=30)
            self.main_group.append(brightness_label)

            # Scale to 0-100 for bar width (presets are 15-35%, scale to fill bar)
            bar_width = max(1, min(int(brightness_percent * 2.5), 100))
            brightness_group = displayio.Group()

            bg_palette = displayio.Palette(1)
            bg_palette[0] = 0x444444
            bright_bg_bitmap = displayio.Bitmap(100, 14, 1)
            bright_bg_bitmap.fill(0)
            bg_tile = displayio.TileGrid(bright_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
            brightness_group.append(bg_tile)

            bright_palette = displayio.Palette(1)
            bright_palette[0] = 0xFFFF00
            bright_bitmap = displayio.Bitmap(bar_width, 10, 1)
            bright_bitmap.fill(0)
            bright_tile = displayio.TileGrid(bright_bitmap, pixel_shader=bright_palette, x=16, y=48)
            brightness_group.append(bright_tile)
            self.main_group.append(brightness_group)

            board.DISPLAY.root_group = self.main_group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing brightness status:", e)

    def _evict_oldest_image(self):
        """Remove oldest image from cache (LRU eviction)."""
        if not self.image_cache_order:
            return
        oldest_key = self.image_cache_order.pop(0)
        if oldest_key in self.image_cache:
            try:
                del self.image_cache[oldest_key]
            except Exception:
                pass
        gc.collect()

    def _load_image(self, theme_index, image_type="logo"):
        """Load image with LRU caching."""
        cache_key = "{}{}".format(theme_index, image_type)

        if cache_key in self.image_cache:
            self.image_cache_order.remove(cache_key)
            self.image_cache_order.append(cache_key)
            return self.image_cache[cache_key]

        filename = "/images/{}{}.bmp".format(theme_index, image_type)
        try:
            if len(self.image_cache) >= UserConfig.MAX_IMAGE_CACHE_SIZE:
                self._evict_oldest_image()

            bitmap = displayio.OnDiskBitmap(filename)
            tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
            self.image_cache[cache_key] = tile_grid
            self.image_cache_order.append(cache_key)
            return tile_grid
        except Exception as e:
            print("Error loading image {}: {}".format(filename, e))
            return None

    def show_image(self, theme_index, image_type="logo", duration=None):
        """Display theme image (blocking, mutes audio to reduce display whine)."""
        if duration is None:
            duration = self.image_display_duration

        # Mute speaker during display refresh to reduce electrical noise
        if self.audio_manager:
            self.audio_manager.mute()

        try:
            while len(self.main_group):
                self.main_group.pop()

            image = self._load_image(theme_index, image_type)
            if image:
                self.main_group.append(image)
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
                board.DISPLAY.refresh()
                time.sleep(duration)
                while len(self.main_group):
                    self.main_group.pop()
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = 0

            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing image:", e)
        finally:
            if self.audio_manager:
                self.audio_manager.unmute()

    def show_image_async(self, theme_index, image_type="logo", duration=None):
        """Display theme image non-blocking (for use with simultaneous audio)."""
        if duration is None:
            duration = self.image_display_duration

        try:
            while len(self.main_group):
                self.main_group.pop()

            image = self._load_image(theme_index, image_type)
            if image:
                self.main_group.append(image)
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
                board.DISPLAY.refresh()

            # Set timeout for auto-off (handled by update_display)
            self.display_start_time = time.monotonic()
            self.display_timeout = duration
            self.display_active = True
        except Exception as e:
            print("Error showing image:", e)

    def update_display(self):
        """Handle display timeout (clears image group and turns off screen)."""
        if self.display_active:
            if time.monotonic() - self.display_start_time > self.display_timeout:
                # Clear the display group before turning off
                try:
                    while len(self.main_group):
                        self.main_group.pop()
                    board.DISPLAY.root_group = self.main_group
                except Exception:
                    pass
                self.turn_off_screen()
                self.display_active = False

    def clear_cache(self):
        self.image_cache.clear()
        self.image_cache_order.clear()
        gc.collect()

    def cleanup(self):
        self.clear_cache()
        self.turn_off_screen()


# =============================================================================
# MAIN CONTROLLER
# =============================================================================

class SaberController:
    """
    Main controller coordinating hardware, audio, and display.
    State Machine: OFF -> TRANSITION -> IDLE <-> SWING/HIT
    """

    def __init__(self):
        print("Booting SaberController...")

        self.hw = SaberHardware()
        self.audio = AudioManager(speaker_enable=self.hw.speaker_enable)
        self.display = SaberDisplay(self._get_battery_percentage, audio_manager=self.audio)

        self.power_saver_mode = False
        self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY
        self.mode = SaberConfig.STATE_OFF

        # Load persistent settings
        self.theme_index = PersistentSettings.load_theme()
        saved_volume = PersistentSettings.load_volume()
        self.audio.set_volume(saved_volume)
        self.brightness_preset_index = PersistentSettings.load_brightness()
        self.current_brightness = UserConfig.BRIGHTNESS_PRESETS[self.brightness_preset_index]
        print("  Loaded: theme={}, volume={}%, brightness={}%".format(
            self.theme_index, saved_volume, int(self.current_brightness * 100)))

        # Color state (RGBW format)
        self.color_idle = (0, 0, 0, 0)
        self.color_swing = (0, 0, 0, 0)
        self.color_hit = (0, 0, 0, 0)
        self.color_active = (0, 0, 0, 0)
        self.last_color = None

        # Timing
        self.event_start_time = 0
        self.last_gc_time = time.monotonic()
        self.last_battery_check = 0
        self.last_battery_warning = 0
        self.last_accel_recovery_attempt = 0
        self.last_led_update = 0  # LED frame rate limiter

        # Per-input touch state (independent debouncing for each button)
        self.touch_state = {
            'left': {'last_time': 0, 'press_start': 0, 'is_long_press': False},
            'right': {'last_time': 0, 'press_start': 0, 'is_long_press': False},
            'a3': {'last_time': 0, 'press_start': 0, 'is_long_press': False},
            'a4': {'last_time': 0, 'press_start': 0, 'is_long_press': False},
        }

        # Error tracking
        self.accel_error_count = 0
        self.accel_enabled = True
        self.accel_disabled_time = 0

        # Diagnostics
        self.loop_count = 0
        self.state_changes = 0
        self.last_accel_output = 0

        # Watchdog
        self.watchdog = None
        self._init_watchdog()

        self._update_theme_colors()
        self._apply_power_mode()
        self.display.turn_off_screen()
        print("SaberController init complete.\n")

    def _init_watchdog(self):
        """Initialize watchdog timer for crash recovery."""
        if not UserConfig.ENABLE_WATCHDOG or not WATCHDOG_AVAILABLE:
            return
        try:
            self.watchdog = microcontroller.watchdog
            self.watchdog.timeout = UserConfig.WATCHDOG_TIMEOUT
            self.watchdog.mode = WatchDogMode.RESET
            print("  Watchdog enabled ({}s)".format(UserConfig.WATCHDOG_TIMEOUT))
        except Exception as e:
            print("  Watchdog init failed:", e)
            self.watchdog = None

    def _feed_watchdog(self):
        """Feed watchdog to prevent reset."""
        if self.watchdog is not None:
            try:
                self.watchdog.feed()
            except Exception:
                pass

    def _apply_power_mode(self):
        if self.power_saver_mode:
            self.display.update_power_saver_settings(True)
            self.cpu_loop_delay = 0.03
        else:
            self.display.update_power_saver_settings(False)
            self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY

    def toggle_power_mode(self):
        self.power_saver_mode = not self.power_saver_mode
        self._apply_power_mode()
        print("Power saver:", "ON" if self.power_saver_mode else "OFF")

    def _get_battery_percentage(self):
        """Get battery percentage (returns "USB" if plugged in)."""
        if supervisor.runtime.usb_connected:
            return "USB"
        if not self.hw.battery_voltage:
            return 0

        try:
            sum_val = 0
            for _ in range(SaberConfig.BATTERY_VOLTAGE_SAMPLES):
                sum_val += self.hw.battery_voltage.value
                time.sleep(0.001)

            avg_val = sum_val / SaberConfig.BATTERY_VOLTAGE_SAMPLES
            voltage = (avg_val / SaberConfig.BATTERY_ADC_MAX) * \
                      self.hw.battery_voltage.reference_voltage * \
                      SaberConfig.BATTERY_VOLTAGE_DIVIDER

            percent = ((voltage - SaberConfig.BATTERY_MIN_VOLTAGE) /
                      (SaberConfig.BATTERY_MAX_VOLTAGE - SaberConfig.BATTERY_MIN_VOLTAGE)) * 100
            return min(max(int(percent), 0), 100)
        except Exception as e:
            print("Battery read error:", e)
            return 0

    def _update_theme_colors(self):
        """Update RGBW colors from current theme."""
        theme = SaberConfig.THEMES[self.theme_index]
        # Dim all 4 RGBW channels for idle color
        self.color_idle = tuple(int(c / SaberConfig.IDLE_COLOR_DIVISOR) for c in theme["color"])
        self.color_swing = theme["color"]
        self.color_hit = theme["hit_color"]

    def cycle_theme(self):
        self.theme_index = (self.theme_index + 1) % len(SaberConfig.THEMES)
        self._update_theme_colors()

    def cycle_brightness_preset(self):
        """Cycle through brightness presets and apply."""
        self.brightness_preset_index = (self.brightness_preset_index + 1) % len(UserConfig.BRIGHTNESS_PRESETS)
        self.current_brightness = UserConfig.BRIGHTNESS_PRESETS[self.brightness_preset_index]
        if self.hw.strip:
            self.hw.strip.brightness = self.current_brightness
            self.hw.strip.show()
        print("Brightness: {}%".format(int(self.current_brightness * 100)))
        return int(self.current_brightness * 100)

    def _transition_to_state(self, new_state):
        """Validate and execute state transition."""
        if new_state == self.mode:
            return True

        valid_next_states = SaberConfig.VALID_TRANSITIONS.get(self.mode, [])
        if new_state not in valid_next_states:
            old_name = SaberConfig.STATE_NAMES.get(self.mode, str(self.mode))
            new_name = SaberConfig.STATE_NAMES.get(new_state, str(new_state))
            print("INVALID: {} -> {}".format(old_name, new_name))
            return False

        old_state = self.mode
        self.mode = new_state
        self.state_changes += 1
        # Always show state transitions (except to/from TRANSITION state for cleaner output)
        if old_state != SaberConfig.STATE_TRANSITION and new_state != SaberConfig.STATE_TRANSITION:
            old_name = SaberConfig.STATE_NAMES.get(old_state, str(old_state))
            new_name = SaberConfig.STATE_NAMES.get(new_state, str(new_state))
            print("[{}->{}]".format(old_name, new_name))
        return True

    def _animate_power(self, name, duration, reverse):
        """Animate blade ignition/retraction."""
        if not self.hw.strip:
            return

        self.audio.stop_audio()
        self.audio.play_audio_clip(self.theme_index, name, loop=False)
        start_time = time.monotonic()

        while True:
            self._feed_watchdog()
            elapsed = time.monotonic() - start_time
            if elapsed > duration:
                break

            fraction = math.sqrt(min(elapsed / duration, 1.0))
            threshold = int(SaberConfig.NUM_PIXELS * fraction + 0.5)

            try:
                if not reverse:
                    for i in range(SaberConfig.NUM_PIXELS):
                        self.hw.strip[i] = self.color_idle if i <= threshold else 0
                else:
                    lit_end = SaberConfig.NUM_PIXELS - threshold
                    for i in range(SaberConfig.NUM_PIXELS):
                        self.hw.strip[i] = self.color_idle if i < lit_end else 0
                self.hw.strip.show()
                # Brief pause after LED update to let audio DMA catch up
                time.sleep(0.02)
            except Exception as e:
                print("Strip animation error:", e)
                break

        try:
            self.hw.strip.fill(0 if reverse else self.color_idle)
            self.hw.strip.show()
        except Exception:
            pass

        while self.audio.audio and self.audio.audio.playing:
            self._feed_watchdog()
            time.sleep(SaberConfig.AUDIO_STOP_CHECK_INTERVAL)

    def _get_touch_key(self, touch_input):
        """Map touch input to state key."""
        if touch_input == self.hw.touch_left:
            return 'left'
        elif touch_input == self.hw.touch_right:
            return 'right'
        elif touch_input == self.hw.touch_batt_a3:
            return 'a3'
        elif touch_input == self.hw.touch_batt_a4:
            return 'a4'
        return None

    def _check_touch_debounced(self, touch_input, touch_key=None):
        """Check touch with debouncing and long-press detection."""
        if not touch_input:
            return False

        if touch_key is None:
            touch_key = self._get_touch_key(touch_input)
        if touch_key is None or touch_key not in self.touch_state:
            return False

        state = self.touch_state[touch_key]

        try:
            if touch_input.value:
                now = time.monotonic()
                if state['press_start'] == 0:
                    state['press_start'] = now

                press_duration = now - state['press_start']
                if press_duration >= UserConfig.LONG_PRESS_TIME and not state['is_long_press']:
                    state['is_long_press'] = True
                    return False

                if now - state['last_time'] >= UserConfig.TOUCH_DEBOUNCE_TIME:
                    state['last_time'] = now
                    return True
            else:
                state['press_start'] = 0
                state['is_long_press'] = False
        except Exception as e:
            print("Touch read error:", e)

        return False

    def _check_long_press(self, touch_input, touch_key=None):
        if not touch_input:
            return False
        if touch_key is None:
            touch_key = self._get_touch_key(touch_input)
        if touch_key is None or touch_key not in self.touch_state:
            return False
        try:
            if touch_input.value and self.touch_state[touch_key]['is_long_press']:
                return True
        except Exception:
            pass
        return False

    def _wait_for_touch_release(self, touch_input, touch_key=None):
        """Wait for touch release (feeds watchdog during wait)."""
        if not touch_input:
            return
        if touch_key is None:
            touch_key = self._get_touch_key(touch_input)
        try:
            while touch_input.value:
                self._feed_watchdog()
                time.sleep(UserConfig.TOUCH_DEBOUNCE_TIME)
        except Exception:
            pass
        if touch_key and touch_key in self.touch_state:
            self.touch_state[touch_key]['press_start'] = 0
            self.touch_state[touch_key]['is_long_press'] = False

    def _handle_battery_touch(self):
        """A3/A4: Long press = volume, tap = battery status."""
        if self._check_long_press(self.hw.touch_batt_a3, 'a3'):
            new_vol = self.audio.increase_volume()
            PersistentSettings.save_volume(new_vol)
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a3, 'a3')
            return True

        if self._check_long_press(self.hw.touch_batt_a4, 'a4'):
            new_vol = self.audio.decrease_volume()
            PersistentSettings.save_volume(new_vol)
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a4, 'a4')
            return True

        if self._check_touch_debounced(self.hw.touch_batt_a3, 'a3') or \
           self._check_touch_debounced(self.hw.touch_batt_a4, 'a4'):
            self.display.show_battery_status()
            self._wait_for_touch_release(self.hw.touch_batt_a3, 'a3')
            self._wait_for_touch_release(self.hw.touch_batt_a4, 'a4')
            return True
        return False

    def _handle_theme_switch(self):
        """LEFT: Long press = volume presets, tap = theme switch."""
        if self._check_long_press(self.hw.touch_left, 'left'):
            preset_vol = self.audio.cycle_volume_preset()
            PersistentSettings.save_volume(preset_vol)
            self.display.show_volume_status(preset_vol)
            self._wait_for_touch_release(self.hw.touch_left, 'left')
            return True

        if not self._check_touch_debounced(self.hw.touch_left, 'left'):
            return False

        if self.mode == SaberConfig.STATE_OFF:
            old_theme = self.theme_index
            self.cycle_theme()
            PersistentSettings.save_theme(self.theme_index)
            print("Theme: {} -> {}".format(old_theme, self.theme_index))
            # Play switch sound and show image simultaneously (non-blocking)
            self.audio.play_audio_clip(self.theme_index, "switch")
            self.display.show_image_async(self.theme_index, "logo")
            self.event_start_time = time.monotonic()
        else:
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)

            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self._animate_power("off", duration=SaberConfig.POWER_OFF_DURATION, reverse=True)
            self._transition_to_state(SaberConfig.STATE_OFF)

            self.cycle_theme()
            PersistentSettings.save_theme(self.theme_index)
            print("Theme (while on): {}".format(self.theme_index))
            # Play switch sound and show image simultaneously (non-blocking)
            self.audio.play_audio_clip(self.theme_index, "switch")
            self.display.show_image_async(self.theme_index, "logo")
            self.event_start_time = time.monotonic()

        self._wait_for_touch_release(self.hw.touch_left, 'left')
        return True

    def _handle_power_toggle(self):
        """RIGHT: Long press = brightness presets, tap = power on/off."""
        # Long press cycles brightness presets
        if self._check_long_press(self.hw.touch_right, 'right'):
            brightness_pct = self.cycle_brightness_preset()
            PersistentSettings.save_brightness(self.brightness_preset_index)
            self.display.show_brightness_status(brightness_pct)
            self._wait_for_touch_release(self.hw.touch_right, 'right')
            return True

        if not self._check_touch_debounced(self.hw.touch_right, 'right'):
            return False

        if self.mode == SaberConfig.STATE_OFF:
            print("POWER ON - theme {}".format(self.theme_index))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self._animate_power("on", duration=SaberConfig.POWER_ON_DURATION, reverse=False)
            self.audio.play_audio_clip(self.theme_index, "idle", loop=True)
            self._transition_to_state(SaberConfig.STATE_IDLE)
            self.event_start_time = time.monotonic()
        else:
            print("POWER OFF - theme {}".format(self.theme_index))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)
            self._animate_power("off", duration=SaberConfig.POWER_OFF_DURATION, reverse=True)
            self._transition_to_state(SaberConfig.STATE_OFF)
            self.event_start_time = time.monotonic()

        self._wait_for_touch_release(self.hw.touch_right, 'right')
        return True

    def _read_acceleration_magnitude(self):
        """Read accelerometer. Returns (mag², x, y, z) or None."""
        if not self.accel_enabled or not self.hw.accel:
            return None

        try:
            accel_x, accel_y, accel_z = self.hw.accel.acceleration
            accel_magnitude_sq = accel_x**2 + accel_y**2 + accel_z**2
            self.accel_error_count = 0
            return (accel_magnitude_sq, accel_x, accel_y, accel_z)
        except Exception as e:
            self.accel_error_count += 1
            if self.accel_error_count >= UserConfig.MAX_ACCEL_ERRORS:
                print("Accelerometer disabled after {} errors".format(self.accel_error_count))
                self.accel_enabled = False
                self.accel_disabled_time = time.monotonic()
            elif self.accel_error_count % 5 == 0:
                print("Accel error {} of {}: {}".format(
                    self.accel_error_count, UserConfig.MAX_ACCEL_ERRORS, e))
            time.sleep(UserConfig.ERROR_RECOVERY_DELAY)
            return None

    def _try_recover_accelerometer(self):
        """Periodically attempt to recover disabled accelerometer."""
        if self.accel_enabled:
            return True
        now = time.monotonic()
        if now - self.last_accel_recovery_attempt < UserConfig.ACCEL_RECOVERY_INTERVAL:
            return False
        self.last_accel_recovery_attempt = now
        print("Attempting accelerometer recovery...")
        if self.hw.try_reinit_accel():
            self.accel_enabled = True
            self.accel_error_count = 0
            print("Accelerometer recovered!")
            return True
        return False

    def _handle_motion_detection(self):
        """Detect swing/hit from accelerometer."""
        if self.mode != SaberConfig.STATE_IDLE:
            return False

        accel_data = self._read_acceleration_magnitude()
        if accel_data is None:
            return False

        accel_magnitude_sq, accel_x, accel_y, accel_z = accel_data
        now = time.monotonic()

        # Periodic accel output for threshold tuning
        if UserConfig.ENABLE_DIAGNOSTICS:
            if now - self.last_accel_output >= UserConfig.ACCEL_OUTPUT_INTERVAL:
                self.last_accel_output = now
                # Show mag² relative to thresholds: swing=105, hit=135, rest~96
                print("accel: {:.0f} (swing>{} hit>{})".format(
                    accel_magnitude_sq,
                    SaberConfig.SWING_THRESHOLD,
                    SaberConfig.HIT_THRESHOLD))

        if accel_magnitude_sq > SaberConfig.HIT_THRESHOLD:
            print(">>> HIT: {:.0f}".format(accel_magnitude_sq))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)
            self.audio.play_audio_clip(self.theme_index, "hit")
            self.color_active = self.color_hit
            # Set event time AFTER fade completes so animation starts fresh
            self.event_start_time = time.monotonic()
            self.last_led_update = 0  # Force immediate LED update
            self._transition_to_state(SaberConfig.STATE_HIT)
            return True

        elif accel_magnitude_sq > SaberConfig.SWING_THRESHOLD:
            print(">> SWING: {:.0f}".format(accel_magnitude_sq))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)
            self.audio.play_audio_clip(self.theme_index, "swing")
            self.color_active = self.color_swing
            # Set event time AFTER fade completes so animation starts fresh
            self.event_start_time = time.monotonic()
            self.last_led_update = 0  # Force immediate LED update
            self._transition_to_state(SaberConfig.STATE_SWING)
            return True

        return False

    def _update_swing_hit_animation(self):
        """Blend colors during swing/hit animation."""
        if self.mode not in (SaberConfig.STATE_SWING, SaberConfig.STATE_HIT):
            return

        if self.audio.audio and self.audio.audio.playing:
            elapsed = time.monotonic() - self.event_start_time
            # Blend: 0 = full active color (swing/hit), 1 = full idle color
            # Start with active color, fade to idle over time
            if self.mode == SaberConfig.STATE_SWING:
                # Swing: fast fade from swing color to idle (0.5 seconds)
                blend = min(elapsed * 2.0, 1.0)
            else:
                # Hit: slower fade from hit color to idle (1 second)
                blend = min(elapsed, 1.0)
            self._fill_blend(self.color_active, self.color_idle, blend)
        else:
            self.audio.play_audio_clip(self.theme_index, "idle", loop=True)
            if self.hw.strip:
                try:
                    self.hw.strip.fill(self.color_idle)
                    self.hw.strip.show()
                    self.last_color = self.color_idle
                except Exception as e:
                    print("Strip update error:", e)
            self._transition_to_state(SaberConfig.STATE_IDLE)

    def _fill_blend(self, c1, c2, ratio):
        """Fill strip with blended color (rate-limited to prevent audio lag)."""
        if not self.hw.strip:
            return
        # Rate limit LED updates to prevent blocking audio DMA
        now = time.monotonic()
        if now - self.last_led_update < UserConfig.LED_UPDATE_INTERVAL:
            return  # Skip this update, too soon
        ratio = max(0, min(ratio, 1.0))
        color = self._mix_colors(c1, c2, ratio)
        if color != self.last_color:
            try:
                self.hw.strip.fill(color)
                self.hw.strip.show()
                self.last_color = color
                self.last_led_update = now
            except Exception as e:
                print("Strip blend error:", e)

    def _mix_colors(self, color1, color2, w2):
        """Linear interpolation between two RGBW colors."""
        w2 = max(0.0, min(w2, 1.0))
        w1 = 1.0 - w2
        return (
            int(color1[0] * w1 + color2[0] * w2),
            int(color1[1] * w1 + color2[1] * w2),
            int(color1[2] * w1 + color2[2] * w2),
            int(color1[3] * w1 + color2[3] * w2),
        )

    def _update_strip_brightness(self):
        """Adjust brightness based on state (uses current preset for active)."""
        if not self.hw.strip:
            return
        try:
            target = UserConfig.NEOPIXEL_IDLE_BRIGHTNESS if \
                self.mode == SaberConfig.STATE_IDLE else \
                self.current_brightness
            if self.hw.strip.brightness != target:
                self.hw.strip.brightness = target
        except Exception as e:
            print("Brightness error:", e)

    def _periodic_maintenance(self):
        """Run maintenance: GC, battery check, accel recovery."""
        now = time.monotonic()

        # Critical memory check
        try:
            mem_free = gc.mem_free()
            if mem_free < UserConfig.CRITICAL_MEMORY_THRESHOLD:
                gc.collect()
                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("CRITICAL GC: {} -> {} bytes".format(mem_free, gc.mem_free()))
        except Exception:
            pass

        # Regular GC when idle
        if self.mode in (SaberConfig.STATE_OFF, SaberConfig.STATE_IDLE):
            if now - self.last_gc_time > UserConfig.GC_INTERVAL:
                gc.collect()
                self.last_gc_time = now
                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("GC: {} bytes free".format(gc.mem_free()))

        # Battery monitoring
        if now - self.last_battery_check > UserConfig.BATTERY_CHECK_INTERVAL:
            battery = self._get_battery_percentage()
            self.last_battery_check = now
            if UserConfig.ENABLE_DIAGNOSTICS:
                print("Battery: {}".format(battery))

            if battery != "USB" and isinstance(battery, int):
                if battery <= UserConfig.BATTERY_CRITICAL_THRESHOLD:
                    if now - self.last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_critical_warning()
                        self.last_battery_warning = now
                elif battery <= UserConfig.BATTERY_WARNING_THRESHOLD:
                    if now - self.last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_low_warning()
                        self.last_battery_warning = now

        # Accelerometer recovery
        if not self.accel_enabled:
            self._try_recover_accelerometer()

    def _battery_low_warning(self):
        """Flash yellow twice for low battery warning."""
        print("WARNING: Low battery!")
        if self.hw.strip and self.mode == SaberConfig.STATE_OFF:
            try:
                for _ in range(2):
                    self.hw.strip.fill((255, 255, 0, 0))  # RGBW yellow
                    self.hw.strip.show()
                    time.sleep(0.15)
                    self.hw.strip.fill(0)
                    self.hw.strip.show()
                    time.sleep(0.15)
            except Exception:
                pass

    def _battery_critical_warning(self):
        """Flash red three times for critical battery."""
        print("CRITICAL: Battery very low!")
        if self.hw.strip and self.mode == SaberConfig.STATE_OFF:
            try:
                for _ in range(3):
                    self.hw.strip.fill((255, 0, 0, 0))  # RGBW red
                    self.hw.strip.show()
                    time.sleep(0.1)
                    self.hw.strip.fill(0)
                    self.hw.strip.show()
                    time.sleep(0.1)
            except Exception:
                pass

    def run(self):
        """Main event loop."""
        print("=== SABER READY ===")
        print("Thresholds: swing>{}, hit>{} (rest~96)".format(
            SaberConfig.SWING_THRESHOLD, SaberConfig.HIT_THRESHOLD))
        print("Controls: RIGHT=power, LEFT=theme")
        print("Long: RIGHT=bright, LEFT=vol, A3=vol+, A4=vol-")
        print()

        try:
            while True:
                self.loop_count += 1
                self._feed_watchdog()

                self.audio.update_fade()

                if self._handle_battery_touch():
                    continue
                if self._handle_theme_switch():
                    continue
                if self._handle_power_toggle():
                    continue

                self._handle_motion_detection()
                self._update_swing_hit_animation()
                self.display.update_display()
                self.audio.check_audio_done()
                self._update_strip_brightness()
                self._periodic_maintenance()

                if self.mode == SaberConfig.STATE_IDLE:
                    time.sleep(UserConfig.IDLE_LOOP_DELAY)
                else:
                    time.sleep(UserConfig.ACTIVE_LOOP_DELAY)

        except KeyboardInterrupt:
            print("\nShutdown...")
            self.cleanup()
        except MemoryError as e:
            print("\nMEMORY ERROR:", e)
            gc.collect()
            print("Recovery: {} bytes free".format(gc.mem_free()))
        except Exception as e:
            print("\nFATAL:", e)
            self.cleanup()
            raise

    def cleanup(self):
        """Clean up all resources."""
        print("Cleaning up...")
        if self.watchdog is not None:
            try:
                self.watchdog.mode = None
                print("  Watchdog disabled")
            except Exception:
                pass
        try:
            self.audio.cleanup()
            self.display.cleanup()
            self.hw.cleanup()
            print("Cleanup complete.")
        except Exception as e:
            print("Cleanup error:", e)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    controller = None
    try:
        controller = SaberController()
        controller.run()
    except Exception as e:
        print("\nFATAL:", e)
        if controller:
            controller.cleanup()
        raise


if __name__ == "__main__":
    main()
