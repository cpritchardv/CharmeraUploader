"""Single-color status LED control via libgpiod.

Wiring: each LED's anode (long leg) -> a current-limiting resistor
(330-470 ohm) -> a GPIO pin. Cathode (short leg) -> a GND pin on the
header. Run `gpiodetect` / `gpioinfo` on the Pi to find the correct
chip/line numbers for the physical header pins you wired up, and put
them in config.yaml - exact line numbering depends on the board's pinout
and isn't hardcoded here.

Set `leds_simulate: true` in config (or construct with simulate=True) to
run without any GPIO hardware at all - status changes are just logged.
Useful for developing off-device.
"""

from __future__ import annotations

import logging
import threading
import time

from .config import LedConfig

logger = logging.getLogger(__name__)

try:
    import gpiod
    from gpiod.line import Direction, Value
except ImportError:  # pragma: no cover - exercised only off-Pi
    gpiod = None


class Led:
    """A single GPIO-backed LED, or a simulated stand-in."""

    def __init__(self, name: str, cfg: LedConfig, simulate: bool = False):
        self.name = name
        self.cfg = cfg
        self.simulate = simulate or gpiod is None
        self._request = None
        self._blink_stop: threading.Event | None = None
        self._blink_thread: threading.Thread | None = None

        if self.simulate:
            if gpiod is None:
                logger.warning(
                    "gpiod not available - LED %r running in simulate mode", name
                )
        else:
            on_value = Value.ACTIVE if cfg.active_high else Value.INACTIVE
            off_value = Value.INACTIVE if cfg.active_high else Value.ACTIVE
            self._on_value = on_value
            self._off_value = off_value
            self._request = gpiod.request_lines(
                cfg.chip,
                consumer="charmera-uploader",
                config={cfg.line: gpiod.LineSettings(direction=Direction.OUTPUT)},
            )

    def _set(self, on: bool) -> None:
        if self.simulate:
            logger.debug("LED[%s] -> %s (simulated)", self.name, "ON" if on else "OFF")
            return
        value = self._on_value if on else self._off_value
        self._request.set_value(self.cfg.line, value)

    def on(self) -> None:
        self.stop_blink()
        self._set(True)

    def off(self) -> None:
        self.stop_blink()
        self._set(False)

    def blink(self, interval: float = 0.25) -> None:
        """Blink in the background until stop_blink()/on()/off() is called."""
        self.stop_blink()
        self._blink_stop = threading.Event()
        stop_event = self._blink_stop

        def _run() -> None:
            state = False
            while not stop_event.is_set():
                self._set(state)
                state = not state
                stop_event.wait(interval)
            self._set(False)

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
        if self._request is not None:
            self._request.release()


class StatusLeds:
    """The two-LED "processing" / "complete" status pair used by the daemon."""

    def __init__(
        self,
        processing_cfg: LedConfig,
        complete_cfg: LedConfig,
        simulate: bool = False,
        complete_hold_seconds: float = 20.0,
    ):
        self.processing = Led("processing", processing_cfg, simulate=simulate)
        self.complete = Led("complete", complete_cfg, simulate=simulate)
        self.complete_hold_seconds = complete_hold_seconds
        self._hold_timer: threading.Timer | None = None
        self.reset()

    def reset(self) -> None:
        """Idle state: both LEDs off."""
        self._cancel_hold_timer()
        self.processing.off()
        self.complete.off()

    def start_processing(self) -> None:
        self._cancel_hold_timer()
        self.complete.off()
        self.processing.on()

    def success(self) -> None:
        self.processing.off()
        self.complete.on()
        self._cancel_hold_timer()
        if self.complete_hold_seconds > 0:
            self._hold_timer = threading.Timer(self.complete_hold_seconds, self.complete.off)
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def error(self) -> None:
        self._cancel_hold_timer()
        self.complete.off()
        self.processing.blink(interval=0.15)

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None

    def close(self) -> None:
        self._cancel_hold_timer()
        self.processing.close()
        self.complete.close()
