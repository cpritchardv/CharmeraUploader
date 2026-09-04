# Charmera Uploader

Plug a Kodak Charmera into an Orange Pi Zero 2W over USB and its photos
automatically get uploaded into a Google Photos album, with the Pi's
onboard status LED showing processing/complete/error and a local dedupe
manifest so you never upload the same photo twice. No extra hardware
required - just the Pi and the camera.

## How it works

1. A small daemon (`charmera_uploader.daemon`) runs at boot and watches for
   USB storage devices via udev.
2. When the camera shows up as a USB mass-storage volume, it's mounted,
   scanned for photos/videos (the whole volume by default - Charmera keeps
   stills in `DCIM/` and videos in a separate `VIDEO/` folder), and each new
   file is hashed (SHA-256).
3. New files get uploaded to Google Photos and added to an album (one album
   per calendar date by default, based on EXIF capture date). Files whose
   hash is already in the local manifest are skipped.
4. The Pi's onboard status LED shows what's happening: off = idle, slow
   blink = processing, solid on = success (held for a configurable time, or
   until the camera is unplugged), fast blink = error.
5. By default nothing is deleted from the camera - the local manifest is
   what prevents re-uploads, so it's safe to leave old photos on the card.
   Set `delete_after_upload: true` once you trust the pipeline if you'd
   rather the camera just empty itself out.

### Why local dedupe instead of asking Google what's already there?

As of Google's 2025 Photos API changes, apps can no longer read back
arbitrary library/album contents - the only usable scope for this kind of
unattended uploader is `photoslibrary.appendonly`, which can create albums
and add photos but can't list or search them. So this project keeps its own
SQLite manifest (`manifest_db_path` in config) of every file hash it has
uploaded, and of the album ID it created for each title, and treats that as
the source of truth. This also means: **don't delete `manifest.db`** unless
you're OK with previously-uploaded photos being re-uploaded if they're ever
copied back onto the camera.

## Hardware

- Orange Pi Zero 2W (2GB) running Armbian (or another Debian/Ubuntu-based
  image) with network access.
- Kodak Charmera (USB-C). It reports as a plain USB Mass Storage device
  (not MTP) with a FAT32 microSD card inside showing up as two top-level
  folders: `DCIM/` (JPEG stills) and `VIDEO/` (AVI clips) - which is why
  photo scanning defaults to the whole volume rather than just `DCIM/`.
- A USB-C to USB-C cable to connect the camera to the Pi.

That's it - status is shown on the Pi's own onboard LED, no extra wiring
needed (see below).

### Orange Pi USB port gotcha: enable host mode

The Zero 2W has **two USB-C ports, both USB 2.0**, and by default only the
one further from the board edge runs in USB host mode (able to talk to the
camera) - the other (`USB0`, near the edge) boots in peripheral/gadget
mode. **Plug the Charmera into the host-capable port** and use the other
one for power; that needs no configuration at all.

If you specifically need the camera on the near-edge `USB0` port instead
(e.g. because the other one is occupied), you have to flip it into host
mode with a device tree overlay:

```
armbian-add-overlay usb0-host
```

(or manually add `overlays=usb0-host` under `[all]` in
`/boot/armbianEnv.txt`, if your Armbian image doesn't have the
`sun50i-h616-usb0-host.dtbo` overlay pre-built, you'll need to build it
from the matching `.dts` for your kernel - see the Armbian forum thread
linked below). Reboot after changing this.

Sources: [Orange Pi Zero 2W wiki](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_Zero_2W), [Armbian forum: Orange Pi Zero 2W USB0 host mode](https://forum.armbian.com/topic/31654-orange-pi-zero-2w/page/2/), [DietPi: Enable USB0 host mode](https://dietpi.com/forum/t/orange-pi-zero-2-w-enable-usb0-host-mode/23661)

### Status via the onboard LED

The Zero 2W has two onboard LEDs: a red power LED that's hardware-driven
(always on once powered, can't be controlled from software) and a green
status LED the kernel exposes at `/sys/class/leds/<name>/`. Since only one
LED is actually controllable, this project encodes all its states on that
single LED via blink pattern rather than needing two separate LEDs:

| State | Onboard LED |
|---|---|
| idle | off |
| processing | slow blink |
| success | solid on |
| error | fast blink |

The exact sysfs name varies by board revision/kernel, so find yours on the
Pi with:

```
ls /sys/class/leds/
```

and set it as `led_name` in `config.yaml` (commonly `green_led`, sometimes
something like `orangepi:green:status`). The daemon needs root (which the
systemd service already runs as) to write to it.

If you haven't got the Pi set up yet, or want to develop off-device, set
`leds_simulate: true` to run everything else with LED state changes just
logged instead.

## Software setup

Everything here runs on the Pi itself - nothing needs installing on your
own computer.

### 1. Install on the Pi

```
git clone https://github.com/cpritchardv/CharmeraUploader.git
cd CharmeraUploader
sudo ./scripts/install.sh
```

This installs OS packages (including `rclone` - see below), copies the app
to `/opt/charmera-uploader`, creates a venv, installs Python deps, writes a
default `/etc/charmera-uploader/config.yaml` (edit it - at minimum check
`led_name` against `ls /sys/class/leds/` and consider setting
`usb_id_allowlist`), and enables/starts the `charmera-uploader` systemd
service (it won't be fully working yet - that needs step 2 below).

### 2. Connect Google Photos (via rclone - no Google Cloud Console needed)

Uploads go through [rclone](https://rclone.org/), not a hand-rolled Google
API integration. This matters: registering your *own* app with Google for
the Photos API means either re-authorizing every 7 days, or completing
full app branding (homepage, privacy policy, terms of service) and
publishing it - real requirements, not a shortcut anyone's missing. rclone
sidesteps all of that because it ships its own OAuth client that Google
already verified, shared across every rclone user. Setup is just signing
into your own Google account - no project, no branding, no verification.

1. Log into the Pi with a port forward added to your usual SSH command
   (needed for the browser sign-in step below to reach the Pi):
   ```
   ssh -L 53682:localhost:53682 root@<pi-ip-or-hostname>
   ```
2. In that same SSH session:
   ```
   rclone config
   ```
   - `n` for a new remote
   - name it exactly `googlephotos` (matches this project's default
     `rclone_remote` setting)
   - storage type: search for and pick **Google Photos**
   - client_id / client_secret: leave both **blank** (press Enter) - this
     is what makes it use rclone's pre-verified client instead of your own
   - "Edit advanced config": No
   - "Use web browser to automatically authenticate": **Yes**
3. It prints a Google sign-in URL (or opens it automatically depending on
   your terminal). Open it in a browser **on the same computer you ran
   that `ssh -L` command from** (not your phone - the tunnel only exists
   on that machine). Sign in and approve. `rclone config` finishes on its
   own once you do.
4. Confirm it worked:
   ```
   rclone lsd googlephotos:album
   ```
   (an empty list is fine - it just means no albums yet).
5. Restart the service:
   ```
   systemctl restart charmera-uploader
   systemctl status charmera-uploader
   journalctl -u charmera-uploader -f
   ```

Plug in the camera and watch the log / LED.

Note: rclone's shared client for Google Photos is expected to be retired
at some point (Google has been phasing out shared/community OAuth clients
across the ecosystem) - if `rclone config` ever stops working this way,
rclone's own docs cover creating your own client ID as a fallback, at
which point you're back to the Google Cloud Console path this section was
written to avoid.

### Restricting to just the Charmera (optional but recommended)

By default the daemon reacts to *any* USB mass-storage device plugged into
the Pi. To restrict it to just the camera, plug it in and run:

```
lsusb
```

Find its `vendor:model` ID (e.g. `04b0:0421`) and add it to
`usb_id_allowlist` in `config.yaml`, then restart the service.

## Manual testing without a camera

Point the daemon at any folder containing images/videos instead of waiting
for a real USB event:

```
python -m charmera_uploader.daemon --config config.yaml --process-path /path/to/test/folder
```

## Configuration reference

See [`config.example.yaml`](config.example.yaml) for every option with
comments; copy it to `config.yaml` and edit.

## Running the tests

```
pip install -r requirements-dev.txt
pytest
```

The test suite covers the dedupe manifest, photo scanning, album/upload
orchestration (against a fake photos client), the rclone command
construction (with `rclone` itself mocked out), LED state machine (in
simulate mode), and config loading - everything that doesn't require actual
USB/LED/rclone/Google hardware access. The udev monitoring loop and the
sysfs LED writes are deliberately thin wrappers so there's not much left
to break; test those for real once you're on the actual Pi.

## References

- [Updates to the Google Photos APIs](https://developers.google.com/photos/support/updates) - the 2025 scope deprecations that shaped the local-manifest dedupe design (still relevant even via rclone, which is subject to the same restrictions).
- [rclone: Google Photos](https://rclone.org/googlephotos/) and [rclone: Remote Setup](https://rclone.org/remote_setup/) - the shared-client setup and headless/SSH-tunnel authorization flow used in the setup steps above and verified against `rclone config`'s actual prompts.
- [rclone GitHub issue #9580: retiring the shared client_id](https://github.com/rclone/rclone/issues/9580) - why the "no Console setup needed" path is expected to eventually require your own client ID.
- [pyudev user guide](https://pyudev.readthedocs.io/en/latest/guide.html) - the `Monitor`/`Device` API used in `daemon.py`.
- [Orange Pi Zero 2W wiki](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_Zero_2W) and [Armbian forum thread on USB0 host mode](https://forum.armbian.com/topic/31654-orange-pi-zero-2w/page/2/) - the USB port/host-mode behavior described above, and the onboard red-power/green-status LED layout (`/sys/class/leds/`) used in `leds.py`.
- [KODAK Charmera Quick Start Guide](https://www.bhphotovideo.com/lit_files/1267743.pdf) and [B&H product listing](https://www.bhphotovideo.com/c/product/1920220-REG/kodak_rk0601_charmera_keychain_digital_camera.html) - confirms USB Mass Storage mode, FAT32 microSD, and the DCIM/VIDEO folder layout.
