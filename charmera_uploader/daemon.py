"""Watches for the Charmera being plugged in over USB and runs the pipeline.

Normal usage (as the systemd service) is just:

    python -m charmera_uploader.daemon --config /etc/charmera-uploader/config.yaml

For testing without touching real udev/USB hardware, point it at an
already-mounted directory instead:

    python -m charmera_uploader.daemon --config config.yaml --process-path /path/to/folder
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .camera import MountError, find_photos, mount_device, unmount_device
from .config import Config
from .leds import StatusLed
from .manifest import Manifest
from .pipeline import upload_batch
from .rclone_photos import RclonePhotosClient

logger = logging.getLogger("charmera_uploader")


def setup_logging(cfg: Config) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if cfg.log_path:
        try:
            handlers.append(logging.FileHandler(cfg.log_path))
        except OSError:
            pass  # fine, stdout (captured by journald under systemd) still works
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def process_mounted_volume(
    mount_point: Path,
    cfg: Config,
    manifest: Manifest,
    leds: StatusLed,
    delete_originals: bool,
) -> None:
    leds.start_processing()
    try:
        photos = find_photos(mount_point, cfg.dcim_subpath, cfg.file_extensions)
        logger.info("Found %d photo(s) on %s", len(photos), mount_point)
        if not photos:
            leds.success()
            return

        client = RclonePhotosClient(cfg.rclone_remote, upload_timeout_seconds=cfg.rclone_upload_timeout_seconds)
        result = upload_batch(photos, cfg, manifest, client)

        logger.info(
            "Batch done: %d uploaded, %d already uploaded, %d failed",
            len(result.uploaded), len(result.skipped_duplicate), len(result.failed),
        )

        if delete_originals:
            for photo in result.uploaded + result.skipped_duplicate:
                try:
                    photo.path.unlink()
                except OSError:
                    logger.warning("Could not delete %s from camera", photo.path)

        if result.had_failures:
            leds.error()
        else:
            leds.success()
    except Exception:
        logger.exception("Processing failed")
        leds.error()


def handle_device(device_node: str, cfg: Config, manifest: Manifest, leds: StatusLed) -> None:
    mount_point = Path(cfg.mount_base) / Path(device_node).name
    try:
        mount_device(device_node, mount_point, read_write=cfg.delete_after_upload)
    except MountError:
        logger.exception("Could not mount %s", device_node)
        leds.error()
        return

    try:
        process_mounted_volume(mount_point, cfg, manifest, leds, cfg.delete_after_upload)
    finally:
        unmount_device(mount_point)


def _device_allowed(device, cfg: Config) -> bool:
    if device.get("ID_BUS") != "usb":
        return False
    if "ID_FS_TYPE" not in device:
        # Not an actual filesystem (e.g. an extended/empty partition table
        # entry) - nothing we could mount anyway.
        return False
    if not cfg.usb_id_allowlist:
        return True
    vendor = device.get("ID_VENDOR_ID", "")
    model = device.get("ID_MODEL_ID", "")
    return f"{vendor}:{model}" in cfg.usb_id_allowlist


def run_monitor(cfg: Config) -> None:
    import pyudev

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by("block")

    manifest = Manifest(cfg.manifest_db_path)
    leds = StatusLed(
        cfg.led_name,
        simulate=cfg.leds_simulate,
        success_hold_seconds=cfg.led_success_hold_seconds,
    )
    leds.reset()

    logger.info("Watching for USB storage devices...")
    try:
        for device in iter(monitor.poll, None):
            if device.get("DEVTYPE") != "partition":
                continue
            if device.action != "add":
                if device.action == "remove":
                    leds.reset()
                continue
            if not _device_allowed(device, cfg):
                continue

            device_node = device.device_node
            if not device_node:
                continue
            logger.info("New USB volume detected: %s", device_node)
            handle_device(device_node, cfg, manifest, leds)
    finally:
        leds.close()
        manifest.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/charmera-uploader/config.yaml")
    parser.add_argument(
        "--process-path",
        help="Skip udev/mounting entirely and process an already-mounted directory once.",
    )
    args = parser.parse_args(argv)

    cfg = Config.load(args.config)
    setup_logging(cfg)

    if args.process_path:
        manifest = Manifest(cfg.manifest_db_path)
        leds = StatusLed(
            cfg.led_name,
            simulate=cfg.leds_simulate,
            success_hold_seconds=cfg.led_success_hold_seconds,
        )
        try:
            process_mounted_volume(
                Path(args.process_path), cfg, manifest, leds, cfg.delete_after_upload
            )
        finally:
            leds.close()
            manifest.close()
        return 0

    run_monitor(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
