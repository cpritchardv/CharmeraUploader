"""Configuration loading for the Charmera uploader."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EXTENSIONS = [".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".avi"]


@dataclasses.dataclass
class Config:
    # Where camera partitions get mounted while we work.
    mount_base: str = "/mnt/charmera"
    # Sub-path (relative to the mounted volume) to search for photos.
    # Empty string = scan the whole volume, which is the right default for
    # the Charmera since it splits stills (DCIM/) and videos (VIDEO/) into
    # separate top-level folders.
    dcim_subpath: str = ""
    file_extensions: list[str] = dataclasses.field(default_factory=lambda: list(DEFAULT_EXTENSIONS))

    # "daily" -> one album per calendar day of the photos (by EXIF/mtime date).
    # "single" -> every photo goes into one persistent album.
    album_mode: str = "daily"
    album_title_template: str = "Charmera {date}"
    single_album_title: str = "Charmera Photos"

    # Never delete from the camera by default; only rely on the local
    # dedupe manifest. Flip this on once you trust the pipeline.
    delete_after_upload: bool = False

    manifest_db_path: str = "/var/lib/charmera-uploader/manifest.db"
    # Name of the rclone remote (from `rclone config`) pointing at a Google
    # Photos backend. Uploads run as `rclone copy <file> <remote>:album/<title>/`.
    # Using rclone's already Google-verified shared client means no Google
    # Cloud Console project, OAuth branding, or verification is needed at
    # all - just `rclone config` and a normal Google sign-in. See README.
    rclone_remote: str = "googlephotos"

    # Onboard status LED, exposed by the kernel under /sys/class/leds/<name>.
    # Run `ls /sys/class/leds/` on the Pi to find the exact name (commonly
    # "green_led"). The Zero 2W's red power LED is hardware-only and can't
    # be controlled, so this single LED encodes all states: off = idle,
    # slow blink = processing, solid on = success, fast blink = error.
    led_name: str = "green_led"
    # How long to hold the LED solid-on after a successful run.
    # 0 means "leave it on until the camera is unplugged / the next run starts".
    led_success_hold_seconds: float = 20.0
    leds_simulate: bool = False

    log_level: str = "INFO"
    log_path: str | None = "/var/log/charmera-uploader.log"

    # Only USB devices whose udev ID_BUS is "usb" are ever touched, but as
    # an extra safety net you can restrict to specific vendor:model ids
    # (e.g. ["04b0:0421"]). Empty list = accept any USB mass storage device.
    usb_id_allowlist: list[str] = dataclasses.field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
        return cls(**raw)
