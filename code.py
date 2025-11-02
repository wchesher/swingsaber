"""
John Park & William Chesher
Lightsaber Code – Version 2.0
© 2025
"""

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

# -----------------------------------------------------------------------------
# (1) USER CONFIG FOR POWER SAVINGS
# -----------------------------------------------------------------------------
class UserConfig:
    DISPLAY_BRIGHTNESS = 0.3
    DISPLAY_BRIGHTNESS_SAVER = 0.1
    DISPLAY_TIMEOUT_NORMAL = 2.0
    DISPLAY_TIMEOUT_SAVER = 1.0
    NEOPIXEL_IDLE_BRIGHTNESS = 0.05
    NEOPIXEL_ACTIVE_BRIGHTNESS = 0.3
    IDLE_LOOP_DELAY = 0.05
    ACTIVE_LOOP_DELAY = 0.01
    STOP_AUDIO_WHEN_IDLE = True
    NEAR_SWING_RATIO = 0.8  # Movement "just short" of swing threshold (80% by default)

# -----------------------------------------------------------------------------
# (2) SABER CONFIG
# -----------------------------------------------------------------------------
class SaberConfig:
    CAP_PIN = board.CAP_PIN
    SPEAKER_ENABLE_PIN = board.SPEAKER_ENABLE
    VOLTAGE_MONITOR_PIN = board.VOLTAGE_MONITOR

    NUM_PIXELS = 30
    SWING_THRESHOLD = 140
    HIT_THRESHOLD = 220

    STATE_OFF = 0
    STATE_IDLE = 1
    STATE_SWING = 2
    STATE_HIT = 3
    STATE_TRANSITION = 4

    DISPLAY_TIMEOUT_SAVER_ON = UserConfig.DISPLAY_TIMEOUT_SAVER
    DISPLAY_TIMEOUT_SAVER_OFF = UserConfig.DISPLAY_TIMEOUT_NORMAL
    IMAGE_DISPLAY_DURATION_SAVER_ON = 1.5
    IMAGE_DISPLAY_DURATION_SAVER_OFF = 3.0

    THEMES = [
        {"name": "jedi",       "color": (0, 0, 255),   "hit_color": (255, 255, 255)},
        {"name": "powerpuff",  "color": (255, 0, 255), "hit_color": (0, 200, 255)},
        {"name": "ricknmorty", "color": (0, 255, 0),   "hit_color": (255, 0, 0)},
        {"name": "spongebob",  "color": (255, 255, 0), "hit_color": (255, 255, 255)},
    ]

# -----------------------------------------------------------------------------
# (3) HARDWARE SETUP
# -----------------------------------------------------------------------------
class SaberHardware:
    def __init__(self):
        print("Initializing Saber Hardware...")
        self.cap_pin = DigitalInOut(SaberConfig.CAP_PIN)
        self.cap_pin.switch_to_output(value=False)

        self.speaker_enable = DigitalInOut(SaberConfig.SPEAKER_ENABLE_PIN)
        self.speaker_enable.switch_to_output(value=True)

        self.battery_voltage = analogio.AnalogIn(SaberConfig.VOLTAGE_MONITOR_PIN)
        self.strip = self._init_strip()

        self.touch_left = None
        self.touch_right = None
        self.touch_batt_a3 = None
        self.touch_batt_a4 = None
        self._init_touch()

        self.accel = self._init_accel()
        print("Hardware init complete.\n")

    def _init_strip(self):
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
            return strip
        except Exception as e:
            print("  NeoPixel error:", e)
            return None

    def _init_touch(self):
        try:
            self.touch_left = touchio.TouchIn(board.TOUCH1)
            self.touch_right = touchio.TouchIn(board.TOUCH4)
            self.touch_batt_a3 = touchio.TouchIn(board.A3)
            self.touch_batt_a4 = touchio.TouchIn(board.A4)
            print("  Touch inputs OK.")
        except Exception as e:
            print("  Touch error:", e)

    def _init_accel(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            accel = adafruit_msa3xx.MSA311(i2c)
            print("  Accelerometer OK.")
            return accel
        except Exception as e:
            print("  Accel error:", e)
            return None

# -----------------------------------------------------------------------------
# (4) AUDIO MANAGER
# -----------------------------------------------------------------------------
class AudioManager:
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

    def _create_silence_sample(self):
        try:
            silent_samples = array.array("h", [0] * 1024)
            return audiocore.RawSample(silent_samples)
        except Exception as e:
            print("Error creating silence sample:", e)
            return None

    def play_audio_clip(self, theme_index, name, loop=False):
        if not self.audio:
            return
        gc.collect()
        if self.audio.playing:
            self.audio.stop()

        filename = f"sounds/{theme_index}{name}.wav"
        try:
            self.current_wave_file = open(filename, "rb")
            self.current_wav = audiocore.WaveFile(self.current_wave_file)
            self.audio.play(self.current_wav, loop=loop)
        except OSError:
            pass

    def stop_audio(self):
        if self.audio and self.audio.playing:
            self.audio.stop()

    def check_audio_done(self):
        if self.audio and not self.audio.playing and self.current_wave_file is not None:
            self.current_wave_file.close()
            self.current_wave_file = None

    def fade_out_and_stop_nonblocking(self, target_duration=0.5):
        start = time.monotonic()
        while time.monotonic() - start < target_duration:
            time.sleep(0.03)
        self.stop_audio()
        if self.current_wave_file is not None:
            self.current_wave_file.close()
            self.current_wave_file = None

        if (not UserConfig.STOP_AUDIO_WHEN_IDLE) and self.silence_sample and self.audio:
            self.audio.play(self.silence_sample, loop=True)

# -----------------------------------------------------------------------------
# (5) DISPLAY MANAGER (Minimal prints)
# -----------------------------------------------------------------------------
class SaberDisplay:
    def __init__(self, battery_voltage_ref):
        self.main_group = displayio.Group()
        board.DISPLAY.auto_refresh = True
        board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS
        self.image_cache = {}

        self.display_start_time = 0
        self.display_active = False
        self.display_timeout = SaberConfig.DISPLAY_TIMEOUT_SAVER_OFF
        self.get_battery_voltage_pct = battery_voltage_ref
        self.image_display_duration = SaberConfig.IMAGE_DISPLAY_DURATION_SAVER_OFF
        self.turn_off_screen()

    def turn_off_screen(self):
        try:
            board.DISPLAY.brightness = 0
        except Exception:
            pass

    def update_display_timeout(self, timeout):
        self.display_timeout = timeout

    def update_image_display_duration(self, duration):
        self.image_display_duration = duration

    def update_power_saver_settings(self, saver_on):
        if saver_on:
            self.update_display_timeout(UserConfig.DISPLAY_TIMEOUT_SAVER)
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS_SAVER
        else:
            self.update_display_timeout(UserConfig.DISPLAY_TIMEOUT_NORMAL)
            board.DISPLAY.brightness = UserConfig.DISPLAY_BRIGHTNESS

    def show_battery_status(self):
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

        if battery_percent != "USB":
            battery_bar_width = battery_percent
            battery_group = displayio.Group()
            bg_palette = displayio.Palette(1)
            bg_palette[0] = 0x444444
            bat_bg_bitmap = displayio.Bitmap(100, 14, 1)
            bat_bg_bitmap.fill(0)
            bg_tile2 = displayio.TileGrid(bat_bg_bitmap, pixel_shader=bg_palette, x=14, y=46)
            battery_group.append(bg_tile2)

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

    def _load_image(self, theme_index, image_type="logo"):
        cache_key = "{}{}".format(theme_index, image_type)
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]
        filename = "/images/{}{}.bmp".format(theme_index, image_type)
        try:
            bitmap = displayio.OnDiskBitmap(filename)
            tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
            self.image_cache[cache_key] = tile_grid
            return tile_grid
        except Exception:
            return None

    def show_image(self, theme_index, image_type="logo", duration=None):
        if duration is None:
            duration = self.image_display_duration
            print("\n" * 40)  # Add 40 blank lines before displaying image

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

    def update_display(self):
        if self.display_active and (time.monotonic() - self.display_start_time) > self.display_timeout:
            self.turn_off_screen()
            self.display_active = False

# -----------------------------------------------------------------------------
# (6) SABER CONTROLLER (Accel print: swing/hit/near swing only)
# -----------------------------------------------------------------------------
class SaberController:
    def __init__(self):
        print("Booting SaberController...")
        self.hw = SaberHardware()
        self.display = SaberDisplay(self._get_battery_percentage)
        self.audio = AudioManager()

        self.power_saver_mode = False
        self.cpu_loop_delay = 0.01
        self.mode = SaberConfig.STATE_OFF
        self.theme_index = 0

        self.color_idle = (0, 0, 0)
        self.color_swing = (0, 0, 0)
        self.color_hit = (0, 0, 0)
        self.color_active = (0, 0, 0)

        self.event_start_time = 0

        self._update_theme_colors()
        self._apply_power_mode()
        self.display.turn_off_screen()
        print("SaberController init complete.\n")

    def _apply_power_mode(self):
        if self.power_saver_mode:
            self.display.update_power_saver_settings(True)
            self.cpu_loop_delay = 0.03
        else:
            self.display.update_power_saver_settings(False)
            self.cpu_loop_delay = 0.01

    def toggle_power_mode(self):
        self.power_saver_mode = not self.power_saver_mode
        self._apply_power_mode()

    def _get_battery_percentage(self):
        if supervisor.runtime.usb_connected:
            return "USB"
        sum_val = 0
        for _ in range(10):
            sum_val += self.hw.battery_voltage.value
            time.sleep(0.01)
        avg_val = sum_val / 10
        voltage = (avg_val / 65535) * self.hw.battery_voltage.reference_voltage * 2
        percent = ((voltage - 3.3) / (4.2 - 3.3)) * 100
        return min(max(int(percent), 0), 100)

    def _update_theme_colors(self):
        t = SaberConfig.THEMES[self.theme_index]
        self.color_idle = tuple(int(c / 4) for c in t["color"])
        self.color_swing = t["color"]
        self.color_hit = t["hit_color"]

    def cycle_theme(self):
        self.theme_index = (self.theme_index + 1) % len(SaberConfig.THEMES)
        self._update_theme_colors()

    def _animate_power(self, name, duration, reverse):
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

            if not reverse:
                for i in range(SaberConfig.NUM_PIXELS):
                    self.hw.strip[i] = self.color_idle if i <= threshold else 0
            else:
                lit_end = SaberConfig.NUM_PIXELS - threshold
                for i in range(SaberConfig.NUM_PIXELS):
                    self.hw.strip[i] = self.color_idle if i < lit_end else 0
            self.hw.strip.show()

        if reverse:
            self.hw.strip.fill(0)
        else:
            self.hw.strip.fill(self.color_idle)
        self.hw.strip.show()

        while self.audio.audio and self.audio.audio.playing:
            time.sleep(0.03)

    def run(self):
        while True:
            now = time.monotonic()

            # A3 => battery
            if self.hw.touch_batt_a3 and self.hw.touch_batt_a3.value:
                self.display.show_battery_status()
                while self.hw.touch_batt_a3.value:
                    time.sleep(0.02)

            # A4 => battery
            if self.hw.touch_batt_a4 and self.hw.touch_batt_a4.value:
                self.display.show_battery_status()
                while self.hw.touch_batt_a4.value:
                    time.sleep(0.02)

            # Left => cycle theme
            if self.hw.touch_left and self.hw.touch_left.value:
                if self.mode == SaberConfig.STATE_OFF:
                    old_theme = self.theme_index
                    self.cycle_theme()
                    self.audio.play_audio_clip(self.theme_index, "switch")
                    print("Switched theme from {} to {}.".format(old_theme, self.theme_index))
                    self.display.show_image(self.theme_index, "logo")
                    self.event_start_time = time.monotonic()
                else:
                    self.audio.fade_out_and_stop_nonblocking(0.5)
                    self._animate_power("off", duration=1.15, reverse=True)
                    self.mode = SaberConfig.STATE_OFF
                    self.cycle_theme()
                    print("Switched theme while on. Now theme={}".format(self.theme_index))
                    self.audio.play_audio_clip(self.theme_index, "switch")
                    self.display.show_image(self.theme_index, "logo")
                    self.event_start_time = time.monotonic()

                while self.hw.touch_left.value:
                    time.sleep(0.02)

            # Right => on/off
            if self.hw.touch_right and self.hw.touch_right.value:
                if self.mode == SaberConfig.STATE_OFF:
                    print("Powering ON - theme {}".format(self.theme_index))
                    self.mode = SaberConfig.STATE_TRANSITION
                    self._animate_power("on", duration=1.7, reverse=False)
                    self.audio.play_audio_clip(self.theme_index, "idle", loop=True)
                    self.mode = SaberConfig.STATE_IDLE
                    self.event_start_time = time.monotonic()
                else:
                    print("Powering OFF - theme {}".format(self.theme_index))
                    self.mode = SaberConfig.STATE_TRANSITION
                    self.audio.fade_out_and_stop_nonblocking(0.5)
                    self._animate_power("off", duration=1.15, reverse=True)
                    self.mode = SaberConfig.STATE_OFF
                    self.event_start_time = time.monotonic()

                while self.hw.touch_right.value:
                    time.sleep(0.02)

            # ACCEL DETECTION: we only print if near, swing, or hit
            if self.mode == SaberConfig.STATE_IDLE and self.hw.accel is not None:
                try:
                    accel_x, accel_y, accel_z = self.hw.accel.acceleration
                    accel_magnitude = accel_x**2 + accel_z**2

                    # "Near swing" threshold e.g. 0.8 * SWING_THRESHOLD
                    near_swing_threshold = UserConfig.NEAR_SWING_RATIO * SaberConfig.SWING_THRESHOLD

                    if accel_magnitude > SaberConfig.HIT_THRESHOLD:
                        print("HIT: Magnitude={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                            accel_magnitude, accel_x, accel_y, accel_z))
                        self.event_start_time = time.monotonic()
                        self.mode = SaberConfig.STATE_TRANSITION
                        self.audio.fade_out_and_stop_nonblocking(0.5)
                        self.audio.play_audio_clip(self.theme_index, "hit")
                        self.color_active = self.color_hit
                        self.mode = SaberConfig.STATE_HIT

                    elif accel_magnitude > SaberConfig.SWING_THRESHOLD:
                        print("SWING: Magnitude={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                            accel_magnitude, accel_x, accel_y, accel_z))
                        self.event_start_time = time.monotonic()
                        self.mode = SaberConfig.STATE_TRANSITION
                        self.audio.fade_out_and_stop_nonblocking(0.5)
                        self.audio.play_audio_clip(self.theme_index, "swing")
                        self.color_active = self.color_swing
                        self.mode = SaberConfig.STATE_SWING

                    # Movement “just short” of SWING
                    elif accel_magnitude > near_swing_threshold:
                        print("ALMOST SWING: Mag={:.1f}, threshold={:.1f}, (x={:.1f}, y={:.1f}, z={:.1f})".format(
                            accel_magnitude, SaberConfig.SWING_THRESHOLD, accel_x, accel_y, accel_z))

                except Exception as e:
                    pass

            # Swing/hit color update
            if self.mode in (SaberConfig.STATE_SWING, SaberConfig.STATE_HIT):
                if self.audio.audio and self.audio.audio.playing:
                    blend = time.monotonic() - self.event_start_time
                    if self.mode == SaberConfig.STATE_SWING:
                        blend = abs(0.5 - blend) * 2.0
                    self._fill_blend(self.color_active, self.color_idle, blend)
                else:
                    self.audio.play_audio_clip(self.theme_index, "idle", loop=True)
                    if self.hw.strip:
                        self.hw.strip.fill(self.color_idle)
                        self.hw.strip.show()
                    self.mode = SaberConfig.STATE_IDLE

            # Update display & check audio
            self.display.update_display()
            self.audio.check_audio_done()

            # Dim or bright NeoPixels depending on IDLE vs. active
            if self.hw.strip:
                if self.mode == SaberConfig.STATE_IDLE:
                    self.hw.strip.brightness = UserConfig.NEOPIXEL_IDLE_BRIGHTNESS
                else:
                    self.hw.strip.brightness = UserConfig.NEOPIXEL_ACTIVE_BRIGHTNESS

            # Larger loop delay if idle => save battery
            if self.mode == SaberConfig.STATE_IDLE:
                time.sleep(UserConfig.IDLE_LOOP_DELAY)
            else:
                time.sleep(UserConfig.ACTIVE_LOOP_DELAY)

    def _fill_blend(self, c1, c2, ratio):
        if not self.hw.strip:
            return
        ratio = max(0, min(ratio, 1.0))
        color = self._mix_colors(c1, c2, ratio)
        self.hw.strip.fill(color)
        self.hw.strip.show()

    def _mix_colors(self, color1, color2, w2):
        w2 = max(0, min(w2, 1.0))
        w1 = 1.0 - w2
        return (
            int(color1[0] * w1 + color2[0] * w2),
            int(color1[1] * w1 + color2[1] * w2),
            int(color1[2] * w1 + color2[2] * w2),
        )

# -----------------------------------------------------------------------------
# (7) ENTRY POINT
# -----------------------------------------------------------------------------
def main():
    controller = SaberController()
    controller.run()

main()
