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

# Watchdog: Hardware timer that resets device if code hangs
# Must be "fed" regularly to prove code is running
try:
    from watchdog import WatchDogMode
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# =============================================================================
# USER SETTINGS - Customize these to make the saber your own!
# =============================================================================

class UserConfig:
    """Settings you'll want to customize. Most important ones are at the top!"""

    # ==========================================================================
    # THEMES - Your saber's personality! Change colors and sounds here.
    # ==========================================================================
    # Each theme needs matching sound files in /sounds folder:
    #   0on.wav, 0off.wav, 0idle.wav, 0swing.wav, 0hit.wav, 0switch.wav
    #   1on.wav, 1off.wav, etc. (number matches theme index)
    #
    # Colors are RGBW format: (Red, Green, Blue, White) each 0-255
    #   Red only:    (255, 0, 0, 0)
    #   Green only:  (0, 255, 0, 0)
    #   Blue only:   (0, 0, 255, 0)
    #   Purple:      (255, 0, 255, 0)
    #   White:       (0, 0, 0, 255) or (255, 255, 255, 255)
    #
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255, 0),   "hit_color": (255, 255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255, 0), "hit_color": (0, 200, 255, 0)},
        {"name": "ricknmorty", "color": (0, 255, 0, 0),   "hit_color": (255, 0, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0, 0), "hit_color": (255, 255, 255, 255)},
    ]

    # ==========================================================================
    # MOTION SENSITIVITY - How easily swings and hits trigger
    # ==========================================================================
    # Watch console output to tune: "delta: 5.2 (swing>15 hit>40)"
    # Lower = more sensitive, Higher = needs bigger movements
    #
    SWING_THRESHOLD = 15    # Gentle swing triggers at this level
    HIT_THRESHOLD = 40      # Hard impact/clash triggers at this level

    # ==========================================================================
    # BRIGHTNESS - How bright the blade glows
    # ==========================================================================
    # Long-press RIGHT button to cycle through these presets
    # Max safe brightness ~40% with 1781 battery (1A current limit)
    #
    BRIGHTNESS_PRESETS = [0.15, 0.25, 0.35]  # 15%, 25%, 35%
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.25        # Default brightness (25%)
    NEOPIXEL_IDLE_BRIGHTNESS = 0.05          # Dim glow when idle (5%)

    # ==========================================================================
    # VOLUME - Sound levels
    # ==========================================================================
    # Long-press LEFT button to cycle through these presets
    #
    VOLUME_PRESETS = [30, 50, 70, 100]  # Quiet, Medium, Loud, Max
    DEFAULT_VOLUME = 70

    # ==========================================================================
    # DISPLAY - Screen settings
    # ==========================================================================
    DISPLAY_BRIGHTNESS = 0.3       # Screen brightness (0.0-1.0)
    DISPLAY_TIMEOUT_NORMAL = 2.0   # Seconds before screen auto-off

    # ==========================================================================
    # LESS COMMON SETTINGS - You probably don't need to change these
    # ==========================================================================

    # Volume fine-tuning
    VOLUME_STEP = 10    # How much A3/A4 long-press changes volume
    MIN_VOLUME = 10
    MAX_VOLUME = 100

    # Console output (set to False to hide accelerometer readings)
    ENABLE_DIAGNOSTICS = True
    ACCEL_OUTPUT_INTERVAL = 0.5   # How often to show accel values (seconds)

    # Touch input timing
    TOUCH_DEBOUNCE_TIME = 0.02  # Ignore rapid re-triggers (20ms)
    LONG_PRESS_TIME = 1.0       # Hold time for long press (1 second)

    # ==========================================================================
    # ADVANCED SETTINGS - Only change if you know what you're doing
    # ==========================================================================

    # Loop timing (affects responsiveness vs audio quality)
    IDLE_LOOP_DELAY = 0.05      # 50ms between checks when idle
    ACTIVE_LOOP_DELAY = 0.025   # 25ms between checks when active
    LED_UPDATE_INTERVAL = 0.05  # 50ms between LED updates (20 FPS)

    # Audio processing
    STOP_AUDIO_WHEN_IDLE = True
    FADE_TRANSITION_DURATION = 0.1  # Audio fade time (100ms)
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_BITS_PER_SAMPLE = 8

    # Battery monitoring
    BATTERY_CHECK_INTERVAL = 30.0    # Check every 30 seconds
    BATTERY_WARNING_THRESHOLD = 15   # Warn at 15%
    BATTERY_CRITICAL_THRESHOLD = 5   # Critical at 5%
    BATTERY_WARNING_INTERVAL = 60.0  # Don't spam warnings

    # Memory management
    MAX_IMAGE_CACHE_SIZE = 4
    GC_INTERVAL = 10.0
    CRITICAL_MEMORY_THRESHOLD = 8192

    # Error recovery
    MAX_ACCEL_ERRORS = 10
    ERROR_RECOVERY_DELAY = 0.1
    ACCEL_RECOVERY_INTERVAL = 30.0

    # Watchdog (auto-reset if code freezes)
    ENABLE_WATCHDOG = True
    WATCHDOG_TIMEOUT = 8.0

    # Persistent storage addresses (don't change)
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

    # NeoPixel LED strip (RGBW strip)
    NUM_PIXELS = 55
    IDLE_COLOR_DIVISOR = 4  # Dim idle color to 25% of full brightness

    # Onboard NeoPixels (HalloWing M4 has 4 RGB pixels around the eye)
    ONBOARD_PIXELS = 4
    ONBOARD_BRIGHTNESS = 0.3

    # ==========================================================================
    # STATE MACHINE - The saber is always in exactly ONE of these states
    # ==========================================================================
    # Think of states like modes: the saber behaves differently in each one.
    # OFF -> user presses power -> IDLE (blade on, waiting for motion)
    # IDLE -> user swings -> SWING (play swing sound/animation)
    # IDLE -> user hits something -> HIT (play clash sound/animation)
    # Any state -> user presses power -> OFF (blade retracts)

    STATE_OFF = 0         # Blade is dark, saber is "sleeping"
    STATE_IDLE = 1        # Blade is lit, waiting for motion
    STATE_SWING = 2       # Swing detected, playing swing effect
    STATE_HIT = 3         # Impact detected, playing clash effect
    STATE_TRANSITION = 4  # Animating between states (power on/off)
    STATE_ERROR = 5       # Something went wrong

    # Human-readable names for console output
    STATE_NAMES = {0: "OFF", 1: "IDLE", 2: "SWING", 3: "HIT", 4: "TRANS", 5: "ERROR"}

    # Which state transitions are allowed (prevents bugs from impossible states)
    # Format: FROM_STATE: [list of allowed TO_STATES]
    VALID_TRANSITIONS = {
        STATE_OFF: [STATE_TRANSITION, STATE_ERROR],
        STATE_IDLE: [STATE_SWING, STATE_HIT, STATE_TRANSITION, STATE_ERROR],
        STATE_SWING: [STATE_IDLE, STATE_TRANSITION, STATE_ERROR],
        STATE_HIT: [STATE_IDLE, STATE_TRANSITION, STATE_ERROR],
        STATE_TRANSITION: [STATE_OFF, STATE_IDLE, STATE_SWING, STATE_HIT, STATE_ERROR],
        STATE_ERROR: [STATE_OFF],
    }

    # Display timing
    DISPLAY_TIMEOUT = UserConfig.DISPLAY_TIMEOUT_NORMAL
    IMAGE_DISPLAY_DURATION = 3.0

    # Animation timing
    POWER_ON_DURATION = 1.7
    POWER_OFF_DURATION = 1.15
    FADE_OUT_DURATION = 0.5
    SWING_BLEND_MIDPOINT = 0.5
    SWING_BLEND_SCALE = 2.0
    # Fallback durations when audio files are missing
    SWING_DURATION_NO_AUDIO = 0.5  # Swing animation without audio
    HIT_DURATION_NO_AUDIO = 0.8    # Hit animation without audio

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


# =============================================================================
# PERSISTENT SETTINGS (NVM Storage)
# Saves settings to chip memory so they survive power-off
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
            if theme < len(UserConfig.THEMES):
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
        self.onboard = self._init_onboard_pixels()
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

    def _init_onboard_pixels(self):
        """Initialize onboard NeoPixels (around the eye on HalloWing M4)."""
        try:
            pixels = neopixel.NeoPixel(
                board.NEOPIXEL,
                SaberConfig.ONBOARD_PIXELS,
                brightness=SaberConfig.ONBOARD_BRIGHTNESS,
                auto_write=False
            )
            pixels.fill(0)
            pixels.show()
            print("  Onboard pixels OK.")
            return pixels
        except Exception as e:
            print("  Onboard pixels error:", e)
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
            return (wave_file, wav)
        except OSError:
            # Audio file not found - this is OK, device works without sounds
            print("  (no audio: {})".format(filename))
            return (None, None)
        except Exception as e:
            print("  Audio error:", e)
            return (None, None)

    def play_audio_clip(self, theme_index, name, loop=False):
        """Play audio clip. Works even if file is missing."""
        if not self.audio:
            return False

        # Stop current playback and let DMA settle
        if self.audio.playing:
            self.audio.stop()
            time.sleep(0.01)
        self._close_current_file()

        gc.collect()

        filename = "sounds/{}{}.wav".format(theme_index, name)
        self.current_wave_file, self.current_wav = self._load_and_process_wav(filename)

        if self.current_wav is None:
            return False  # File not found - that's OK

        try:
            self.audio.play(self.current_wav, loop=loop)
            return True
        except Exception as e:
            print("Audio play error:", e)
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
        self.display_timeout = SaberConfig.DISPLAY_TIMEOUT
        self.get_battery_voltage_pct = battery_voltage_ref
        self.image_display_duration = SaberConfig.IMAGE_DISPLAY_DURATION

        self.turn_off_screen()

    def turn_off_screen(self):
        try:
            board.DISPLAY.brightness = 0
        except Exception as e:
            print("Error turning off screen:", e)

    def _show_status_with_bar(self, title, value, color, bar_width=None):
        """Helper: Show status text with optional progress bar.

        Args:
            title: Label text (e.g., "VOLUME: 70%")
            value: Numeric value for bar width (0-100), or None to skip bar
            color: Hex color for text and bar (e.g., 0x00FF00 for green)
            bar_width: Override bar width (default: use value directly)
        """
        try:
            # Clear previous display content
            while len(self.main_group):
                self.main_group.pop()

            # Add text label
            text_label = label.Label(
                terminalio.FONT, text=title, scale=2, color=color, x=10, y=30)
            self.main_group.append(text_label)

            # Add progress bar if value provided
            if value is not None:
                width = bar_width if bar_width is not None else max(1, min(value, 100))
                bar_group = displayio.Group()

                # Gray background bar
                bg_palette = displayio.Palette(1)
                bg_palette[0] = 0x444444
                bg_bitmap = displayio.Bitmap(100, 14, 1)
                bg_bitmap.fill(0)
                bar_group.append(displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette, x=14, y=46))

                # Colored fill bar
                fill_palette = displayio.Palette(1)
                fill_palette[0] = color
                fill_bitmap = displayio.Bitmap(width, 10, 1)
                fill_bitmap.fill(0)
                bar_group.append(displayio.TileGrid(fill_bitmap, pixel_shader=fill_palette, x=16, y=48))

                self.main_group.append(bar_group)

            # Show on display
            board.DISPLAY.root_group = self.main_group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing status:", e)

    def show_battery_status(self):
        """Show battery percentage with progress bar."""
        battery = self.get_battery_voltage_pct()
        if battery == "USB":
            self._show_status_with_bar("BATTERY: USB", None, 0xFFFFFF)
        else:
            self._show_status_with_bar("BATTERY: {}%".format(battery), battery, 0xFFFF00)

    def show_volume_status(self, volume_percent):
        """Show volume with progress bar."""
        self._show_status_with_bar("VOLUME: {}%".format(volume_percent), volume_percent, 0x00FF00)

    def show_brightness_status(self, brightness_percent):
        """Show brightness with progress bar (scaled for 15-35% range)."""
        # Scale brightness to fill bar (15% -> ~38, 35% -> ~88)
        bar_width = max(1, min(int(brightness_percent * 2.5), 100))
        self._show_status_with_bar("BRIGHT: {}%".format(brightness_percent), brightness_percent, 0xFFFF00, bar_width)

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
        except OSError:
            # Image file not found - this is OK, device works without images
            print("(no image: {})".format(filename))
            return None
        except Exception as e:
            print("Image error {}: {}".format(filename, e))
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

        # Touch button state tracking (for debouncing and long-press detection)
        # Each button tracks: when last triggered, when press started, if it's a long press
        def new_touch_state():
            return {'last_time': 0, 'press_start': 0, 'is_long_press': False}
        self.touch_state = {
            'left': new_touch_state(), 'right': new_touch_state(),
            'a3': new_touch_state(), 'a4': new_touch_state()
        }

        # Error tracking
        self.accel_error_count = 0
        self.accel_enabled = True
        self.accel_disabled_time = 0

        # Delta-based motion detection (previous acceleration for change detection)
        self.prev_accel = (0.0, 0.0, 0.0)

        # Diagnostics
        self.loop_count = 0
        self.state_changes = 0
        self.last_accel_output = 0

        # Watchdog
        self.watchdog = None
        self._init_watchdog()

        self._update_theme_colors()
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
        theme = UserConfig.THEMES[self.theme_index]
        # Dim all 4 RGBW channels for idle color
        self.color_idle = tuple(int(c / SaberConfig.IDLE_COLOR_DIVISOR) for c in theme["color"])
        self.color_swing = theme["color"]
        self.color_hit = theme["hit_color"]

    def cycle_theme(self):
        self.theme_index = (self.theme_index + 1) % len(UserConfig.THEMES)
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
                # Use same rate limiting as swing/hit animations to prevent audio buffer underruns
                time.sleep(UserConfig.LED_UPDATE_INTERVAL)
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

    def _read_acceleration_delta(self):
        """Read accelerometer and calculate delta from previous reading.

        Returns (delta_mag², delta_x, delta_y, delta_z, raw_x, raw_y, raw_z) or None.
        Delta-based detection ignores gravity since it measures CHANGE in acceleration.
        """
        if not self.accel_enabled or not self.hw.accel:
            return None

        try:
            accel_x, accel_y, accel_z = self.hw.accel.acceleration

            # Calculate delta (change from previous reading)
            delta_x = accel_x - self.prev_accel[0]
            delta_y = accel_y - self.prev_accel[1]
            delta_z = accel_z - self.prev_accel[2]
            delta_mag_sq = delta_x**2 + delta_y**2 + delta_z**2

            # Store current as previous for next iteration
            self.prev_accel = (accel_x, accel_y, accel_z)

            self.accel_error_count = 0
            return (delta_mag_sq, delta_x, delta_y, delta_z, accel_x, accel_y, accel_z)
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
        """Detect swing/hit from accelerometer using delta (change in acceleration)."""
        if self.mode != SaberConfig.STATE_IDLE:
            return False

        accel_data = self._read_acceleration_delta()
        if accel_data is None:
            return False

        delta_mag_sq, delta_x, delta_y, delta_z, raw_x, raw_y, raw_z = accel_data
        now = time.monotonic()

        # Periodic output for threshold tuning (delta-based, rest ~0)
        if UserConfig.ENABLE_DIAGNOSTICS:
            if now - self.last_accel_output >= UserConfig.ACCEL_OUTPUT_INTERVAL:
                self.last_accel_output = now
                print("delta: {:.1f} (swing>{} hit>{})".format(
                    delta_mag_sq,
                    UserConfig.SWING_THRESHOLD,
                    UserConfig.HIT_THRESHOLD))

        if delta_mag_sq > UserConfig.HIT_THRESHOLD:
            print(">>> HIT: {:.1f}".format(delta_mag_sq))
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

        elif delta_mag_sq > UserConfig.SWING_THRESHOLD:
            print(">> SWING: {:.1f}".format(delta_mag_sq))
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
        """Blend colors during swing/hit animation.

        Works with or without audio files:
        - With audio: animation runs while audio plays
        - Without audio: uses fallback duration timers
        """
        if self.mode not in (SaberConfig.STATE_SWING, SaberConfig.STATE_HIT):
            return

        elapsed = time.monotonic() - self.event_start_time
        audio_playing = self.audio.audio and self.audio.audio.playing

        # Determine if animation should continue (audio playing OR within fallback duration)
        if self.mode == SaberConfig.STATE_SWING:
            fallback_duration = SaberConfig.SWING_DURATION_NO_AUDIO
            blend = min(elapsed * 2.0, 1.0)  # 0.5 second blend
        else:
            fallback_duration = SaberConfig.HIT_DURATION_NO_AUDIO
            blend = min(elapsed, 1.0)  # 1 second blend

        # Continue animation if audio playing OR still within fallback time
        if audio_playing or elapsed < fallback_duration:
            self._fill_blend(self.color_active, self.color_idle, blend)
        else:
            # Animation done - return to idle
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

    def _update_onboard_pixels(self):
        """Update the 4 onboard NeoPixels with slick state-based effects."""
        if not self.hw.onboard:
            return

        try:
            now = time.monotonic()
            n = SaberConfig.ONBOARD_PIXELS

            if self.mode == SaberConfig.STATE_OFF:
                # Dark when off
                self.hw.onboard.fill(0)

            elif self.mode == SaberConfig.STATE_IDLE:
                # Gentle breathing pulse in theme color
                # Sine wave pulse: 0.3 to 1.0 brightness over 2 seconds
                pulse = 0.65 + 0.35 * math.sin(now * math.pi)  # 0.3 to 1.0
                r = int(self.color_idle[0] * pulse)
                g = int(self.color_idle[1] * pulse)
                b = int(self.color_idle[2] * pulse)
                self.hw.onboard.fill((r, g, b))

            elif self.mode == SaberConfig.STATE_SWING:
                # Spinning chase effect in swing color
                elapsed = now - self.event_start_time
                pos = int(elapsed * 12) % n  # Spin ~3 times per second
                for i in range(n):
                    if i == pos:
                        self.hw.onboard[i] = self.color_swing[:3]  # RGB only
                    else:
                        # Dim trail
                        dist = (pos - i) % n
                        fade = max(0, 1.0 - dist * 0.4)
                        r = int(self.color_swing[0] * fade * 0.3)
                        g = int(self.color_swing[1] * fade * 0.3)
                        b = int(self.color_swing[2] * fade * 0.3)
                        self.hw.onboard[i] = (r, g, b)

            elif self.mode == SaberConfig.STATE_HIT:
                # Bright white flash that fades to hit color
                elapsed = now - self.event_start_time
                if elapsed < 0.1:
                    # Initial white flash
                    self.hw.onboard.fill((255, 255, 255))
                else:
                    # Fade from hit color to idle
                    fade = min((elapsed - 0.1) * 2, 1.0)
                    r = int(self.color_hit[0] * (1 - fade) + self.color_idle[0] * fade)
                    g = int(self.color_hit[1] * (1 - fade) + self.color_idle[1] * fade)
                    b = int(self.color_hit[2] * (1 - fade) + self.color_idle[2] * fade)
                    self.hw.onboard.fill((r, g, b))

            elif self.mode == SaberConfig.STATE_TRANSITION:
                # Quick spinner during power on/off
                pos = int(now * 8) % n
                for i in range(n):
                    if i == pos:
                        self.hw.onboard[i] = self.color_swing[:3]
                    else:
                        self.hw.onboard[i] = (0, 0, 0)

            self.hw.onboard.show()
        except Exception as e:
            print("Onboard pixel error:", e)

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
        print("Delta thresholds: swing>{}, hit>{} (rest~0)".format(
            UserConfig.SWING_THRESHOLD, UserConfig.HIT_THRESHOLD))
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
                self._update_onboard_pixels()
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
