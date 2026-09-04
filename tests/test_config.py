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


def test_load_ignores_unknown_keys_instead_of_crashing(tmp_path, capsys):
    # Deployed config files can carry stale keys from an older schema
    # version (e.g. token_path from before the rclone migration) - this
    # must not crash the whole service on startup.
    path = tmp_path / "config.yaml"
    path.write_text(
        """
        album_mode: single
        token_path: /etc/charmera-uploader/token.json
        some_future_option: true
        """
    )

    cfg = Config.load(path)

    assert cfg.album_mode == "single"
    assert not hasattr(cfg, "token_path")
    err = capsys.readouterr().err
    assert "token_path" in err
    assert "some_future_option" in err
