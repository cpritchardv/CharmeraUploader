import time

from charmera_uploader.config import LedConfig
from charmera_uploader.leds import StatusLeds


def make_leds() -> StatusLeds:
    return StatusLeds(
        LedConfig(line=0),
        LedConfig(line=1),
        simulate=True,
        complete_hold_seconds=0.05,
    )


def test_state_transitions_do_not_raise():
    leds = make_leds()
    try:
        leds.start_processing()
        leds.success()
        leds.start_processing()
        leds.error()
        leds.reset()
    finally:
        leds.close()


def test_success_auto_clears_after_hold_time():
    leds = make_leds()
    try:
        leds.success()
        time.sleep(0.2)
        # Nothing to assert directly in simulate mode beyond "it didn't crash"
        # and the background timer thread cleaned itself up.
        assert leds._hold_timer is None or not leds._hold_timer.is_alive()
    finally:
        leds.close()
