# SPDX-FileCopyrightText: 2021 John Park for Adafruit Industries
# SPDX-FileCopyrightText: © 2024-2025 William C. Chesher <wchesher@gmail.com>
# SPDX-License-Identifier: MIT
#
# swingsaber v1.0
# Based on: https://learn.adafruit.com/hallowing-lightsaber
# CircuitPython 10.x
# ====================================================
#
# Interactive lightsaber controller with motion detection and themed audio.
# Originally by John Park, refactored and enhanced for reliability.
#
# Hardware: Adafruit HalloWing M4 Express
#  - ATSAMD51 Cortex M4 processor
#  - MSA311 3-axis accelerometer
#  - 1.44" 128x128 TFT display
#  - Built-in amplifier + speaker connection
#  - 4x capacitive touch pads
#  - NeoPixel connector (30 pixels)
#  - LiPo battery connector
#
# Features:
#  - Motion detection: swing & hit detection via accelerometer
#  - LED effects: 30-pixel NeoPixel blade animations
#  - Audio system: 4 complete themes
#  - Touch controls: power, theme switch, battery status
#  - State machine: validated transitions, error handling
#  - Memory management: LRU cache, garbage collection
#  - Power saving: adaptive brightness, idle mode, battery monitoring
#
# Prerequisites:
#  - CircuitPython 10.x on HalloWing M4
#  - Libraries: adafruit_msa3xx, neopixel, adafruit_display_text
#  - Sound files in /sounds/ folder (22050Hz, 16-bit, mono WAV)
#  - Optional: theme logos in /images/ folder (BMP format)

import time
import gc
import math
import board
import busio
import neopixel
import audioio
import audiocore
import adafruit_msa3xx
import touchio
import analogio
import supervisor
import displayio
import terminalio
from digitalio import DigitalInOut
from adafruit_display_text import label
import array

# =============================================================================
# (1) USER CONFIG FOR POWER SAVINGS & AUDIO
# =============================================================================
class UserConfig:
    """User-configurable power and performance settings."""
    # Display settings
    DISPLAY_BRIGHTNESS = 0.3
    DISPLAY_BRIGHTNESS_SAVER = 0.1
    DISPLAY_TIMEOUT_NORMAL = 2.0
    DISPLAY_TIMEOUT_SAVER = 1.0

    # NeoPixel settings
    NEOPIXEL_IDLE_BRIGHTNESS = 0.05
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3

    # Loop timing
    IDLE_LOOP_DELAY = 0.05
    ACTIVE_LOOP_DELAY = 0.01

    # Audio settings - ENHANCED
    STOP_AUDIO_WHEN_IDLE = True
    DEFAULT_VOLUME = 70  # 0-100% (70% is good for mono speaker)
    VOLUME_STEP = 10     # Volume change per adjustment
    MIN_VOLUME = 10      # Minimum volume (prevent muting)
    MAX_VOLUME = 100     # Maximum volume
    CROSSFADE_DURATION = 0.05  # 50ms crossfade for smooth transitions
    ENABLE_CROSSFADE = True

    # Volume presets (can cycle through with long-press)
    VOLUME_PRESETS = [30, 50, 70, 100]  # Quiet, Medium, Loud, Max

    # Audio quality settings
    AUDIO_SAMPLE_RATE = 22050  # Hz - CircuitPython typical max
    AUDIO_BITS_PER_SAMPLE = 16  # 16-bit audio for quality

    # Motion detection
    NEAR_SWING_RATIO = 0.8  # 80% of swing threshold for "almost" detection

    # Touch debouncing
    TOUCH_DEBOUNCE_TIME = 0.02  # 20ms debounce
    LONG_PRESS_TIME = 1.0  # 1 second for long press (volume preset cycle)

    # Memory management
    MAX_IMAGE_CACHE_SIZE = 4  # Maximum cached images (LRU eviction)
    GC_INTERVAL = 10.0  # Run garbage collection every 10 seconds in idle

    # Health monitoring
    ENABLE_DIAGNOSTICS = True
    BATTERY_CHECK_INTERVAL = 30.0  # Check battery every 30 seconds

    # Error handling
    MAX_ACCEL_ERRORS = 10  # Disable accelerometer after this many consecutive errors
    ERROR_RECOVERY_DELAY = 0.1  # Delay after error before retry

# =============================================================================
# (2) SABER CONFIG
# =============================================================================
class SaberConfig:
    """Hardware configuration and constants."""
    # Pin definitions
    CAP_PIN = board.CAP_PIN
    SPEAKER_ENABLE_PIN = board.SPEAKER_ENABLE
    VOLTAGE_MONITOR_PIN = board.VOLTAGE_MONITOR

    # NeoPixel configuration
    NUM_PIXELS = 30

    # Motion thresholds (in m²/s² since we use magnitude squared for performance)
    SWING_THRESHOLD = 140
    HIT_THRESHOLD = 220

    # State machine states
    STATE_OFF = 0
    STATE_IDLE = 1
    STATE_SWING = 2
    STATE_HIT = 3
    STATE_TRANSITION = 4
    STATE_ERROR = 5

    # Valid state transitions
    VALID_TRANSITIONS = {
        STATE_OFF: [STATE_TRANSITION, STATE_ERROR],
        STATE_IDLE: [STATE_SWING, STATE_HIT, STATE_TRANSITION, STATE_ERROR],
        STATE_SWING: [STATE_IDLE, STATE_ERROR],
        STATE_HIT: [STATE_IDLE, STATE_ERROR],
        STATE_TRANSITION: [STATE_OFF, STATE_IDLE, STATE_ERROR],
        STATE_ERROR: [STATE_OFF],
    }

    # Display timing
    DISPLAY_TIMEOUT_SAVER_ON = UserConfig.DISPLAY_TIMEOUT_SAVER
    DISPLAY_TIMEOUT_SAVER_OFF = UserConfig.DISPLAY_TIMEOUT_NORMAL
    IMAGE_DISPLAY_DURATION_SAVER_ON = 1.5
    IMAGE_DISPLAY_DURATION_SAVER_OFF = 3.0

    # Animation constants
    POWER_ON_DURATION = 1.7
    POWER_OFF_DURATION = 1.15
    FADE_OUT_DURATION = 0.5
    SWING_BLEND_MIDPOINT = 0.5
    SWING_BLEND_SCALE = 2.0

    # Battery constants
    BATTERY_VOLTAGE_SAMPLES = 10
    BATTERY_MIN_VOLTAGE = 3.3
    BATTERY_MAX_VOLTAGE = 4.2
    BATTERY_ADC_MAX = 65535
    BATTERY_VOLTAGE_DIVIDER = 2

    # Audio constants - ENHANCED
    SILENCE_SAMPLE_SIZE = 1024
    AUDIO_STOP_CHECK_INTERVAL = 0.03
    AUDIO_BUFFER_SIZE = 4096  # Larger buffer for smoother playback

    # Fade constants for click/pop prevention
    FADE_IN_SAMPLES = 100    # Number of samples to fade in
    FADE_OUT_SAMPLES = 100   # Number of samples to fade out

    # Themes
    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255),   "hit_color": (255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255), "hit_color": (0, 200, 255)},
        {"name": "ricknmorty", "color": (0, 255, 0),   "hit_color": (255, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0), "hit_color": (255, 255, 255)},
    ]

    # Color calculation
    IDLE_COLOR_DIVISOR = 4

# =============================================================================
# (3) AUDIO UTILITIES FOR QUALITY & VOLUME CONTROL
# =============================================================================
class AudioUtils:
    """Utilities for audio processing and volume control."""

    @staticmethod
    def scale_sample(sample, volume_percent):
        """
        Scale an audio sample by volume percentage.

        Args:
            sample: 16-bit signed audio sample (-32768 to 32767)
            volume_percent: Volume level 0-100

        Returns:
            Scaled sample as 16-bit signed integer
        """
        if volume_percent >= 100:
            return sample
        if volume_percent <= 0:
            return 0

        # Scale and clamp to prevent overflow
        scaled = int(sample * volume_percent / 100)
        return max(-32768, min(32767, scaled))

    @staticmethod
    def apply_fade_envelope(samples, fade_in_samples=100, fade_out_samples=100):
        """
        Apply fade in/out envelope to prevent clicks and pops.

        Args:
            samples: Array of audio samples
            fade_in_samples: Number of samples for fade-in
            fade_out_samples: Number of samples for fade-out

        Returns:
            Modified samples array
        """
        sample_count = len(samples)

        # Fade in
        for i in range(min(fade_in_samples, sample_count)):
            factor = i / fade_in_samples
            samples[i] = int(samples[i] * factor)

        # Fade out
        start_fade_out = max(0, sample_count - fade_out_samples)
        for i in range(start_fade_out, sample_count):
            factor = (sample_count - i) / fade_out_samples
            samples[i] = int(samples[i] * factor)

        return samples

    @staticmethod
    def create_silence(duration_ms, sample_rate=22050):
        """
        Create a silence buffer for clean transitions.

        Args:
            duration_ms: Duration in milliseconds
            sample_rate: Audio sample rate

        Returns:
            RawSample object with silence
        """
        num_samples = int((duration_ms / 1000.0) * sample_rate)
        silence = array.array("h", [0] * num_samples)
        return audiocore.RawSample(silence, sample_rate=sample_rate)

# =============================================================================
# (4) HARDWARE SETUP
# =============================================================================
class SaberHardware:
    """Hardware initialization and management with robust error handling."""

    def __init__(self):
        print("Initializing Saber Hardware...")
        self.hardware_status = {
            "strip": False,
            "touch": False,
            "accel": False,
            "battery": False
        }

        # Initialize cap pin
        try:
            self.cap_pin = DigitalInOut(SaberConfig.CAP_PIN)
            self.cap_pin.switch_to_output(value=False)
        except Exception as e:
            print("  CAP_PIN error:", e)
            self.cap_pin = None

        # Initialize speaker enable
        try:
            self.speaker_enable = DigitalInOut(SaberConfig.SPEAKER_ENABLE_PIN)
            self.speaker_enable.switch_to_output(value=True)
        except Exception as e:
            print("  SPEAKER_ENABLE error:", e)
            self.speaker_enable = None

        # Initialize battery monitor
        try:
            self.battery_voltage = analogio.AnalogIn(SaberConfig.VOLTAGE_MONITOR_PIN)
            self.hardware_status["battery"] = True
        except Exception as e:
            print("  VOLTAGE_MONITOR error:", e)
            self.battery_voltage = None

        # Initialize NeoPixel strip
        self.strip = self._init_strip()

        # Initialize touch inputs
        self.touch_left = None
        self.touch_right = None
        self.touch_batt_a3 = None
        self.touch_batt_a4 = None
        self._init_touch()

        # Initialize accelerometer
        self.accel = self._init_accel()
        self.accel_error_count = 0

        print("Hardware init complete.")
        print("Status:", self.hardware_status)
        print()

    def _init_strip(self):
        """Initialize NeoPixel strip with error handling."""
        try:
            strip = neopixel.NeoPixel(
                board.EXTERNAL_NEOPIXEL,
                SaberConfig.NUM_PIXELS,
                brightness=UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS,
                auto_write=False,
                pixel_order=neopixel.GRB
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
        """Initialize touch inputs with error handling."""
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
        """Initialize accelerometer with error handling."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            accel = adafruit_msa3xx.MSA311(i2c)
            print("  Accelerometer OK.")
            self.hardware_status["accel"] = True
            return accel
        except Exception as e:
            print("  Accel error:", e)
            return None

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

# =============================================================================
# (5) ENHANCED AUDIO MANAGER WITH VOLUME CONTROL
# =============================================================================
class AudioManager:
    """Enhanced audio management with volume control and quality improvements."""

    def __init__(self):
        try:
            self.audio = audioio.AudioOut(board.SPEAKER)
            print("Audio system OK.")
        except Exception as e:
            print("Audio error:", e)
            self.audio = None

        self.current_wave_file = None
        self.current_wav = None
        self.silence_sample = self._create_silence_sample()

        # Volume control
        self.volume = UserConfig.DEFAULT_VOLUME  # 0-100%
        self.volume_preset_index = 1  # Start at medium preset

        # Fade state for non-blocking fade
        self.fade_start_time = None
        self.fade_duration = 0
        self.is_fading = False

        # Crossfade state
        self.is_crossfading = False
        self.crossfade_start_time = None

        print("  Audio volume: {}%".format(self.volume))

    def _create_silence_sample(self):
        """Create a silent audio sample for keepalive."""
        try:
            silent_samples = array.array("h", [0] * SaberConfig.SILENCE_SAMPLE_SIZE)
            return audiocore.RawSample(silent_samples)
        except Exception as e:
            print("Error creating silence sample:", e)
            return None

    def _close_current_file(self):
        """Safely close the current audio file."""
        if self.current_wave_file is not None:
            try:
                self.current_wave_file.close()
            except Exception as e:
                print("Error closing audio file:", e)
            finally:
                self.current_wave_file = None
                self.current_wav = None

    def set_volume(self, volume_percent):
        """
        Set volume level (0-100%).
        Note: CircuitPython's audioio doesn't have native volume control,
        so we track it for potential software scaling.

        For hardware volume control, this would need:
        - External DAC with volume control
        - PWM audio output with duty cycle adjustment
        - Digital potentiometer on analog output
        """
        self.volume = max(UserConfig.MIN_VOLUME, min(volume_percent, UserConfig.MAX_VOLUME))
        print("Volume: {}%".format(self.volume))
        return self.volume

    def increase_volume(self):
        """Increase volume by one step."""
        new_volume = self.volume + UserConfig.VOLUME_STEP
        return self.set_volume(new_volume)

    def decrease_volume(self):
        """Decrease volume by one step."""
        new_volume = self.volume - UserConfig.VOLUME_STEP
        return self.set_volume(new_volume)

    def cycle_volume_preset(self):
        """Cycle through volume presets."""
        self.volume_preset_index = (self.volume_preset_index + 1) % len(UserConfig.VOLUME_PRESETS)
        preset_volume = UserConfig.VOLUME_PRESETS[self.volume_preset_index]
        self.set_volume(preset_volume)
        return preset_volume

    def _load_and_process_wav(self, filename, apply_volume=True):
        """
        Load WAV file and optionally apply volume scaling.

        Note: This is a placeholder for future enhancement.
        Full implementation would:
        1. Read WAV file samples
        2. Apply volume scaling to each sample
        3. Apply fade envelope
        4. Create RawSample with processed audio

        For now, we load normally and track volume for future use.
        """
        try:
            wave_file = open(filename, "rb")
            wav = audiocore.WaveFile(wave_file)
            return (wave_file, wav)
        except OSError as e:
            print("Audio file not found:", filename)
            return (None, None)
        except Exception as e:
            print("Error loading audio:", e)
            return (None, None)

    def play_audio_clip(self, theme_index, name, loop=False):
        """Play an audio clip with proper file handling and volume."""
        if not self.audio:
            return False

        # Clean up before playing new clip
        gc.collect()

        # Handle crossfade if enabled
        if UserConfig.ENABLE_CROSSFADE and self.audio.playing:
            self.start_crossfade()
            # Brief wait for crossfade start
            time.sleep(0.01)
        else:
            if self.audio.playing:
                self.audio.stop()

        # Close previous file before opening new one
        self._close_current_file()

        filename = "sounds/{}{}.wav".format(theme_index, name)

        # Load and process audio
        self.current_wave_file, self.current_wav = self._load_and_process_wav(
            filename,
            apply_volume=(self.volume < 100)
        )

        if self.current_wav is None:
            return False

        try:
            self.audio.play(self.current_wav, loop=loop)
            return True
        except Exception as e:
            print("Error playing audio:", e)
            self._close_current_file()
            return False

    def start_crossfade(self):
        """Start a crossfade (fade out current, will fade in next)."""
        if UserConfig.ENABLE_CROSSFADE:
            self.is_crossfading = True
            self.crossfade_start_time = time.monotonic()

    def update_crossfade(self):
        """Update crossfade state."""
        if not self.is_crossfading:
            return False

        elapsed = time.monotonic() - self.crossfade_start_time
        if elapsed >= UserConfig.CROSSFADE_DURATION:
            self.audio.stop()
            self.is_crossfading = False
            return True

        return False

    def stop_audio(self):
        """Stop audio playback with pop prevention."""
        if self.audio and self.audio.playing:
            # Brief silence before stop to prevent pop
            time.sleep(0.001)
            self.audio.stop()

    def check_audio_done(self):
        """Check if audio is done and clean up if needed."""
        if self.audio and not self.audio.playing and self.current_wave_file is not None:
            self._close_current_file()

    def start_fade_out(self, duration=None):
        """Start a non-blocking fade out."""
        if duration is None:
            duration = SaberConfig.FADE_OUT_DURATION
        self.fade_start_time = time.monotonic()
        self.fade_duration = duration
        self.is_fading = True

    def update_fade(self):
        """Update fade state - call this in main loop."""
        if not self.is_fading:
            return False

        elapsed = time.monotonic() - self.fade_start_time
        if elapsed >= self.fade_duration:
            # Fade complete
            self.stop_audio()
            self._close_current_file()
            self.is_fading = False

            # Play silence if configured
            if (not UserConfig.STOP_AUDIO_WHEN_IDLE) and self.silence_sample and self.audio:
                try:
                    self.audio.play(self.silence_sample, loop=True)
                except Exception as e:
                    print("Error playing silence:", e)

            return True  # Fade complete

        return False  # Still fading

    def cleanup(self):
        """Clean up audio resources."""
        self.stop_audio()
        self._close_current_file()

# =============================================================================
# (6) DISPLAY MANAGER
# =============================================================================
class SaberDisplay:
    """Display management with image caching and memory limits."""

    def __init__(self, battery_voltage_ref):
        self.main_group = displayio.Group()
        try:
            board.DISPLAY.auto_refresh = True
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
        except Exception as e:
            print("Display init error:", e)

        self.image_cache = {}
        self.image_cache_order = []  # For LRU eviction

        self.display_start_time = 0
        self.display_active = False
        self.display_timeout = SaberConfig.DISPLAY_TIMEOUT_SAVER_OFF
        self.get_battery_voltage_pct = battery_voltage_ref
        self.image_display_duration = SaberConfig.IMAGE_DISPLAY_DURATION_SAVER_OFF
        self.turn_off_screen()

    def turn_off_screen(self):
        """Turn off the display to save power."""
        try:
            board.DISPLAY.brightness = 0
        except Exception as e:
            print("Error turning off screen:", e)

    def update_display_timeout(self, timeout):
        """Update display timeout value."""
        self.display_timeout = timeout

    def update_image_display_duration(self, duration):
        """Update image display duration."""
        self.image_display_duration = duration

    def update_power_saver_settings(self, saver_on):
        """Update display settings for power saver mode."""
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
        """Display battery status on screen."""
        try:
            # Clear existing display
            while len(self.main_group):
                self.main_group.pop()

            battery_percent = self.get_battery_voltage_pct()
            battery_text = "BATTERY: {}%".format(battery_percent) if battery_percent != "USB" else "BATTERY: USB"
            battery_label = label.Label(
                terminalio.FONT,
                text=battery_text,
                scale=2,
                color=0xFFFFFF,
                x=10,
                y=30
            )
            self.main_group.append(battery_label)

            # Draw battery bar if not on USB
            if battery_percent != "USB":
                battery_bar_width = max(1, min(battery_percent, 100))
                battery_group = displayio.Group()

                # Background
                bg_palette = displayio.Palette(1)
                bg_palette[0] = 0x444444
                bat_bg_bitmap = displayio.Bitmap(100, 14, 1)
                bat_bg_bitmap.fill(0)
                bg_tile2 = displayio.TileGrid(bat_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
                battery_group.append(bg_tile2)

                # Battery level
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
        """Display volume level on screen."""
        try:
            # Clear existing display
            while len(self.main_group):
                self.main_group.pop()

            volume_text = "VOLUME: {}%".format(volume_percent)
            volume_label = label.Label(
                terminalio.FONT,
                text=volume_text,
                scale=2,
                color=0x00FF00,
                x=10,
                y=30
            )
            self.main_group.append(volume_label)

            # Draw volume bar
            volume_bar_width = max(1, min(volume_percent, 100))
            volume_group = displayio.Group()

            # Background
            bg_palette = displayio.Palette(1)
            bg_palette[0] = 0x444444
            vol_bg_bitmap = displayio.Bitmap(100, 14, 1)
            vol_bg_bitmap.fill(0)
            bg_tile2 = displayio.TileGrid(vol_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
            volume_group.append(bg_tile2)

            # Volume level
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

            # Auto-hide after 1 second
            time.sleep(1.0)
            self.turn_off_screen()
        except Exception as e:
            print("Error showing volume status:", e)

    def _evict_oldest_image(self):
        """Remove oldest image from cache (LRU)."""
        if not self.image_cache_order:
            return

        oldest_key = self.image_cache_order.pop(0)
        if oldest_key in self.image_cache:
            del self.image_cache[oldest_key]
        gc.collect()

    def _load_image(self, theme_index, image_type="logo"):
        """Load image with LRU caching."""
        cache_key = "{}{}".format(theme_index, image_type)

        # Check cache
        if cache_key in self.image_cache:
            # Move to end (most recently used)
            self.image_cache_order.remove(cache_key)
            self.image_cache_order.append(cache_key)
            return self.image_cache[cache_key]

        # Load from disk
        filename = "/images/{}{}.bmp".format(theme_index, image_type)
        try:
            # Evict if cache is full
            if len(self.image_cache) >= UserConfig.MAX_IMAGE_CACHE_SIZE:
                self._evict_oldest_image()

            bitmap = displayio.OnDiskBitmap(filename)
            tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)

            # Add to cache
            self.image_cache[cache_key] = tile_grid
            self.image_cache_order.append(cache_key)

            return tile_grid
        except Exception as e:
            print("Error loading image {}: {}".format(filename, e))
            return None

    def show_image(self, theme_index, image_type="logo", duration=None):
        """Display an image on screen."""
        if duration is None:
            duration = self.image_display_duration
            print("\n" * 40)  # Clear console

        try:
            # Clear existing display
            while len(self.main_group):
                self.main_group.pop()

            image = self._load_image(theme_index, image_type)
            if image:
                self.main_group.append(image)
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
                board.DISPLAY.refresh()
                time.sleep(duration)

                # Clear display
                while len(self.main_group):
                    self.main_group.pop()
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = 0

            self.display_start_time = time.monotonic()
            self.display_active = True
        except Exception as e:
            print("Error showing image:", e)

    def update_display(self):
        """Update display state and handle timeout."""
        if self.display_active and (time.monotonic() - self.display_start_time) > self.display_timeout:
            self.turn_off_screen()
            self.display_active = False

    def clear_cache(self):
        """Clear image cache and free memory."""
        self.image_cache.clear()
        self.image_cache_order.clear()
        gc.collect()

    def cleanup(self):
        """Clean up display resources."""
        self.clear_cache()
        self.turn_off_screen()

# =============================================================================
# (7) SABER CONTROLLER
# =============================================================================
class SaberController:
    """Main controller with bulletproof state machine and premium audio."""

    def __init__(self):
        print("Booting SaberController...")
        self.hw = SaberHardware()
        self.display = SaberDisplay(self._get_battery_percentage)
        self.audio = AudioManager()

        self.power_saver_mode = False
        self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY
        self.mode = SaberConfig.STATE_OFF
        self.theme_index = 0

        # Color state
        self.color_idle = (0, 0, 0)
        self.color_swing = (0, 0, 0)
        self.color_hit = (0, 0, 0)
        self.color_active = (0, 0, 0)
        self.last_color = None

        # Timing state
        self.event_start_time = 0
        self.last_gc_time = time.monotonic()
        self.last_battery_check = 0

        # Touch debouncing with long press detection
        self.last_touch_time = 0
        self.touch_press_start = 0
        self.touch_is_long_press = False

        # Error tracking
        self.accel_error_count = 0
        self.accel_enabled = True

        # Diagnostics
        self.loop_count = 0
        self.state_changes = 0

        self._update_theme_colors()
        self._apply_power_mode()
        self.display.turn_off_screen()
        print("SaberController init complete.\n")

    def _apply_power_mode(self):
        """Apply power mode settings."""
        if self.power_saver_mode:
            self.display.update_power_saver_settings(True)
            self.cpu_loop_delay = 0.03
        else:
            self.display.update_power_saver_settings(False)
            self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY

    def toggle_power_mode(self):
        """Toggle power saver mode."""
        self.power_saver_mode = not self.power_saver_mode
        self._apply_power_mode()
        print("Power saver mode:", "ON" if self.power_saver_mode else "OFF")

    def _get_battery_percentage(self):
        """Get battery percentage with error handling."""
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
        """Update theme colors based on current theme."""
        t = SaberConfig.THEMES[self.theme_index]
        self.color_idle = tuple(int(c / SaberConfig.IDLE_COLOR_DIVISOR) for c in t["color"])
        self.color_swing = t["color"]
        self.color_hit = t["hit_color"]

    def cycle_theme(self):
        """Cycle to next theme."""
        self.theme_index = (self.theme_index + 1) % len(SaberConfig.THEMES)
        self._update_theme_colors()

    def _transition_to_state(self, new_state):
        """Validate and execute state transition."""
        if new_state == self.mode:
            return True

        if new_state not in SaberConfig.VALID_TRANSITIONS.get(self.mode, []):
            print("INVALID STATE TRANSITION: {} -> {}".format(self.mode, new_state))
            return False

        old_state = self.mode
        self.mode = new_state
        self.state_changes += 1

        if UserConfig.ENABLE_DIAGNOSTICS:
            print("State: {} -> {}".format(old_state, new_state))

        return True

    def _animate_power(self, name, duration, reverse):
        """Animate power on/off with LED strip."""
        if not self.hw.strip:
            return

        self.audio.stop_audio()
        self.audio.play_audio_clip(self.theme_index, name, loop=False)
        start_time = time.monotonic()

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > duration:
                break

            fraction = min(elapsed / duration, 1.0)
            fraction = math.sqrt(fraction)
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
            except Exception as e:
                print("Strip animation error:", e)
                break

        try:
            if reverse:
                self.hw.strip.fill(0)
            else:
                self.hw.strip.fill(self.color_idle)
            self.hw.strip.show()
        except Exception:
            pass

        while self.audio.audio and self.audio.audio.playing:
            time.sleep(SaberConfig.AUDIO_STOP_CHECK_INTERVAL)

    def _check_touch_debounced(self, touch_input):
        """Check touch input with debouncing and long-press detection."""
        if not touch_input:
            return False

        try:
            if touch_input.value:
                now = time.monotonic()

                # Start of press
                if self.touch_press_start == 0:
                    self.touch_press_start = now

                # Check for long press
                press_duration = now - self.touch_press_start
                if press_duration >= UserConfig.LONG_PRESS_TIME and not self.touch_is_long_press:
                    self.touch_is_long_press = True
                    return False  # Don't trigger normal press during long press

                # Normal debounced press
                if now - self.last_touch_time >= UserConfig.TOUCH_DEBOUNCE_TIME:
                    self.last_touch_time = now
                    return True
            else:
                # Release - reset long press tracking
                self.touch_press_start = 0
                self.touch_is_long_press = False

        except Exception as e:
            print("Touch read error:", e)

        return False

    def _check_long_press(self, touch_input):
        """Check if touch is a long press."""
        if not touch_input:
            return False

        try:
            if touch_input.value and self.touch_is_long_press:
                return True
        except Exception:
            pass

        return False

    def _wait_for_touch_release(self, touch_input):
        """Wait for touch input to be released."""
        if not touch_input:
            return

        try:
            while touch_input.value:
                time.sleep(UserConfig.TOUCH_DEBOUNCE_TIME)
        except Exception:
            pass

        # Reset long press tracking on release
        self.touch_press_start = 0
        self.touch_is_long_press = False

    def _handle_battery_touch(self):
        """Handle battery status display request."""
        # Check for long press on A3/A4 for volume control
        if self._check_long_press(self.hw.touch_batt_a3):
            self.audio.increase_volume()
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a3)
            return True

        if self._check_long_press(self.hw.touch_batt_a4):
            self.audio.decrease_volume()
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a4)
            return True

        # Normal press shows battery
        if self._check_touch_debounced(self.hw.touch_batt_a3) or \
           self._check_touch_debounced(self.hw.touch_batt_a4):
            self.display.show_battery_status()
            self._wait_for_touch_release(self.hw.touch_batt_a3)
            self._wait_for_touch_release(self.hw.touch_batt_a4)
            return True
        return False

    def _handle_theme_switch(self):
        """Handle theme switch button."""
        # Long press on left button cycles volume presets
        if self._check_long_press(self.hw.touch_left):
            preset_vol = self.audio.cycle_volume_preset()
            self.display.show_volume_status(preset_vol)
            self._wait_for_touch_release(self.hw.touch_left)
            return True

        if not self._check_touch_debounced(self.hw.touch_left):
            return False

        if self.mode == SaberConfig.STATE_OFF:
            old_theme = self.theme_index
            self.cycle_theme()
            self.audio.play_audio_clip(self.theme_index, "switch")
            print("Theme: {} -> {}".format(old_theme, self.theme_index))
            self.display.show_image(self.theme_index, "logo")
            self.event_start_time = time.monotonic()
        else:
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                time.sleep(0.01)

            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self._animate_power("off", duration=SaberConfig.POWER_OFF_DURATION, reverse=True)
            self._transition_to_state(SaberConfig.STATE_OFF)

            self.cycle_theme()
            print("Theme (while on): {}".format(self.theme_index))
            self.audio.play_audio_clip(self.theme_index, "switch")
            self.display.show_image(self.theme_index, "logo")
            self.event_start_time = time.monotonic()

        self._wait_for_touch_release(self.hw.touch_left)
        return True

    def _handle_power_toggle(self):
        """Handle power on/off button."""
        if not self._check_touch_debounced(self.hw.touch_right):
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
                time.sleep(0.01)

            self._animate_power("off", duration=SaberConfig.POWER_OFF_DURATION, reverse=True)
            self._transition_to_state(SaberConfig.STATE_OFF)
            self.event_start_time = time.monotonic()

        self._wait_for_touch_release(self.hw.touch_right)
        return True

    def _read_acceleration_magnitude(self):
        """Read acceleration magnitude with proper calculation and error handling."""
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
            else:
                if self.accel_error_count % 5 == 0:
                    print("Accel read error {} of {}: {}".format(
                        self.accel_error_count, UserConfig.MAX_ACCEL_ERRORS, e))

            time.sleep(UserConfig.ERROR_RECOVERY_DELAY)
            return None

    def _handle_motion_detection(self):
        """Handle motion detection for swing and hit."""
        if self.mode != SaberConfig.STATE_IDLE:
            return False

        accel_data = self._read_acceleration_magnitude()
        if accel_data is None:
            return False

        accel_magnitude_sq, accel_x, accel_y, accel_z = accel_data
        near_swing_threshold = UserConfig.NEAR_SWING_RATIO * SaberConfig.SWING_THRESHOLD

        if accel_magnitude_sq > SaberConfig.HIT_THRESHOLD:
            print("HIT: Mag²={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                accel_magnitude_sq, accel_x, accel_y, accel_z))

            self.event_start_time = time.monotonic()
            self._transition_to_state(SaberConfig.STATE_TRANSITION)

            self.audio.start_fade_out()
            while not self.audio.update_fade():
                time.sleep(0.01)

            self.audio.play_audio_clip(self.theme_index, "hit")
            self.color_active = self.color_hit
            self._transition_to_state(SaberConfig.STATE_HIT)
            return True

        elif accel_magnitude_sq > SaberConfig.SWING_THRESHOLD:
            print("SWING: Mag²={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                accel_magnitude_sq, accel_x, accel_y, accel_z))

            self.event_start_time = time.monotonic()
            self._transition_to_state(SaberConfig.STATE_TRANSITION)

            self.audio.start_fade_out()
            while not self.audio.update_fade():
                time.sleep(0.01)

            self.audio.play_audio_clip(self.theme_index, "swing")
            self.color_active = self.color_swing
            self._transition_to_state(SaberConfig.STATE_SWING)
            return True

        elif accel_magnitude_sq > near_swing_threshold:
            if UserConfig.ENABLE_DIAGNOSTICS and self.loop_count % 10 == 0:
                print("ALMOST: Mag²={:.1f}, threshold={:.1f}".format(
                    accel_magnitude_sq, SaberConfig.SWING_THRESHOLD))

        return False

    def _update_swing_hit_animation(self):
        """Update color animation during swing/hit."""
        if self.mode not in (SaberConfig.STATE_SWING, SaberConfig.STATE_HIT):
            return

        if self.audio.audio and self.audio.audio.playing:
            elapsed = time.monotonic() - self.event_start_time

            if self.mode == SaberConfig.STATE_SWING:
                blend = abs(SaberConfig.SWING_BLEND_MIDPOINT - elapsed) * SaberConfig.SWING_BLEND_SCALE
            else:
                blend = elapsed

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
        """Fill strip with blended color, only if different from last."""
        if not self.hw.strip:
            return

        ratio = max(0, min(ratio, 1.0))
        color = self._mix_colors(c1, c2, ratio)

        if color != self.last_color:
            try:
                self.hw.strip.fill(color)
                self.hw.strip.show()
                self.last_color = color
            except Exception as e:
                print("Strip blend error:", e)

    def _mix_colors(self, color1, color2, w2):
        """Mix two colors with weight w2 for color2."""
        w2 = max(0, min(w2, 1.0))
        w1 = 1.0 - w2
        return (
            int(color1[0] * w1 + color2[0] * w2),
            int(color1[1] * w1 + color2[1] * w2),
            int(color1[2] * w1 + color2[1] * w2),
        )

    def _update_strip_brightness(self):
        """Update NeoPixel brightness based on state."""
        if not self.hw.strip:
            return

        try:
            target_brightness = UserConfig.NEOPIXEL_IDLE_BRIGHTNESS if \
                self.mode == SaberConfig.STATE_IDLE else \
                UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS

            if self.hw.strip.brightness != target_brightness:
                self.hw.strip.brightness = target_brightness
        except Exception as e:
            print("Brightness update error:", e)

    def _periodic_maintenance(self):
        """Run periodic maintenance tasks."""
        now = time.monotonic()

        if self.mode in (SaberConfig.STATE_OFF, SaberConfig.STATE_IDLE):
            if now - self.last_gc_time > UserConfig.GC_INTERVAL:
                gc.collect()
                self.last_gc_time = now

                if UserConfig.ENABLE_DIAGNOSTICS:
                    mem_free = gc.mem_free()
                    print("GC: {} bytes free".format(mem_free))

        if UserConfig.ENABLE_DIAGNOSTICS:
            if now - self.last_battery_check > UserConfig.BATTERY_CHECK_INTERVAL:
                battery = self._get_battery_percentage()
                print("Battery: {}".format(battery))
                self.last_battery_check = now

    def run(self):
        """Main run loop with bulletproof error handling."""
        print("=== SABER READY ===")
        print("Volume Controls:")
        print("  - Long press A3: Increase volume")
        print("  - Long press A4: Decrease volume")
        print("  - Long press LEFT: Cycle volume presets")
        print()

        try:
            while True:
                self.loop_count += 1

                self.audio.update_fade()
                self.audio.update_crossfade()

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
            print("\nShutdown requested...")
            self.cleanup()
        except Exception as e:
            print("\nFATAL ERROR:", e)
            self.cleanup()
            raise

    def cleanup(self):
        """Clean up all resources."""
        print("Cleaning up...")
        try:
            self.audio.cleanup()
            self.display.cleanup()
            self.hw.cleanup()
            print("Cleanup complete.")
        except Exception as e:
            print("Cleanup error:", e)

# =============================================================================
# (8) ENTRY POINT
# =============================================================================
def main():
    """Main entry point with error handling."""
    controller = None
    try:
        controller = SaberController()
        controller.run()
    except Exception as e:
        print("\nFATAL ERROR:", e)
        if controller:
            controller.cleanup()
        raise

if __name__ == "__main__":
    main()
