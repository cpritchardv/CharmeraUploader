from charmera_uploader.config import Config


def test_defaults_are_safe():
    cfg = Config()
    assert cfg.delete_after_upload is False
    assert cfg.album_mode == "daily"


def test_load_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
        album_mode: single
        single_album_title: My Charmera
        delete_after_upload: true
        led_name: status_led
        led_success_hold_seconds: 5
        """
    )

    cfg = Config.load(path)

    assert cfg.album_mode == "single"
    assert cfg.single_album_title == "My Charmera"
    assert cfg.delete_after_upload is True
    assert cfg.led_name == "status_led"
    assert cfg.led_success_hold_seconds == 5


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg == Config()
