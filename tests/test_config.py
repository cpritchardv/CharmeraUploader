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
        processing_led:
          chip: /dev/gpiochip1
          line: 5
          active_high: false
        complete_led:
          line: 6
        """
    )

    cfg = Config.load(path)

    assert cfg.album_mode == "single"
    assert cfg.single_album_title == "My Charmera"
    assert cfg.delete_after_upload is True
    assert cfg.processing_led.chip == "/dev/gpiochip1"
    assert cfg.processing_led.line == 5
    assert cfg.processing_led.active_high is False
    assert cfg.complete_led.line == 6


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg == Config()
