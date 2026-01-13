# =============================================================================
# SPDX-FileCopyrightText: 2021 John Park for Adafruit Industries
# SPDX-FileCopyrightText: © 2024-2025 William C. Chesher <wchesher@gmail.com>
# SPDX-License-Identifier: MIT
#
# SwingSaber v1.1 - Stability & Optimization Update
# Based on: https://learn.adafruit.com/hallowing-lightsaber
# CircuitPython 10.x
# =============================================================================
#
#                         *** EDUCATIONAL OVERVIEW ***
#
# WHAT IS THIS PROJECT?
# ---------------------
# This is firmware (the code that runs directly on hardware) for an interactive
# lightsaber toy. When you move the device, it detects the motion and plays
# appropriate sounds while lighting up LED strips to simulate a lightsaber blade.
#
# WHAT HARDWARE DOES IT USE?
# --------------------------
# - Adafruit HalloWing M4 Express: A small computer (microcontroller) shaped like
#   an eyeball, containing:
#     * ATSAMD51 Cortex M4 processor: The "brain" that runs this code
#     * MSA311 accelerometer: A motion sensor that detects tilting and shaking
#     * 1.44" TFT display: A small color screen (128x128 pixels)
#     * Speaker + amplifier: For playing sound effects
#     * 4 capacitive touch pads: Buttons you touch (not press) to control it
#     * NeoPixel connector: Port for connecting addressable RGB LED strips
#     * LiPo battery connector: For rechargeable battery power
#
# HOW DOES IT WORK? (HIGH LEVEL)
# ------------------------------
# 1. On startup, the code initializes all hardware components
# 2. It enters a continuous loop (called "main loop") that runs forever
# 3. Each loop iteration:
#    - Checks if any touch buttons are pressed
#    - Reads the accelerometer to detect motion
#    - Updates LED colors and plays sounds based on what's happening
#    - Manages battery level and memory usage
#
# KEY PROGRAMMING CONCEPTS USED:
# ------------------------------
# - Classes: Blueprints for creating objects that group related data and functions
# - State Machine: A design pattern where the system can only be in one "state"
#   at a time (OFF, IDLE, SWING, HIT, etc.) with defined rules for transitions
# - Exception Handling: try/except blocks that catch errors gracefully
# - Callbacks: Functions passed to other functions to be called later
# - Debouncing: Technique to prevent registering multiple button presses from
#   one physical press (buttons can "bounce" and register many times)
#
# =============================================================================

# =============================================================================
# SECTION: IMPORTS
# =============================================================================
# "Imports" bring in pre-written code libraries that provide functionality.
# Think of them like including tools from a toolbox - instead of building
# everything from scratch, we use existing tools others have created.
# =============================================================================

import time      # Provides timing functions: sleep (pause), monotonic (get current time)
import gc        # "Garbage Collector" - frees up memory that's no longer being used
import math      # Mathematical functions like sqrt (square root)
import board     # CircuitPython library that knows the hardware pin names for this board
import busio     # Handles communication buses (I2C, SPI) for talking to sensors
import neopixel  # Library for controlling NeoPixel/WS2812 addressable RGB LEDs
import audioio   # Audio output library for playing sounds through speakers
import audiocore # Core audio classes for working with WAV files
import adafruit_msa3xx  # Driver for the MSA311 accelerometer (motion sensor)
import touchio   # Library for reading capacitive touch inputs
import analogio  # Library for reading analog voltages (like battery level)
import supervisor  # Access to CircuitPython supervisor (monitors USB, etc.)
import displayio  # Library for managing displays and graphics
import terminalio  # Provides a built-in font for text display
import microcontroller  # Low-level access to microcontroller features (like NVM storage)
from digitalio import DigitalInOut  # For controlling simple on/off digital pins
from adafruit_display_text import label  # For displaying text on the screen
import array     # Provides efficient arrays of numbers (used for audio samples)

# =============================================================================
# WATCHDOG TIMER - CRASH RECOVERY SYSTEM
# =============================================================================
# A "watchdog" is a hardware timer that automatically resets the device if the
# code gets stuck. Think of it like a dead man's switch - the code must
# regularly "pet" or "feed" the watchdog to prove it's still running. If it
# doesn't (because it crashed or got stuck in an infinite loop), the watchdog
# times out and reboots the device automatically.
#
# Why is this important? In embedded systems, there's no one to press a reset
# button if things go wrong. The watchdog ensures the device recovers on its own.
# =============================================================================
try:
    # Try to import watchdog support (only available in CircuitPython 7+)
    from watchdog import WatchDogMode
    WATCHDOG_AVAILABLE = True  # Mark that watchdog is available
except ImportError:
    # If the import fails, watchdog isn't supported on this CircuitPython version
    WATCHDOG_AVAILABLE = False

# =============================================================================
# SECTION 1: USER CONFIGURATION
# =============================================================================
# This class contains settings that users might want to customize without
# having to understand the rest of the code. By putting all adjustable values
# in one place, it's easy to tweak behavior.
#
# A "class" in Python is like a blueprint. "UserConfig" is a container that
# groups related constants together. The values here are "class attributes"
# meaning they belong to the class itself, not to instances of the class.
# =============================================================================

class UserConfig:
    """
    USER-ADJUSTABLE SETTINGS

    These values control how the lightsaber behaves. You can modify them
    to customize performance, power usage, and responsiveness.

    IMPORTANT: All values here are "class attributes" - they're constants
    shared by all parts of the code that reference UserConfig.
    """

    # -------------------------------------------------------------------------
    # DISPLAY SETTINGS
    # -------------------------------------------------------------------------
    # The HalloWing has a small TFT screen. These settings control its behavior.
    # Brightness is a decimal from 0.0 (off) to 1.0 (maximum brightness).
    # -------------------------------------------------------------------------

    DISPLAY_BRIGHTNESS = 0.3          # Normal screen brightness (30% = visible but not blinding)
    DISPLAY_BRIGHTNESS_SAVER = 0.1    # Dimmer brightness for power saver mode (10%)
    DISPLAY_TIMEOUT_NORMAL = 2.0      # Seconds before display turns off (saves power)
    DISPLAY_TIMEOUT_SAVER = 1.0       # Faster timeout in power saver mode

    # -------------------------------------------------------------------------
    # NEOPIXEL LED BRIGHTNESS SETTINGS
    # -------------------------------------------------------------------------
    # NeoPixels are very bright! Lower values save power and reduce eye strain.
    # Values from 0.0 (off) to 1.0 (maximum). Note: LEDs draw significant
    # current at high brightness - important for battery life.
    # -------------------------------------------------------------------------

    NEOPIXEL_IDLE_BRIGHTNESS = 0.05   # Dim glow when saber is on but still (5%)
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3  # Brighter during swings/hits (30%)

    # -------------------------------------------------------------------------
    # MAIN LOOP TIMING
    # -------------------------------------------------------------------------
    # The main code runs in an infinite loop. These values control how long
    # to "sleep" (pause) between each iteration. Faster loops = more responsive
    # but uses more CPU power. Slower loops = less responsive but saves power.
    # -------------------------------------------------------------------------

    IDLE_LOOP_DELAY = 0.05    # 50 milliseconds when idle (20 loops per second)
    ACTIVE_LOOP_DELAY = 0.01  # 10 milliseconds during action (100 loops per second)

    # -------------------------------------------------------------------------
    # AUDIO SETTINGS
    # -------------------------------------------------------------------------
    # These control sound playback quality and volume behavior.
    # -------------------------------------------------------------------------

    STOP_AUDIO_WHEN_IDLE = True    # Stop playing sounds when saber is idle (saves power)
    DEFAULT_VOLUME = 70            # Starting volume level (0-100%)
    VOLUME_STEP = 10               # How much volume changes per button press
    MIN_VOLUME = 10                # Lowest allowed volume (prevent accidentally muting)
    MAX_VOLUME = 100               # Highest allowed volume
    CROSSFADE_DURATION = 0.05      # 50ms fade between sounds (prevents audio "pops")
    ENABLE_CROSSFADE = True        # Whether to use crossfading

    # Volume presets are quick-select levels you can cycle through with a long press
    VOLUME_PRESETS = [30, 50, 70, 100]  # Quiet, Medium, Loud, Max

    # Technical audio specifications for WAV files
    AUDIO_SAMPLE_RATE = 22050      # Samples per second (Hz) - standard for CircuitPython
    AUDIO_BITS_PER_SAMPLE = 16     # Bit depth - 16-bit gives good quality audio

    # -------------------------------------------------------------------------
    # MOTION DETECTION TUNING
    # -------------------------------------------------------------------------

    # This ratio determines the "almost swinging" threshold.
    # At 0.8 (80%), we detect when motion is close to triggering a swing.
    # Useful for debugging/testing sensitivity without triggering sounds.
    NEAR_SWING_RATIO = 0.8

    # -------------------------------------------------------------------------
    # TOUCH INPUT SETTINGS
    # -------------------------------------------------------------------------
    # "Debouncing" prevents a single touch from being registered multiple times.
    # Physical buttons/touch sensors can create "bounce" - brief on/off signals.
    # We ignore touches that happen too quickly after the previous one.
    # -------------------------------------------------------------------------

    TOUCH_DEBOUNCE_TIME = 0.02  # 20 milliseconds - ignore touches within this window
    LONG_PRESS_TIME = 1.0       # 1 second hold required to register as "long press"

    # -------------------------------------------------------------------------
    # MEMORY MANAGEMENT
    # -------------------------------------------------------------------------
    # Microcontrollers have limited RAM (memory). We need to be careful not to
    # run out. These settings control automatic memory cleanup.
    #
    # "Garbage Collection" (GC) is like cleaning up - it finds memory that's
    # no longer being used and makes it available again.
    # -------------------------------------------------------------------------

    MAX_IMAGE_CACHE_SIZE = 4       # Keep only 4 images in memory at once
    GC_INTERVAL = 10.0             # Run garbage collector every 10 seconds
    CRITICAL_MEMORY_THRESHOLD = 8192  # Force cleanup if less than 8KB free

    # -------------------------------------------------------------------------
    # HEALTH MONITORING
    # -------------------------------------------------------------------------

    ENABLE_DIAGNOSTICS = True      # Print debug info to console (serial monitor)
    BATTERY_CHECK_INTERVAL = 30.0  # Check battery level every 30 seconds

    # Battery warning thresholds - when to alert the user
    BATTERY_WARNING_THRESHOLD = 15   # Start warning at 15% remaining
    BATTERY_CRITICAL_THRESHOLD = 5   # Critical warning at 5% remaining
    BATTERY_WARNING_INTERVAL = 60.0  # Only warn once per minute (avoid spam)

    # -------------------------------------------------------------------------
    # ERROR HANDLING AND RECOVERY
    # -------------------------------------------------------------------------
    # Hardware can sometimes fail temporarily. These settings control how
    # the code handles errors and attempts to recover.
    # -------------------------------------------------------------------------

    MAX_ACCEL_ERRORS = 10          # Disable accelerometer after 10 consecutive errors
    ERROR_RECOVERY_DELAY = 0.1     # Wait 100ms after an error before retrying
    ACCEL_RECOVERY_INTERVAL = 30.0 # Try to reinitialize accelerometer every 30 seconds

    # -------------------------------------------------------------------------
    # WATCHDOG SETTINGS
    # -------------------------------------------------------------------------
    # See the explanation above about watchdog timers.
    # -------------------------------------------------------------------------

    ENABLE_WATCHDOG = True         # Use watchdog for automatic crash recovery
    WATCHDOG_TIMEOUT = 8.0         # Reset device if code is stuck for 8 seconds

    # -------------------------------------------------------------------------
    # PERSISTENT SETTINGS (Non-Volatile Memory)
    # -------------------------------------------------------------------------
    # NVM (Non-Volatile Memory) is memory that retains data even when power
    # is off. We use it to remember user preferences across reboots.
    #
    # "Byte offsets" are positions in the NVM array where we store each value.
    # Think of NVM as a small array of bytes, and offsets as array indices.
    #
    # The "magic value" is a special marker that tells us if NVM contains valid
    # data (vs. random garbage from a fresh chip). If we find the magic value
    # at the expected position, we know the other stored values are valid.
    # -------------------------------------------------------------------------

    ENABLE_PERSISTENT_SETTINGS = True  # Save settings to survive power-off
    NVM_THEME_OFFSET = 0               # Byte 0: stores current theme index
    NVM_VOLUME_OFFSET = 1              # Byte 1: stores volume level
    NVM_MAGIC_OFFSET = 2               # Byte 2: stores magic validation byte
    NVM_MAGIC_VALUE = 0xAB             # If byte 2 equals 0xAB, data is valid


# =============================================================================
# SECTION 2: HARDWARE CONFIGURATION CONSTANTS
# =============================================================================
# This class contains hardware-specific constants that define how the physical
# device is configured. These are generally not user-adjustable.
# =============================================================================

class SaberConfig:
    """
    HARDWARE CONFIGURATION AND PHYSICAL CONSTANTS

    These values define the hardware setup and physics of the lightsaber.
    Most of these shouldn't be changed unless you're using different hardware.
    """

    # -------------------------------------------------------------------------
    # PIN DEFINITIONS
    # -------------------------------------------------------------------------
    # "Pins" are the physical connection points on the microcontroller.
    # The 'board' module provides human-readable names for them.
    # -------------------------------------------------------------------------

    CAP_PIN = board.CAP_PIN                    # Capacitive touch reference pin
    SPEAKER_ENABLE_PIN = board.SPEAKER_ENABLE  # Pin to turn speaker on/off
    VOLTAGE_MONITOR_PIN = board.VOLTAGE_MONITOR  # Analog pin for battery voltage

    # -------------------------------------------------------------------------
    # NEOPIXEL CONFIGURATION
    # -------------------------------------------------------------------------

    NUM_PIXELS = 30  # Number of LEDs in the blade strip (30 is typical for a short blade)

    # -------------------------------------------------------------------------
    # MOTION DETECTION THRESHOLDS
    # -------------------------------------------------------------------------
    # The accelerometer measures acceleration in meters per second squared (m/s²).
    # We use "magnitude squared" (sum of x² + y² + z²) to avoid expensive
    # square root calculations. This is a common optimization.
    #
    # Higher thresholds = less sensitive (need more force to trigger)
    # Lower thresholds = more sensitive (triggers more easily)
    # -------------------------------------------------------------------------

    SWING_THRESHOLD = 140  # Magnitude² needed to register as a swing
    HIT_THRESHOLD = 220    # Higher threshold for a "hit" (impact/clash)

    # -------------------------------------------------------------------------
    # STATE MACHINE DEFINITIONS
    # -------------------------------------------------------------------------
    # A "state machine" is a programming pattern where the system can only be
    # in one state at a time. This makes complex behavior manageable.
    #
    # States are represented as integers (numbers) for efficiency.
    # -------------------------------------------------------------------------

    STATE_OFF = 0          # Saber is powered off (blade dark, silent)
    STATE_IDLE = 1         # Saber is on, humming, waiting for motion
    STATE_SWING = 2        # Currently swinging (playing swing sound)
    STATE_HIT = 3          # Just clashed/hit something (flash + hit sound)
    STATE_TRANSITION = 4   # Changing between states (power on/off animation)
    STATE_ERROR = 5        # Something went wrong

    # -------------------------------------------------------------------------
    # STATE TRANSITION RULES
    # -------------------------------------------------------------------------
    # This dictionary defines which state transitions are VALID.
    # For example, you can go from OFF to TRANSITION (when powering on),
    # but you can't go directly from OFF to SWING.
    #
    # This prevents bugs where the system gets into impossible states.
    # -------------------------------------------------------------------------

    VALID_TRANSITIONS = {
        STATE_OFF: [STATE_TRANSITION, STATE_ERROR],
        STATE_IDLE: [STATE_SWING, STATE_HIT, STATE_TRANSITION, STATE_ERROR],
        STATE_SWING: [STATE_IDLE, STATE_ERROR],
        STATE_HIT: [STATE_IDLE, STATE_ERROR],
        STATE_TRANSITION: [STATE_OFF, STATE_IDLE, STATE_ERROR],
        STATE_ERROR: [STATE_OFF],  # Can only recover to OFF from ERROR
    }

    # -------------------------------------------------------------------------
    # DISPLAY TIMING
    # -------------------------------------------------------------------------

    DISPLAY_TIMEOUT_SAVER_ON = UserConfig.DISPLAY_TIMEOUT_SAVER
    DISPLAY_TIMEOUT_SAVER_OFF = UserConfig.DISPLAY_TIMEOUT_NORMAL
    IMAGE_DISPLAY_DURATION_SAVER_ON = 1.5   # Show theme logo for 1.5 seconds
    IMAGE_DISPLAY_DURATION_SAVER_OFF = 3.0  # Or 3 seconds in normal mode

    # -------------------------------------------------------------------------
    # ANIMATION TIMING CONSTANTS
    # -------------------------------------------------------------------------

    POWER_ON_DURATION = 1.7    # Blade ignition takes 1.7 seconds
    POWER_OFF_DURATION = 1.15  # Blade retraction takes 1.15 seconds
    FADE_OUT_DURATION = 0.5    # Audio fade out time
    SWING_BLEND_MIDPOINT = 0.5 # Color blend timing for swing animation
    SWING_BLEND_SCALE = 2.0    # Speed of color transition during swing

    # -------------------------------------------------------------------------
    # BATTERY MONITORING CONSTANTS
    # -------------------------------------------------------------------------
    # LiPo batteries have a voltage range: 3.3V (empty) to 4.2V (full)
    # We use ADC (Analog-to-Digital Converter) to read voltage.
    # -------------------------------------------------------------------------

    BATTERY_VOLTAGE_SAMPLES = 10   # Average 10 readings for accuracy
    BATTERY_MIN_VOLTAGE = 3.3      # Battery empty voltage
    BATTERY_MAX_VOLTAGE = 4.2      # Battery full voltage
    BATTERY_ADC_MAX = 65535        # Maximum ADC reading (16-bit resolution)
    BATTERY_VOLTAGE_DIVIDER = 2    # Voltage divider ratio on board

    # -------------------------------------------------------------------------
    # AUDIO CONSTANTS
    # -------------------------------------------------------------------------

    SILENCE_SAMPLE_SIZE = 1024     # Number of samples in silence buffer
    AUDIO_STOP_CHECK_INTERVAL = 0.03  # Check if audio done every 30ms
    AUDIO_BUFFER_SIZE = 4096       # Audio buffer size for smooth playback
    FADE_IN_SAMPLES = 100          # Fade in over 100 samples (prevents pops)
    FADE_OUT_SAMPLES = 100         # Fade out over 100 samples

    # -------------------------------------------------------------------------
    # THEME DEFINITIONS
    # -------------------------------------------------------------------------
    # Each theme has a name, main blade color, and hit/clash color.
    # Colors are RGB tuples: (Red, Green, Blue) with values 0-255.
    #
    # (0, 0, 255) = Blue      (255, 0, 0) = Red
    # (0, 255, 0) = Green     (255, 255, 0) = Yellow
    # (255, 0, 255) = Magenta (255, 255, 255) = White
    # -------------------------------------------------------------------------

    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255),   "hit_color": (255, 255, 255)},   # Blue blade, white clash
        {"name": "powerpuff",  "color": (255, 0, 255), "hit_color": (0, 200, 255)},    # Magenta blade, cyan clash
        {"name": "ricknmorty", "color": (0, 255, 0),   "hit_color": (255, 0, 0)},      # Green blade, red clash
        {"name": "spongebob",  "color": (255, 255, 0), "hit_color": (255, 255, 255)},  # Yellow blade, white clash
    ]

    # How much to dim the main color for idle state (divide by 4 = 25% brightness)
    IDLE_COLOR_DIVISOR = 4


# =============================================================================
# SECTION 3: AUDIO UTILITY FUNCTIONS
# =============================================================================
# These are helper functions for audio processing. They're "static methods"
# meaning they don't need an instance of the class - they're just grouped here.
# =============================================================================

class AudioUtils:
    """
    AUDIO PROCESSING UTILITIES

    Static helper functions for working with audio data.
    These handle volume scaling and fade effects.
    """

    @staticmethod  # This decorator indicates the method doesn't use 'self'
    def scale_sample(sample, volume_percent):
        """
        SCALE AN AUDIO SAMPLE BY VOLUME

        Audio samples are numbers representing sound wave amplitude.
        16-bit audio uses values from -32768 to +32767.
        To reduce volume, we multiply by a fraction.

        Args:
            sample: One audio sample (-32768 to 32767)
            volume_percent: Volume level (0-100)

        Returns:
            Scaled sample, clamped to valid range
        """
        # If volume is 100% or more, return unchanged
        if volume_percent >= 100:
            return sample

        # If volume is 0 or less, return silence
        if volume_percent <= 0:
            return 0

        # Scale the sample by the volume percentage
        # Example: sample=1000, volume=50 -> 1000 * 50 / 100 = 500
        scaled = int(sample * volume_percent / 100)

        # "Clamp" the value to prevent overflow (stay within valid range)
        return max(-32768, min(32767, scaled))

    @staticmethod
    def apply_fade_envelope(samples, fade_in_samples=100, fade_out_samples=100):
        """
        APPLY FADE IN/OUT TO AUDIO

        Without fading, audio that starts or stops abruptly creates "clicks"
        or "pops" - unpleasant sharp sounds. Fading gradually increases/decreases
        volume at the beginning and end to prevent this.

        This modifies the samples array IN PLACE (changes the original).

        Args:
            samples: Array of audio samples to modify
            fade_in_samples: How many samples to fade in over
            fade_out_samples: How many samples to fade out over

        Returns:
            The modified samples array
        """
        sample_count = len(samples)

        # FADE IN: Gradually increase volume at the start
        # factor goes from 0.0 to 1.0 over fade_in_samples
        for i in range(min(fade_in_samples, sample_count)):
            factor = i / fade_in_samples  # 0/100=0.0, 50/100=0.5, 100/100=1.0
            samples[i] = int(samples[i] * factor)

        # FADE OUT: Gradually decrease volume at the end
        start_fade_out = max(0, sample_count - fade_out_samples)
        for i in range(start_fade_out, sample_count):
            # factor goes from 1.0 down to 0.0
            factor = (sample_count - i) / fade_out_samples
            samples[i] = int(samples[i] * factor)

        return samples

    @staticmethod
    def create_silence(duration_ms, sample_rate=22050):
        """
        CREATE A BUFFER OF SILENCE

        Sometimes we need to play "nothing" - this creates a buffer of
        zero-valued samples. Useful for smooth transitions.

        Args:
            duration_ms: How long the silence should be (milliseconds)
            sample_rate: Audio sample rate (samples per second)

        Returns:
            A RawSample object containing silence
        """
        # Calculate how many samples we need
        # duration_ms / 1000 = duration in seconds
        # * sample_rate = number of samples
        num_samples = int((duration_ms / 1000.0) * sample_rate)

        # Create array of zeros (silence)
        # "h" means signed 16-bit integers
        silence = array.array("h", [0] * num_samples)

        # Wrap in RawSample for audio playback
        return audiocore.RawSample(silence, sample_rate=sample_rate)


# =============================================================================
# SECTION 3.5: PERSISTENT SETTINGS MANAGER
# =============================================================================
# This class handles saving and loading settings to Non-Volatile Memory (NVM).
# NVM is a small amount of memory that keeps its data even when power is off.
# =============================================================================

class PersistentSettings:
    """
    PERSISTENT SETTINGS STORAGE

    Manages saving user preferences (theme, volume) to NVM so they're
    remembered even after the device is turned off or reset.

    HOW IT WORKS:
    1. NVM is accessed like a simple array of bytes
    2. We store theme at byte 0, volume at byte 1
    3. We use a "magic byte" at byte 2 to verify data is valid
    4. If the magic byte matches our expected value, we trust the data

    This is important because NVM might contain random garbage on a new
    chip or after corruption - the magic byte tells us if our data is there.
    """

    @staticmethod
    def is_valid():
        """
        CHECK IF STORED SETTINGS ARE VALID

        Returns True if NVM contains valid settings data.
        Checks if the magic byte matches what we expect.
        """
        # Skip if persistent settings are disabled
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False

        try:
            # Read the magic byte and compare to expected value
            return microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] == UserConfig.NVM_MAGIC_VALUE
        except Exception:
            # If anything goes wrong reading NVM, consider invalid
            return False

    @staticmethod
    def load_theme():
        """
        LOAD SAVED THEME INDEX FROM NVM

        Returns the stored theme index (0-3) or 0 if not valid.
        """
        # If NVM doesn't have valid data, return default (first theme)
        if not PersistentSettings.is_valid():
            return 0

        try:
            theme = microcontroller.nvm[UserConfig.NVM_THEME_OFFSET]

            # Validate the theme index is within bounds
            if theme < len(SaberConfig.THEMES):
                return theme
        except Exception:
            pass  # If error, fall through to return default

        return 0  # Default to first theme

    @staticmethod
    def load_volume():
        """
        LOAD SAVED VOLUME LEVEL FROM NVM

        Returns the stored volume (10-100) or default if not valid.
        """
        if not PersistentSettings.is_valid():
            return UserConfig.DEFAULT_VOLUME

        try:
            volume = microcontroller.nvm[UserConfig.NVM_VOLUME_OFFSET]

            # Validate volume is within allowed range
            if UserConfig.MIN_VOLUME <= volume <= UserConfig.MAX_VOLUME:
                return volume
        except Exception:
            pass

        return UserConfig.DEFAULT_VOLUME

    @staticmethod
    def save_theme(theme_index):
        """
        SAVE THEME INDEX TO NVM

        Writes the theme index to NVM along with magic byte.
        Returns True on success, False on failure.
        """
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False

        try:
            # Write theme index
            microcontroller.nvm[UserConfig.NVM_THEME_OFFSET] = theme_index
            # Write magic byte to mark data as valid
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("Error saving theme:", e)
            return False

    @staticmethod
    def save_volume(volume):
        """
        SAVE VOLUME LEVEL TO NVM

        Writes volume and magic byte to NVM.
        Returns True on success, False on failure.
        """
        if not UserConfig.ENABLE_PERSISTENT_SETTINGS:
            return False

        try:
            microcontroller.nvm[UserConfig.NVM_VOLUME_OFFSET] = volume
            microcontroller.nvm[UserConfig.NVM_MAGIC_OFFSET] = UserConfig.NVM_MAGIC_VALUE
            return True
        except Exception as e:
            print("Error saving volume:", e)
            return False


# =============================================================================
# SECTION 4: HARDWARE INITIALIZATION AND MANAGEMENT
# =============================================================================
# This class handles setting up all the physical hardware components.
# It uses "defensive programming" - assuming things might fail and handling
# errors gracefully instead of crashing.
# =============================================================================

class SaberHardware:
    """
    HARDWARE INITIALIZATION AND MANAGEMENT

    This class is responsible for:
    1. Initializing all hardware components (LEDs, sensors, touch inputs)
    2. Tracking which components initialized successfully
    3. Providing a cleanup method to safely shut down
    4. Attempting to recover from hardware failures

    "Encapsulation" - grouping related functionality together - makes the
    code easier to understand and maintain.
    """

    def __init__(self):
        """
        CONSTRUCTOR - Called when a SaberHardware object is created

        The __init__ method is special in Python - it runs automatically
        when you create a new instance of the class:
            hw = SaberHardware()  # This calls __init__
        """
        print("Initializing Saber Hardware...")

        # Track which hardware initialized successfully
        # This dictionary acts as a status board
        self.hardware_status = {
            "strip": False,    # NeoPixel LED strip
            "touch": False,    # Touch input buttons
            "accel": False,    # Accelerometer (motion sensor)
            "battery": False   # Battery voltage monitor
        }

        # =====================================================================
        # CAPACITIVE TOUCH REFERENCE PIN
        # =====================================================================
        # This pin helps calibrate the capacitive touch system.
        # We set it to output LOW to provide a reference.
        # =====================================================================
        try:
            self.cap_pin = DigitalInOut(SaberConfig.CAP_PIN)
            self.cap_pin.switch_to_output(value=False)  # Set as output, drive LOW
        except Exception as e:
            print("  CAP_PIN error:", e)
            self.cap_pin = None  # Mark as unavailable

        # =====================================================================
        # SPEAKER ENABLE PIN
        # =====================================================================
        # This pin turns the speaker amplifier on/off.
        # We set it HIGH (True) to enable sound output.
        # =====================================================================
        try:
            self.speaker_enable = DigitalInOut(SaberConfig.SPEAKER_ENABLE_PIN)
            self.speaker_enable.switch_to_output(value=True)  # Enable speaker
        except Exception as e:
            print("  SPEAKER_ENABLE error:", e)
            self.speaker_enable = None

        # =====================================================================
        # BATTERY VOLTAGE MONITOR
        # =====================================================================
        # AnalogIn reads the battery voltage through a voltage divider.
        # This lets us monitor battery level and warn when it's low.
        # =====================================================================
        try:
            self.battery_voltage = analogio.AnalogIn(SaberConfig.VOLTAGE_MONITOR_PIN)
            self.hardware_status["battery"] = True
        except Exception as e:
            print("  VOLTAGE_MONITOR error:", e)
            self.battery_voltage = None

        # Initialize the LED strip (calls helper method)
        self.strip = self._init_strip()

        # Initialize touch inputs
        self.touch_left = None
        self.touch_right = None
        self.touch_batt_a3 = None
        self.touch_batt_a4 = None
        self._init_touch()

        # Initialize accelerometer (motion sensor)
        self.accel = self._init_accel()
        self.accel_error_count = 0  # Track consecutive errors

        # Print summary
        print("Hardware init complete.")
        print("Status:", self.hardware_status)
        print()

    def _init_strip(self):
        """
        INITIALIZE NEOPIXEL LED STRIP

        NeoPixels are addressable RGB LEDs - each LED can be individually
        controlled. The strip connects to the EXTERNAL_NEOPIXEL port.

        Returns: NeoPixel object if successful, None if failed
        """
        try:
            strip = neopixel.NeoPixel(
                board.EXTERNAL_NEOPIXEL,  # Which pin the strip is connected to
                SaberConfig.NUM_PIXELS,    # How many LEDs in the strip
                brightness=UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS,  # Starting brightness
                auto_write=False,          # Don't update LEDs automatically (we call show())
                pixel_order=neopixel.GRB   # Color order: Green-Red-Blue (common for WS2812)
            )

            # Turn all LEDs off initially
            strip.fill(0)  # 0 = black/off
            strip.show()   # Send the data to the LEDs

            print("  NeoPixel strip OK.")
            self.hardware_status["strip"] = True
            return strip

        except Exception as e:
            print("  NeoPixel error:", e)
            return None

    def _init_touch(self):
        """
        INITIALIZE CAPACITIVE TOUCH INPUTS

        Capacitive touch works by detecting changes in electrical capacitance
        when a finger (which is conductive) comes near the sensor pad.
        Unlike mechanical buttons, there's no physical switch to press.
        """
        try:
            # Create TouchIn objects for each touch pad
            self.touch_left = touchio.TouchIn(board.TOUCH1)   # Left button (theme)
            self.touch_right = touchio.TouchIn(board.TOUCH4)  # Right button (power)
            self.touch_batt_a3 = touchio.TouchIn(board.A3)    # A3 pad (battery/volume)
            self.touch_batt_a4 = touchio.TouchIn(board.A4)    # A4 pad (battery/volume)

            print("  Touch inputs OK.")
            self.hardware_status["touch"] = True

        except Exception as e:
            print("  Touch error:", e)

    def _init_accel(self):
        """
        INITIALIZE ACCELEROMETER (MOTION SENSOR)

        The MSA311 is a 3-axis accelerometer that measures acceleration
        (rate of change of velocity) in the X, Y, and Z directions.
        It communicates via I2C - a two-wire serial protocol.

        IMPORTANT: We store the I2C bus reference to prevent garbage collection.
        If Python's garbage collector frees the I2C bus object while the
        accelerometer is still using it, things will break!
        """
        try:
            # Create I2C bus object (SCL = clock, SDA = data)
            # We store it as self.i2c_bus to keep a reference alive
            self.i2c_bus = busio.I2C(board.SCL, board.SDA)

            # Create accelerometer object using the I2C bus
            accel = adafruit_msa3xx.MSA311(self.i2c_bus)

            print("  Accelerometer OK.")
            self.hardware_status["accel"] = True
            return accel

        except Exception as e:
            print("  Accel error:", e)
            self.i2c_bus = None  # Clear reference if failed
            return None

    def try_reinit_accel(self):
        """
        ATTEMPT TO REINITIALIZE A FAILED ACCELEROMETER

        Sometimes hardware fails temporarily (loose connection, EMI, etc.).
        This method tries to reinitialize the accelerometer from scratch.

        Returns: True if recovery successful, False otherwise
        """
        # If accelerometer is already working, nothing to do
        if self.accel is not None:
            return True

        try:
            # Clean up old I2C bus if it exists
            if hasattr(self, 'i2c_bus') and self.i2c_bus is not None:
                try:
                    self.i2c_bus.deinit()  # Release hardware resources
                except Exception:
                    pass  # Ignore cleanup errors

            # Try to reinitialize fresh
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
        """
        CLEAN UP HARDWARE RESOURCES

        Called when shutting down. Releases hardware resources gracefully:
        - Turns off LEDs
        - Disables speaker
        - Releases I2C bus

        This is good practice to leave hardware in a known state.
        """
        # Turn off LED strip
        if self.strip:
            try:
                self.strip.fill(0)  # All LEDs off
                self.strip.show()
            except Exception:
                pass  # Ignore errors during cleanup

        # Disable speaker amplifier
        if self.speaker_enable:
            try:
                self.speaker_enable.value = False
            except Exception:
                pass

        # Release I2C bus
        if hasattr(self, 'i2c_bus') and self.i2c_bus is not None:
            try:
                self.i2c_bus.deinit()
            except Exception:
                pass


# =============================================================================
# SECTION 5: AUDIO MANAGER
# =============================================================================
# Handles all audio playback including loading files, playing sounds,
# managing volume, and implementing fade effects.
# =============================================================================

class AudioManager:
    """
    AUDIO PLAYBACK MANAGEMENT

    Responsible for:
    - Loading and playing WAV audio files
    - Volume control and presets
    - Crossfading between sounds (smooth transitions)
    - Cleaning up audio resources (closing files)

    AUDIO BASICS:
    - Sound is stored as WAV files (arrays of numbers representing sound waves)
    - Each number is a "sample" - the amplitude at a moment in time
    - Sample rate (22050 Hz) means 22,050 samples per second
    - We play samples sequentially through the speaker to recreate sound
    """

    def __init__(self):
        """
        Initialize the audio system.
        """
        # Create audio output object for the speaker
        try:
            self.audio = audioio.AudioOut(board.SPEAKER)
            print("Audio system OK.")
        except Exception as e:
            print("Audio error:", e)
            self.audio = None

        # File handle tracking (to ensure proper cleanup)
        self.current_wave_file = None  # The open file object
        self.current_wav = None        # The WaveFile wrapper

        # Create silence sample for clean transitions
        self.silence_sample = self._create_silence_sample()

        # Volume state
        self.volume = UserConfig.DEFAULT_VOLUME  # Current volume (0-100)
        self.volume_preset_index = 1  # Which preset we're on (1 = "Medium")

        # Fade state (for non-blocking fade effects)
        self.fade_start_time = None
        self.fade_duration = 0
        self.is_fading = False

        # Crossfade state
        self.is_crossfading = False
        self.crossfade_start_time = None

        print("  Audio volume: {}%".format(self.volume))

    def _create_silence_sample(self):
        """
        CREATE A SILENT AUDIO SAMPLE

        Used for "keepalive" - some audio hardware needs continuous
        signal to stay initialized.
        """
        try:
            # Create array of zeros (silence)
            silent_samples = array.array("h", [0] * SaberConfig.SILENCE_SAMPLE_SIZE)
            return audiocore.RawSample(silent_samples)
        except Exception as e:
            print("Error creating silence sample:", e)
            return None

    def _close_current_file(self):
        """
        SAFELY CLOSE THE CURRENT AUDIO FILE

        File handles are limited resources. We must close them when done
        or the system will eventually run out of file handles.
        """
        if self.current_wave_file is not None:
            try:
                self.current_wave_file.close()
            except Exception as e:
                print("Error closing audio file:", e)
            finally:
                # Always clear references, even if close() failed
                self.current_wave_file = None
                self.current_wav = None

    def set_volume(self, volume_percent):
        """
        SET VOLUME LEVEL

        Note: CircuitPython's audioio doesn't support native volume control.
        This tracks the volume setting for potential future software mixing.

        Args:
            volume_percent: New volume level (0-100)

        Returns:
            The actual volume set (clamped to min/max)
        """
        # Clamp to allowed range
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
        """
        CYCLE THROUGH VOLUME PRESETS

        Presets provide quick access to common volume levels.
        Each long-press advances to the next preset (wraps around).
        """
        # Move to next preset (modulo wraps around to 0)
        self.volume_preset_index = (self.volume_preset_index + 1) % len(UserConfig.VOLUME_PRESETS)
        preset_volume = UserConfig.VOLUME_PRESETS[self.volume_preset_index]
        self.set_volume(preset_volume)
        return preset_volume

    def _load_and_process_wav(self, filename, apply_volume=True):
        """
        LOAD A WAV FILE FOR PLAYBACK

        Opens the file and creates a WaveFile object for playback.

        Args:
            filename: Path to the WAV file
            apply_volume: Reserved for future software volume control

        Returns:
            Tuple of (file_handle, WaveFile) or (None, None) on error
        """
        try:
            # Open file in binary read mode
            wave_file = open(filename, "rb")
            # Wrap in WaveFile for audio playback
            wav = audiocore.WaveFile(wave_file)
            return (wave_file, wav)

        except OSError as e:
            # OSError often means file not found
            print("Audio file not found:", filename)
            return (None, None)

        except Exception as e:
            print("Error loading audio:", e)
            return (None, None)

    def play_audio_clip(self, theme_index, name, loop=False):
        """
        PLAY AN AUDIO CLIP

        Loads and plays a sound file. Handles cleanup of previous audio.

        Args:
            theme_index: Which theme (0-3) for file naming
            name: Sound type ("on", "off", "idle", "swing", "hit", "switch")
            loop: Whether to repeat the sound continuously

        Returns:
            True if playback started, False on error

        File naming convention: sounds/[theme_index][name].wav
        Example: sounds/0idle.wav (theme 0, idle sound)
        """
        if not self.audio:
            return False

        # Free memory before loading new audio
        gc.collect()

        # If something is already playing, handle transition
        if UserConfig.ENABLE_CROSSFADE and self.audio.playing:
            self.start_crossfade()
            time.sleep(0.01)  # Brief pause for crossfade to begin
        else:
            if self.audio.playing:
                self.audio.stop()

        # Close previous file (important for memory/handles)
        self._close_current_file()

        # Build filename
        filename = "sounds/{}{}.wav".format(theme_index, name)

        # Load the audio file
        self.current_wave_file, self.current_wav = self._load_and_process_wav(
            filename,
            apply_volume=(self.volume < 100)
        )

        if self.current_wav is None:
            return False

        # Start playback
        try:
            self.audio.play(self.current_wav, loop=loop)
            return True
        except Exception as e:
            print("Error playing audio:", e)
            self._close_current_file()
            return False

    def start_crossfade(self):
        """Start crossfade (fade out current sound)."""
        if UserConfig.ENABLE_CROSSFADE:
            self.is_crossfading = True
            self.crossfade_start_time = time.monotonic()

    def update_crossfade(self):
        """
        UPDATE CROSSFADE STATE (call each loop iteration)

        Returns True when crossfade is complete.
        """
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
            time.sleep(0.001)  # Tiny delay helps prevent pop
            self.audio.stop()

    def check_audio_done(self):
        """Check if audio finished and clean up resources."""
        if self.audio and not self.audio.playing and self.current_wave_file is not None:
            self._close_current_file()

    def start_fade_out(self, duration=None):
        """
        START A NON-BLOCKING FADE OUT

        "Non-blocking" means it doesn't pause the program. Instead, we
        track state and check progress each loop iteration via update_fade().
        """
        if duration is None:
            duration = SaberConfig.FADE_OUT_DURATION
        self.fade_start_time = time.monotonic()
        self.fade_duration = duration
        self.is_fading = True

    def update_fade(self):
        """
        UPDATE FADE STATE (call each loop iteration)

        Returns True when fade is complete.
        """
        if not self.is_fading:
            return False

        elapsed = time.monotonic() - self.fade_start_time
        if elapsed >= self.fade_duration:
            # Fade complete
            self.stop_audio()
            self._close_current_file()
            self.is_fading = False

            # Optionally play silence to keep audio hardware active
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
# SECTION 6: DISPLAY MANAGER
# =============================================================================
# Handles the TFT display - showing images, text, and battery status.
# Includes an LRU (Least Recently Used) cache for images to save memory.
# =============================================================================

class SaberDisplay:
    """
    DISPLAY MANAGEMENT

    Controls the 128x128 TFT display. Features:
    - Image display with caching (keeps recently used images in memory)
    - Battery status display with progress bar
    - Volume status display
    - Automatic timeout to save power

    LRU CACHE EXPLAINED:
    Loading images from the SD card is slow. We keep recent images in memory
    for fast access. But memory is limited, so when the cache is full, we
    remove the Least Recently Used image to make room.
    """

    def __init__(self, battery_voltage_ref):
        """
        Initialize the display manager.

        Args:
            battery_voltage_ref: A function to call to get battery percentage
        """
        # Create main display group (container for display elements)
        self.main_group = displayio.Group()

        try:
            board.DISPLAY.auto_refresh = True  # Auto-update when content changes
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
        except Exception as e:
            print("Display init error:", e)

        # Image cache: dictionary mapping cache keys to TileGrid objects
        self.image_cache = {}
        # Track access order for LRU eviction (oldest first)
        self.image_cache_order = []

        # Display timeout tracking
        self.display_start_time = 0
        self.display_active = False
        self.display_timeout = SaberConfig.DISPLAY_TIMEOUT_SAVER_OFF

        # Store reference to battery function
        self.get_battery_voltage_pct = battery_voltage_ref

        self.image_display_duration = SaberConfig.IMAGE_DISPLAY_DURATION_SAVER_OFF

        # Start with display off
        self.turn_off_screen()

    def turn_off_screen(self):
        """Turn off display backlight to save power."""
        try:
            board.DISPLAY.brightness = 0
        except Exception as e:
            print("Error turning off screen:", e)

    def update_display_timeout(self, timeout):
        """Update how long display stays on."""
        self.display_timeout = timeout

    def update_image_display_duration(self, duration):
        """Update how long images are shown."""
        self.image_display_duration = duration

    def update_power_saver_settings(self, saver_on):
        """Apply power saver mode settings to display."""
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
        """
        DISPLAY BATTERY STATUS

        Shows battery percentage as text and a progress bar.
        If on USB power, shows "USB" instead of percentage.
        """
        try:
            # Clear any existing display content
            while len(self.main_group):
                self.main_group.pop()

            # Get current battery level
            battery_percent = self.get_battery_voltage_pct()

            # Create text label
            if battery_percent != "USB":
                battery_text = "BATTERY: {}%".format(battery_percent)
            else:
                battery_text = "BATTERY: USB"

            battery_label = label.Label(
                terminalio.FONT,
                text=battery_text,
                scale=2,         # 2x size
                color=0xFFFFFF,  # White text
                x=10, y=30       # Position
            )
            self.main_group.append(battery_label)

            # Draw progress bar if not on USB
            if battery_percent != "USB":
                battery_bar_width = max(1, min(battery_percent, 100))
                battery_group = displayio.Group()

                # Background bar (gray)
                bg_palette = displayio.Palette(1)
                bg_palette[0] = 0x444444  # Dark gray
                bat_bg_bitmap = displayio.Bitmap(100, 14, 1)
                bat_bg_bitmap.fill(0)
                bg_tile = displayio.TileGrid(bat_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
                battery_group.append(bg_tile)

                # Foreground bar (yellow, width = percentage)
                bat_palette = displayio.Palette(1)
                bat_palette[0] = 0xFFFF00  # Yellow
                bat_bitmap = displayio.Bitmap(battery_bar_width, 10, 1)
                bat_bitmap.fill(0)
                bat_tile = displayio.TileGrid(bat_bitmap, pixel_shader=bat_palette, x=16, y=48)
                battery_group.append(bat_tile)

                self.main_group.append(battery_group)

            # Show on display
            board.DISPLAY.root_group = self.main_group
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS

            # Track display timing for auto-off
            self.display_start_time = time.monotonic()
            self.display_active = True

        except Exception as e:
            print("Error showing battery status:", e)

    def show_volume_status(self, volume_percent):
        """
        DISPLAY VOLUME STATUS

        Shows current volume as text and a progress bar (green).
        """
        try:
            # Clear display
            while len(self.main_group):
                self.main_group.pop()

            # Volume text
            volume_text = "VOLUME: {}%".format(volume_percent)
            volume_label = label.Label(
                terminalio.FONT,
                text=volume_text,
                scale=2,
                color=0x00FF00,  # Green text
                x=10, y=30
            )
            self.main_group.append(volume_label)

            # Progress bar
            volume_bar_width = max(1, min(volume_percent, 100))
            volume_group = displayio.Group()

            # Background
            bg_palette = displayio.Palette(1)
            bg_palette[0] = 0x444444
            vol_bg_bitmap = displayio.Bitmap(100, 14, 1)
            vol_bg_bitmap.fill(0)
            bg_tile = displayio.TileGrid(vol_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
            volume_group.append(bg_tile)

            # Volume level (green)
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

    def _evict_oldest_image(self):
        """
        REMOVE OLDEST IMAGE FROM CACHE (LRU EVICTION)

        When cache is full, remove the least recently used image
        to make room for a new one.
        """
        if not self.image_cache_order:
            return

        # Remove from order tracking (first = oldest)
        oldest_key = self.image_cache_order.pop(0)

        # Remove from cache and free memory
        if oldest_key in self.image_cache:
            try:
                tile_grid = self.image_cache[oldest_key]
                del tile_grid  # Dereference
            except Exception:
                pass
            del self.image_cache[oldest_key]

        gc.collect()  # Free memory

    def _load_image(self, theme_index, image_type="logo"):
        """
        LOAD IMAGE WITH LRU CACHING

        If image is in cache, move it to "most recent" and return it.
        If not, load from disk, add to cache (evicting if needed).
        """
        cache_key = "{}{}".format(theme_index, image_type)

        # Check if already cached
        if cache_key in self.image_cache:
            # Move to end of order list (most recently used)
            self.image_cache_order.remove(cache_key)
            self.image_cache_order.append(cache_key)
            return self.image_cache[cache_key]

        # Load from disk
        filename = "/images/{}{}.bmp".format(theme_index, image_type)
        try:
            # Evict oldest if cache is full
            if len(self.image_cache) >= UserConfig.MAX_IMAGE_CACHE_SIZE:
                self._evict_oldest_image()

            # Load bitmap
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
        """
        DISPLAY A THEME IMAGE

        Loads and shows the theme logo for the specified duration.
        """
        if duration is None:
            duration = self.image_display_duration
            print("\n" * 40)  # Clear serial console for cleaner output

        try:
            # Clear display
            while len(self.main_group):
                self.main_group.pop()

            # Load and display image
            image = self._load_image(theme_index, image_type)
            if image:
                self.main_group.append(image)
                board.DISPLAY.root_group = self.main_group
                board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
                board.DISPLAY.refresh()

                # Show for specified duration
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
        """
        UPDATE DISPLAY STATE (call each loop iteration)

        Handles automatic timeout - turns off display after period of inactivity.
        """
        if self.display_active:
            elapsed = time.monotonic() - self.display_start_time
            if elapsed > self.display_timeout:
                self.turn_off_screen()
                self.display_active = False

    def clear_cache(self):
        """Clear all cached images and free memory."""
        self.image_cache.clear()
        self.image_cache_order.clear()
        gc.collect()

    def cleanup(self):
        """Clean up display resources."""
        self.clear_cache()
        self.turn_off_screen()


# =============================================================================
# SECTION 7: MAIN CONTROLLER
# =============================================================================
# This is the brain of the operation - coordinates all other components,
# manages state, and runs the main loop.
# =============================================================================

class SaberController:
    """
    MAIN LIGHTSABER CONTROLLER

    This is the "orchestrator" - it coordinates all other components:
    - Hardware (LEDs, sensors, touch inputs)
    - Audio (sound playback)
    - Display (screen output)

    RESPONSIBILITIES:
    - State machine management (OFF, IDLE, SWING, HIT, etc.)
    - Touch input handling with debouncing
    - Motion detection and response
    - LED color animation
    - Battery monitoring
    - Error recovery

    STATE MACHINE:
    The controller can only be in one state at a time. Valid transitions:

        OFF ─────> TRANSITION ─────> IDLE
         ^              |              |
         |              v              v
         └─── TRANSITION <─── SWING/HIT
    """

    def __init__(self):
        """
        Initialize the controller and all sub-components.
        """
        print("Booting SaberController...")

        # Create sub-component instances
        self.hw = SaberHardware()
        self.display = SaberDisplay(self._get_battery_percentage)
        self.audio = AudioManager()

        # Power and timing state
        self.power_saver_mode = False
        self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY
        self.mode = SaberConfig.STATE_OFF  # Start in OFF state

        # Load persistent settings (theme and volume from last session)
        self.theme_index = PersistentSettings.load_theme()
        saved_volume = PersistentSettings.load_volume()
        self.audio.set_volume(saved_volume)
        print("  Loaded settings: theme={}, volume={}%".format(self.theme_index, saved_volume))

        # Color state (RGB tuples)
        self.color_idle = (0, 0, 0)    # Dim color when on but still
        self.color_swing = (0, 0, 0)   # Bright color during swing
        self.color_hit = (0, 0, 0)     # Flash color on hit
        self.color_active = (0, 0, 0)  # Currently displayed color
        self.last_color = None         # Previous color (optimization)

        # Timing state
        self.event_start_time = 0                    # When current event started
        self.last_gc_time = time.monotonic()         # Last garbage collection
        self.last_battery_check = 0                  # Last battery level check
        self.last_battery_warning = 0                # Last battery warning shown
        self.last_accel_recovery_attempt = 0         # Last accelerometer recovery attempt

        # =====================================================================
        # PER-INPUT TOUCH STATE
        # =====================================================================
        # Each touch input gets its own state tracking. This is important
        # because we might be touching multiple buttons at once, and we need
        # to track debouncing and long-press independently for each.
        # =====================================================================
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

        # Diagnostics (for debugging)
        self.loop_count = 0       # How many main loop iterations
        self.state_changes = 0    # How many state transitions

        # Initialize watchdog timer
        self.watchdog = None
        self._init_watchdog()

        # Apply theme colors
        self._update_theme_colors()
        self._apply_power_mode()
        self.display.turn_off_screen()

        print("SaberController init complete.\n")

    def _init_watchdog(self):
        """
        INITIALIZE WATCHDOG TIMER

        The watchdog will reset the device if the main loop gets stuck.
        We must "feed" it regularly to prove the code is still running.
        """
        if not UserConfig.ENABLE_WATCHDOG or not WATCHDOG_AVAILABLE:
            return

        try:
            self.watchdog = microcontroller.watchdog
            self.watchdog.timeout = UserConfig.WATCHDOG_TIMEOUT
            self.watchdog.mode = WatchDogMode.RESET  # Reset on timeout
            print("  Watchdog enabled ({}s timeout)".format(UserConfig.WATCHDOG_TIMEOUT))
        except Exception as e:
            print("  Watchdog init failed:", e)
            self.watchdog = None

    def _feed_watchdog(self):
        """
        FEED THE WATCHDOG

        This tells the watchdog "I'm still alive, don't reset me!"
        Must be called regularly (at least once per WATCHDOG_TIMEOUT seconds).
        """
        if self.watchdog is not None:
            try:
                self.watchdog.feed()
            except Exception:
                pass  # Ignore feed errors

    def _apply_power_mode(self):
        """Apply current power mode settings."""
        if self.power_saver_mode:
            self.display.update_power_saver_settings(True)
            self.cpu_loop_delay = 0.03  # Slower loop in power saver
        else:
            self.display.update_power_saver_settings(False)
            self.cpu_loop_delay = UserConfig.ACTIVE_LOOP_DELAY

    def toggle_power_mode(self):
        """Toggle power saver mode on/off."""
        self.power_saver_mode = not self.power_saver_mode
        self._apply_power_mode()
        print("Power saver mode:", "ON" if self.power_saver_mode else "OFF")

    def _get_battery_percentage(self):
        """
        GET CURRENT BATTERY PERCENTAGE

        Reads battery voltage and converts to percentage.
        Returns "USB" if connected to USB power.

        HOW IT WORKS:
        1. Check if USB is connected (if so, return "USB")
        2. Read analog voltage multiple times and average (noise reduction)
        3. Convert ADC reading to actual voltage
        4. Map voltage to percentage (3.3V=0%, 4.2V=100%)
        """
        # If USB is connected, battery isn't being used
        if supervisor.runtime.usb_connected:
            return "USB"

        if not self.hw.battery_voltage:
            return 0

        try:
            # Take multiple readings and average (reduces noise)
            sum_val = 0
            for _ in range(SaberConfig.BATTERY_VOLTAGE_SAMPLES):
                sum_val += self.hw.battery_voltage.value
                time.sleep(0.001)  # Small delay between readings

            avg_val = sum_val / SaberConfig.BATTERY_VOLTAGE_SAMPLES

            # Convert ADC reading to voltage
            # ADC gives 0-65535, reference voltage is typically 3.3V
            # Voltage divider on board means actual voltage is 2x the reading
            voltage = (avg_val / SaberConfig.BATTERY_ADC_MAX) * \
                      self.hw.battery_voltage.reference_voltage * \
                      SaberConfig.BATTERY_VOLTAGE_DIVIDER

            # Convert voltage to percentage
            # 3.3V = 0%, 4.2V = 100%
            percent = ((voltage - SaberConfig.BATTERY_MIN_VOLTAGE) /
                      (SaberConfig.BATTERY_MAX_VOLTAGE - SaberConfig.BATTERY_MIN_VOLTAGE)) * 100

            # Clamp to 0-100 range
            return min(max(int(percent), 0), 100)

        except Exception as e:
            print("Battery read error:", e)
            return 0

    def _update_theme_colors(self):
        """
        UPDATE COLORS BASED ON CURRENT THEME

        Gets colors from the theme definition and sets up:
        - Idle color (dimmed version of main color)
        - Swing color (full brightness main color)
        - Hit color (clash flash color)
        """
        theme = SaberConfig.THEMES[self.theme_index]

        # Idle color is dimmed (divided by 4)
        self.color_idle = tuple(int(c / SaberConfig.IDLE_COLOR_DIVISOR) for c in theme["color"])
        self.color_swing = theme["color"]
        self.color_hit = theme["hit_color"]

    def cycle_theme(self):
        """Advance to next theme (wraps around)."""
        self.theme_index = (self.theme_index + 1) % len(SaberConfig.THEMES)
        self._update_theme_colors()

    def _transition_to_state(self, new_state):
        """
        VALIDATE AND EXECUTE STATE TRANSITION

        Checks if the requested transition is valid according to the
        state machine rules, then executes it.

        Returns True if transition succeeded, False if invalid.
        """
        # Already in this state? Nothing to do
        if new_state == self.mode:
            return True

        # Check if transition is valid
        valid_next_states = SaberConfig.VALID_TRANSITIONS.get(self.mode, [])
        if new_state not in valid_next_states:
            print("INVALID STATE TRANSITION: {} -> {}".format(self.mode, new_state))
            return False

        # Execute transition
        old_state = self.mode
        self.mode = new_state
        self.state_changes += 1

        if UserConfig.ENABLE_DIAGNOSTICS:
            print("State: {} -> {}".format(old_state, new_state))

        return True

    def _animate_power(self, name, duration, reverse):
        """
        ANIMATE POWER ON/OFF

        Creates the classic lightsaber ignition/retraction animation:
        - Power ON: LEDs light up from base to tip
        - Power OFF: LEDs turn off from tip to base

        Args:
            name: Sound name ("on" or "off")
            duration: How long animation takes
            reverse: True for power off (retract), False for power on (extend)
        """
        if not self.hw.strip:
            return

        # Play power sound
        self.audio.stop_audio()
        self.audio.play_audio_clip(self.theme_index, name, loop=False)
        start_time = time.monotonic()

        # Animation loop
        while True:
            # Feed watchdog to prevent reset during animation
            self._feed_watchdog()

            elapsed = time.monotonic() - start_time
            if elapsed > duration:
                break

            # Calculate progress (0.0 to 1.0)
            # sqrt makes the animation start fast and slow down (easing)
            fraction = min(elapsed / duration, 1.0)
            fraction = math.sqrt(fraction)

            # How many LEDs should be lit
            threshold = int(SaberConfig.NUM_PIXELS * fraction + 0.5)

            try:
                if not reverse:
                    # Power ON: Light LEDs from index 0 up to threshold
                    for i in range(SaberConfig.NUM_PIXELS):
                        self.hw.strip[i] = self.color_idle if i <= threshold else 0
                else:
                    # Power OFF: Light LEDs from start down to (end - threshold)
                    lit_end = SaberConfig.NUM_PIXELS - threshold
                    for i in range(SaberConfig.NUM_PIXELS):
                        self.hw.strip[i] = self.color_idle if i < lit_end else 0

                self.hw.strip.show()  # Send data to LEDs

            except Exception as e:
                print("Strip animation error:", e)
                break

        # Set final state
        try:
            if reverse:
                self.hw.strip.fill(0)  # All off
            else:
                self.hw.strip.fill(self.color_idle)  # All on (dim)
            self.hw.strip.show()
        except Exception:
            pass

        # Wait for sound to finish
        while self.audio.audio and self.audio.audio.playing:
            self._feed_watchdog()
            time.sleep(SaberConfig.AUDIO_STOP_CHECK_INTERVAL)

    def _get_touch_key(self, touch_input):
        """
        GET THE KEY FOR A TOUCH INPUT'S STATE DICTIONARY

        Maps touch input objects to their string keys in touch_state.
        """
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
        """
        CHECK TOUCH INPUT WITH DEBOUNCING AND LONG-PRESS DETECTION

        DEBOUNCING:
        Physical buttons/touch sensors can "bounce" - rapidly switching
        between on and off when touched. Without debouncing, one press
        might register as many presses. We ignore touches that happen
        too soon after the previous one.

        LONG-PRESS:
        A "long press" is holding the button for 1+ seconds.
        This triggers different functionality than a quick tap.

        Returns True if this is a valid touch event (not long-press).
        """
        if not touch_input:
            return False

        # Get state dictionary for this input
        if touch_key is None:
            touch_key = self._get_touch_key(touch_input)
        if touch_key is None or touch_key not in self.touch_state:
            return False

        state = self.touch_state[touch_key]

        try:
            if touch_input.value:  # Currently being touched
                now = time.monotonic()

                # Record start of press if this is a new touch
                if state['press_start'] == 0:
                    state['press_start'] = now

                # Check if this qualifies as a long press
                press_duration = now - state['press_start']
                if press_duration >= UserConfig.LONG_PRESS_TIME and not state['is_long_press']:
                    state['is_long_press'] = True
                    return False  # Don't also trigger as normal press

                # Normal debounced press check
                if now - state['last_time'] >= UserConfig.TOUCH_DEBOUNCE_TIME:
                    state['last_time'] = now
                    return True
            else:
                # Not touching - reset state
                state['press_start'] = 0
                state['is_long_press'] = False

        except Exception as e:
            print("Touch read error:", e)

        return False

    def _check_long_press(self, touch_input, touch_key=None):
        """Check if current touch is a long press."""
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
        """
        WAIT FOR TOUCH TO BE RELEASED

        Blocking wait - pauses until finger is lifted.
        Feeds watchdog during wait to prevent reset.
        """
        if not touch_input:
            return

        if touch_key is None:
            touch_key = self._get_touch_key(touch_input)

        try:
            while touch_input.value:
                self._feed_watchdog()  # Don't let watchdog timeout
                time.sleep(UserConfig.TOUCH_DEBOUNCE_TIME)
        except Exception:
            pass

        # Reset state on release
        if touch_key and touch_key in self.touch_state:
            self.touch_state[touch_key]['press_start'] = 0
            self.touch_state[touch_key]['is_long_press'] = False

    def _handle_battery_touch(self):
        """
        HANDLE A3/A4 TOUCH INPUTS

        A3/A4 buttons have dual functions:
        - Long press A3: Increase volume
        - Long press A4: Decrease volume
        - Quick tap: Show battery status
        """
        # Long press A3 = volume up
        if self._check_long_press(self.hw.touch_batt_a3, 'a3'):
            new_vol = self.audio.increase_volume()
            PersistentSettings.save_volume(new_vol)
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a3, 'a3')
            return True

        # Long press A4 = volume down
        if self._check_long_press(self.hw.touch_batt_a4, 'a4'):
            new_vol = self.audio.decrease_volume()
            PersistentSettings.save_volume(new_vol)
            self.display.show_volume_status(self.audio.volume)
            self._wait_for_touch_release(self.hw.touch_batt_a4, 'a4')
            return True

        # Quick tap = show battery
        if self._check_touch_debounced(self.hw.touch_batt_a3, 'a3') or \
           self._check_touch_debounced(self.hw.touch_batt_a4, 'a4'):
            self.display.show_battery_status()
            self._wait_for_touch_release(self.hw.touch_batt_a3, 'a3')
            self._wait_for_touch_release(self.hw.touch_batt_a4, 'a4')
            return True

        return False

    def _handle_theme_switch(self):
        """
        HANDLE LEFT BUTTON (THEME SWITCH)

        - Long press: Cycle through volume presets
        - Quick tap when OFF: Change theme
        - Quick tap when ON: Turn off, then change theme
        """
        # Long press = cycle volume presets
        if self._check_long_press(self.hw.touch_left, 'left'):
            preset_vol = self.audio.cycle_volume_preset()
            PersistentSettings.save_volume(preset_vol)
            self.display.show_volume_status(preset_vol)
            self._wait_for_touch_release(self.hw.touch_left, 'left')
            return True

        # Quick tap = theme switch
        if not self._check_touch_debounced(self.hw.touch_left, 'left'):
            return False

        if self.mode == SaberConfig.STATE_OFF:
            # Simply switch theme
            old_theme = self.theme_index
            self.cycle_theme()
            PersistentSettings.save_theme(self.theme_index)
            self.audio.play_audio_clip(self.theme_index, "switch")
            print("Theme: {} -> {}".format(old_theme, self.theme_index))
            self.display.show_image(self.theme_index, "logo")
            self.event_start_time = time.monotonic()
        else:
            # Currently on - turn off first, then switch
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
            self.audio.play_audio_clip(self.theme_index, "switch")
            self.display.show_image(self.theme_index, "logo")
            self.event_start_time = time.monotonic()

        self._wait_for_touch_release(self.hw.touch_left, 'left')
        return True

    def _handle_power_toggle(self):
        """
        HANDLE RIGHT BUTTON (POWER ON/OFF)

        Quick tap toggles power state:
        - If OFF: Power on (ignite blade)
        - If ON: Power off (retract blade)
        """
        if not self._check_touch_debounced(self.hw.touch_right, 'right'):
            return False

        if self.mode == SaberConfig.STATE_OFF:
            # POWER ON
            print("POWER ON - theme {}".format(self.theme_index))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)
            self._animate_power("on", duration=SaberConfig.POWER_ON_DURATION, reverse=False)
            self.audio.play_audio_clip(self.theme_index, "idle", loop=True)
            self._transition_to_state(SaberConfig.STATE_IDLE)
            self.event_start_time = time.monotonic()
        else:
            # POWER OFF
            print("POWER OFF - theme {}".format(self.theme_index))
            self._transition_to_state(SaberConfig.STATE_TRANSITION)

            # Fade out idle hum
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
        """
        READ ACCELERATION FROM THE MOTION SENSOR

        The accelerometer measures acceleration in 3 axes (X, Y, Z).
        We calculate the "magnitude squared" to determine total motion.

        WHY MAGNITUDE SQUARED?
        To get actual magnitude, we'd need sqrt(x² + y² + z²).
        Square root is slow! By comparing squared values, we skip the sqrt.
        Just need to also square our thresholds for comparison.

        Returns: Tuple of (magnitude_squared, x, y, z) or None on error
        """
        if not self.accel_enabled or not self.hw.accel:
            return None

        try:
            # Read acceleration in m/s² for each axis
            accel_x, accel_y, accel_z = self.hw.accel.acceleration

            # Calculate magnitude squared
            accel_magnitude_sq = accel_x**2 + accel_y**2 + accel_z**2

            # Successful read - reset error counter
            self.accel_error_count = 0

            return (accel_magnitude_sq, accel_x, accel_y, accel_z)

        except Exception as e:
            # Track errors
            self.accel_error_count += 1

            if self.accel_error_count >= UserConfig.MAX_ACCEL_ERRORS:
                # Too many errors - disable accelerometer
                print("Accelerometer disabled after {} errors".format(self.accel_error_count))
                self.accel_enabled = False
                self.accel_disabled_time = time.monotonic()
            else:
                # Log occasional errors
                if self.accel_error_count % 5 == 0:
                    print("Accel read error {} of {}: {}".format(
                        self.accel_error_count, UserConfig.MAX_ACCEL_ERRORS, e))

            time.sleep(UserConfig.ERROR_RECOVERY_DELAY)
            return None

    def _try_recover_accelerometer(self):
        """
        ATTEMPT TO RECOVER DISABLED ACCELEROMETER

        After too many errors, we disable the accelerometer. This method
        periodically tries to reinitialize it to see if it started working.
        """
        if self.accel_enabled:
            return True  # Already working

        now = time.monotonic()

        # Don't retry too often
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
        """
        DETECT AND RESPOND TO MOTION

        Reads accelerometer and triggers swing/hit effects based on
        movement intensity.

        SWING vs HIT:
        - Swing: Moderate acceleration (quick movement)
        - Hit: High acceleration (sudden impact/clash)
        """
        # Only detect motion when saber is on and idle
        if self.mode != SaberConfig.STATE_IDLE:
            return False

        accel_data = self._read_acceleration_magnitude()
        if accel_data is None:
            return False

        accel_magnitude_sq, accel_x, accel_y, accel_z = accel_data
        near_swing_threshold = UserConfig.NEAR_SWING_RATIO * SaberConfig.SWING_THRESHOLD

        # Check for HIT (highest priority - above hit threshold)
        if accel_magnitude_sq > SaberConfig.HIT_THRESHOLD:
            print("HIT: Mag²={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                accel_magnitude_sq, accel_x, accel_y, accel_z))

            self.event_start_time = time.monotonic()
            self._transition_to_state(SaberConfig.STATE_TRANSITION)

            # Fade out idle hum
            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)

            # Play hit sound and flash hit color
            self.audio.play_audio_clip(self.theme_index, "hit")
            self.color_active = self.color_hit
            self._transition_to_state(SaberConfig.STATE_HIT)
            return True

        # Check for SWING (above swing threshold)
        elif accel_magnitude_sq > SaberConfig.SWING_THRESHOLD:
            print("SWING: Mag²={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                accel_magnitude_sq, accel_x, accel_y, accel_z))

            self.event_start_time = time.monotonic()
            self._transition_to_state(SaberConfig.STATE_TRANSITION)

            self.audio.start_fade_out()
            while not self.audio.update_fade():
                self._feed_watchdog()
                time.sleep(0.01)

            # Play swing sound and show swing color
            self.audio.play_audio_clip(self.theme_index, "swing")
            self.color_active = self.color_swing
            self._transition_to_state(SaberConfig.STATE_SWING)
            return True

        # Debug: Log when close to swing threshold
        elif accel_magnitude_sq > near_swing_threshold:
            if UserConfig.ENABLE_DIAGNOSTICS and self.loop_count % 10 == 0:
                print("ALMOST: Mag²={:.1f}, threshold={:.1f}".format(
                    accel_magnitude_sq, SaberConfig.SWING_THRESHOLD))

        return False

    def _update_swing_hit_animation(self):
        """
        UPDATE LED ANIMATION DURING SWING/HIT

        Blends between active color (swing/hit) and idle color
        to create a smooth animation effect.
        """
        if self.mode not in (SaberConfig.STATE_SWING, SaberConfig.STATE_HIT):
            return

        if self.audio.audio and self.audio.audio.playing:
            # Calculate blend ratio based on elapsed time
            elapsed = time.monotonic() - self.event_start_time

            if self.mode == SaberConfig.STATE_SWING:
                # Swing: color peaks in middle, returns to idle
                blend = abs(SaberConfig.SWING_BLEND_MIDPOINT - elapsed) * SaberConfig.SWING_BLEND_SCALE
            else:
                # Hit: quick flash fading to idle
                blend = elapsed

            self._fill_blend(self.color_active, self.color_idle, blend)
        else:
            # Sound finished - return to idle state
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
        """
        FILL LED STRIP WITH BLENDED COLOR

        Mixes two colors based on ratio (0.0 = all c1, 1.0 = all c2).
        Only updates if color changed (optimization).
        """
        if not self.hw.strip:
            return

        ratio = max(0, min(ratio, 1.0))  # Clamp to 0-1
        color = self._mix_colors(c1, c2, ratio)

        # Only update if color changed
        if color != self.last_color:
            try:
                self.hw.strip.fill(color)
                self.hw.strip.show()
                self.last_color = color
            except Exception as e:
                print("Strip blend error:", e)

    def _mix_colors(self, color1, color2, w2):
        """
        MIX TWO RGB COLORS

        Linear interpolation between two colors.
        w2 is the weight for color2 (0.0 to 1.0).

        Args:
            color1: First RGB tuple (R, G, B)
            color2: Second RGB tuple (R, G, B)
            w2: Weight for color2 (0.0 = all color1, 1.0 = all color2)

        Returns:
            Mixed RGB tuple
        """
        w2 = max(0.0, min(w2, 1.0))  # Clamp
        w1 = 1.0 - w2

        return (
            int(color1[0] * w1 + color2[0] * w2),  # Red
            int(color1[1] * w1 + color2[1] * w2),  # Green
            int(color1[2] * w1 + color2[2] * w2),  # Blue (BUG FIX: was color2[1])
        )

    def _update_strip_brightness(self):
        """
        ADJUST LED STRIP BRIGHTNESS BASED ON STATE

        Dim when idle, brighter during action.
        """
        if not self.hw.strip:
            return

        try:
            target = UserConfig.NEOPIXEL_IDLE_BRIGHTNESS if \
                self.mode == SaberConfig.STATE_IDLE else \
                UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS

            if self.hw.strip.brightness != target:
                self.hw.strip.brightness = target

        except Exception as e:
            print("Brightness update error:", e)

    def _periodic_maintenance(self):
        """
        RUN PERIODIC MAINTENANCE TASKS

        Called each loop iteration to handle background tasks:
        - Memory cleanup (garbage collection)
        - Battery monitoring and warnings
        - Accelerometer recovery attempts
        """
        now = time.monotonic()

        # CRITICAL MEMORY CHECK
        # If memory is very low, force immediate garbage collection
        try:
            mem_free = gc.mem_free()
            if mem_free < UserConfig.CRITICAL_MEMORY_THRESHOLD:
                gc.collect()
                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("CRITICAL GC: {} -> {} bytes free".format(mem_free, gc.mem_free()))
        except Exception:
            pass

        # REGULAR GARBAGE COLLECTION (when idle)
        if self.mode in (SaberConfig.STATE_OFF, SaberConfig.STATE_IDLE):
            if now - self.last_gc_time > UserConfig.GC_INTERVAL:
                gc.collect()
                self.last_gc_time = now

                if UserConfig.ENABLE_DIAGNOSTICS:
                    print("GC: {} bytes free".format(gc.mem_free()))

        # BATTERY MONITORING
        if now - self.last_battery_check > UserConfig.BATTERY_CHECK_INTERVAL:
            battery = self._get_battery_percentage()
            self.last_battery_check = now

            if UserConfig.ENABLE_DIAGNOSTICS:
                print("Battery: {}".format(battery))

            # Battery warnings (only when on battery, not too frequently)
            if battery != "USB" and isinstance(battery, int):
                if battery <= UserConfig.BATTERY_CRITICAL_THRESHOLD:
                    if now - self.last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_critical_warning()
                        self.last_battery_warning = now
                elif battery <= UserConfig.BATTERY_WARNING_THRESHOLD:
                    if now - self.last_battery_warning > UserConfig.BATTERY_WARNING_INTERVAL:
                        self._battery_low_warning()
                        self.last_battery_warning = now

        # ACCELEROMETER RECOVERY
        if not self.accel_enabled:
            self._try_recover_accelerometer()

    def _battery_low_warning(self):
        """
        VISUAL WARNING FOR LOW BATTERY

        Flashes yellow twice to alert user battery is getting low.
        Only flashes when saber is off (don't interrupt gameplay).
        """
        print("WARNING: Low battery!")
        if self.hw.strip and self.mode == SaberConfig.STATE_OFF:
            try:
                for _ in range(2):
                    self.hw.strip.fill((255, 255, 0))  # Yellow flash
                    self.hw.strip.show()
                    time.sleep(0.15)
                    self.hw.strip.fill(0)
                    self.hw.strip.show()
                    time.sleep(0.15)
            except Exception:
                pass

    def _battery_critical_warning(self):
        """
        VISUAL WARNING FOR CRITICAL BATTERY

        Flashes red three times - battery nearly dead!
        """
        print("CRITICAL: Battery very low!")
        if self.hw.strip and self.mode == SaberConfig.STATE_OFF:
            try:
                for _ in range(3):
                    self.hw.strip.fill((255, 0, 0))  # Red flash
                    self.hw.strip.show()
                    time.sleep(0.1)
                    self.hw.strip.fill(0)
                    self.hw.strip.show()
                    time.sleep(0.1)
            except Exception:
                pass

    def run(self):
        """
        MAIN EVENT LOOP

        This is the heart of the program. It runs forever (until interrupted
        or crash), continuously checking inputs and updating outputs.

        LOOP STRUCTURE:
        1. Feed watchdog (prove we're still running)
        2. Update audio fades
        3. Check touch inputs (battery, theme, power)
        4. Check motion sensor
        5. Update LED animations
        6. Update display
        7. Run maintenance tasks
        8. Sleep briefly (control loop speed)
        """
        print("=== SABER READY ===")
        print("Volume Controls:")
        print("  - Long press A3: Increase volume")
        print("  - Long press A4: Decrease volume")
        print("  - Long press LEFT: Cycle volume presets")

        if UserConfig.ENABLE_PERSISTENT_SETTINGS:
            print("Settings: Persistent (saved across reboots)")
        if self.watchdog is not None:
            print("Watchdog: Enabled ({}s timeout)".format(UserConfig.WATCHDOG_TIMEOUT))
        print()

        try:
            # INFINITE MAIN LOOP
            while True:
                self.loop_count += 1

                # STEP 1: Feed watchdog
                self._feed_watchdog()

                # STEP 2: Update audio state
                self.audio.update_fade()
                self.audio.update_crossfade()

                # STEP 3: Handle touch inputs
                # "continue" skips rest of loop iteration if input handled
                if self._handle_battery_touch():
                    continue
                if self._handle_theme_switch():
                    continue
                if self._handle_power_toggle():
                    continue

                # STEP 4-7: Motion, animation, display, maintenance
                self._handle_motion_detection()
                self._update_swing_hit_animation()
                self.display.update_display()
                self.audio.check_audio_done()
                self._update_strip_brightness()
                self._periodic_maintenance()

                # STEP 8: Sleep to control loop speed
                if self.mode == SaberConfig.STATE_IDLE:
                    time.sleep(UserConfig.IDLE_LOOP_DELAY)
                else:
                    time.sleep(UserConfig.ACTIVE_LOOP_DELAY)

        except KeyboardInterrupt:
            # Ctrl+C pressed - graceful shutdown
            print("\nShutdown requested...")
            self.cleanup()

        except MemoryError as e:
            # Out of memory - try to recover
            print("\nMEMORY ERROR:", e)
            gc.collect()
            print("Attempting recovery... {} bytes free".format(gc.mem_free()))
            # Don't re-raise - try to continue

        except Exception as e:
            # Unexpected error - cleanup and crash
            print("\nFATAL ERROR:", e)
            self.cleanup()
            raise

    def cleanup(self):
        """
        CLEAN UP ALL RESOURCES

        Called on shutdown. Releases all hardware resources gracefully.
        """
        print("Cleaning up...")

        # Disable watchdog (prevent reset during cleanup)
        if self.watchdog is not None:
            try:
                self.watchdog.mode = None
                print("  Watchdog disabled")
            except Exception:
                pass

        # Clean up sub-components
        try:
            self.audio.cleanup()
            self.display.cleanup()
            self.hw.cleanup()
            print("Cleanup complete.")
        except Exception as e:
            print("Cleanup error:", e)


# =============================================================================
# SECTION 8: PROGRAM ENTRY POINT
# =============================================================================
# This is where the program actually starts executing.
# =============================================================================

def main():
    """
    MAIN ENTRY POINT

    Creates the controller and starts the main loop.
    Handles any fatal errors with cleanup.
    """
    controller = None
    try:
        controller = SaberController()
        controller.run()
    except Exception as e:
        print("\nFATAL ERROR:", e)
        if controller:
            controller.cleanup()
        raise  # Re-raise to show full error traceback


# =============================================================================
# PYTHON STANDARD ENTRY POINT CHECK
# =============================================================================
# This "if __name__ == '__main__'" pattern is a Python convention.
# It allows the file to be:
# 1. Run directly (name == '__main__') -> executes main()
# 2. Imported as a module (name == module name) -> doesn't auto-execute
#
# For CircuitPython on a microcontroller, code.py always runs directly,
# but including this pattern is good practice and allows testing on PC.
# =============================================================================

if __name__ == "__main__":
    main()
