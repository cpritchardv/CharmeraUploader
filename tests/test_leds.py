import time

from charmera_uploader.leds import StatusLed


def make_leds() -> StatusLed:
    return StatusLed("green_led", simulate=True, success_hold_seconds=0.05)


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
