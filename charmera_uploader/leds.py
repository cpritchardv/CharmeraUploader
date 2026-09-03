"""Status indication using the Orange Pi's onboard status LED.

The Zero 2W has two onboard LEDs: a red power LED that's hardware-driven
(always on once powered, not controllable from software) and a green
status LED exposed to Linux through the LED class at
/sys/class/leds/<name>/. Since only one LED is actually controllable,
"processing" and "complete" are encoded as different patterns on that
single LED rather than as two separate LEDs:

  idle       -> off
  processing -> slow blink
  success    -> solid on (held for a while, then off)
  error      -> fast blink

The exact sysfs name varies by board revision/kernel - find yours with:

    ls /sys/class/leds/

and set it as `led_name` in config.yaml (commonly `green_led`, sometimes
something like `orangepi:green:status`).

Set `leds_simulate: true` in config to run without touching any LED at
all - state changes are just logged. Useful for developing off-device.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

LEDS_ROOT = Path("/sys/class/leds")


class SysfsLed:
    """A single LED driven through the Linux LED class (/sys/class/leds/<name>)."""

    def __init__(self, name: str, simulate: bool = False):
        self.name = name
        self.simulate = simulate
        self._path = LEDS_ROOT / name
        self._max_brightness = 1
        self._blink_stop: threading.Event | None = None
        self._blink_thread: threading.Thread | None = None

        if not self.simulate:
            if not self._path.is_dir():
                available = (
                    sorted(p.name for p in LEDS_ROOT.iterdir()) if LEDS_ROOT.is_dir() else []
                )
                raise FileNotFoundError(
                    f"No LED at {self._path}. Available: {available or '(none found)'}. "
                    "Run `ls /sys/class/leds/` on the Pi and set led_name in config.yaml "
                    "to the right one, or set leds_simulate: true to test without hardware."
                )
            self._max_brightness = int((self._path / "max_brightness").read_text().strip())
            try:
                # Hand control to us instead of whatever trigger (heartbeat,
                # mmc activity, ...) the board ships with by default.
                (self._path / "trigger").write_text("none")
            except OSError:
                logger.warning(
                    "Could not disable the default trigger on LED %r (need root?)", name
                )

    def _write_brightness(self, on: bool) -> None:
        value = (self._max_brightness if on else 0) if not self.simulate else int(on)
        if self.simulate:
            logger.debug("LED[%s] -> %s (simulated)", self.name, "ON" if on else "OFF")
            return
        (self._path / "brightness").write_text(str(value))

    def on(self) -> None:
        self.stop_blink()
        self._write_brightness(True)

    def off(self) -> None:
        self.stop_blink()
        self._write_brightness(False)

    def blink(self, interval: float) -> None:
        """Blink in the background until stop_blink()/on()/off() is called."""
        self.stop_blink()
        self._blink_stop = threading.Event()
        stop_event = self._blink_stop

        def _run() -> None:
            state = False
            while not stop_event.is_set():
                self._write_brightness(state)
                state = not state
                stop_event.wait(interval)
            self._write_brightness(False)

        self._blink_thread = threading.Thread(target=_run, daemon=True)
        self._blink_thread.start()

    def stop_blink(self) -> None:
        if self._blink_stop is not None:
            self._blink_stop.set()
            if self._blink_thread is not None:
                self._blink_thread.join(timeout=1)
            self._blink_stop = None
            self._blink_thread = None

    def close(self) -> None:
        self.stop_blink()


class StatusLed:
    """The processing/complete/error status states, encoded on one LED."""

    def __init__(self, led_name: str, simulate: bool = False, success_hold_seconds: float = 20.0):
        self.led = SysfsLed(led_name, simulate=simulate)
        self.success_hold_seconds = success_hold_seconds
        self._hold_timer: threading.Timer | None = None
        self.reset()

    def reset(self) -> None:
        """Idle state: LED off."""
        self._cancel_hold_timer()
        self.led.off()

    def start_processing(self) -> None:
        self._cancel_hold_timer()
        self.led.blink(interval=0.5)

    def success(self) -> None:
        self._cancel_hold_timer()
        self.led.on()
        if self.success_hold_seconds > 0:
            self._hold_timer = threading.Timer(self.success_hold_seconds, self.led.off)
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def error(self) -> None:
        self._cancel_hold_timer()
        self.led.blink(interval=0.15)

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None

    def close(self) -> None:
        self._cancel_hold_timer()
        self.led.close()
