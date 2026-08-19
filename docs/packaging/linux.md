# The Ubuntu package

> **Covers:** `packaging/linux/build-deb.sh`, `packaging/linux/build-deb-inner.sh`, `packaging/linux/control`, `packaging/linux/postinst`, `packaging/linux/postrm`, `packaging/linux/copyright`, `packaging/linux/changelog`, `packaging/linux/smoke-test.sh`, `packaging/linux/smoke-test-inner.sh`, `packaging/linux/smoke-test-user.sh`, `packaging/99-turing-lcd.rules`

A `.deb` that depends on the archive's Python rather than bundling one, because
Ubuntu already has it. Built in a container, so it can be produced from any
host including Windows.

```bash
packaging/linux/build-deb.sh      # -> dist/usb-lcd-dashboard_<version>_all.deb
packaging/linux/smoke-test.sh     # install it in a throwaway container
UBUNTU_IMAGE=ubuntu:26.04 packaging/linux/build-deb.sh
```

## Why it is shaped differently from the Windows installer

Windows bundles CPython because Windows has none. Ubuntu 24.04 ships python3
3.12, Pillow, pySerial and numpy, so the package declares them and apt resolves
them — 67 KB instead of 20 MB, with security updates from the archive.

The whole test suite passes against the archive's **Pillow 10.2**, which is why
`pyproject.toml` declares `pillow>=10.1` — 10.1 is the real floor, where
`ImageFont.load_default` gained its `size` argument.

Nothing in the package is compiled, so it is `Architecture: all`.

## Layout

```text
/usr/bin/usb-lcd-dashboard                            a real script, not a shim
/usr/lib/python3/dist-packages/usb_lcd_dashboard/
/usr/lib/python3/dist-packages/smartscreen_driver/    vendored
/lib/udev/rules.d/99-turing-lcd.rules
/usr/share/doc/usb-lcd-dashboard/{README.Debian,config.example.toml,changelog.Debian.gz,copyright}
```

`/usr/bin/usb-lcd-dashboard` must be a real script sitting beside
`/usr/bin/python3`, because that is exactly where `_command_prefix` looks for
the command to write into hooks and the systemd unit.

## Dependencies, and why

```
Depends: python3 (>= 3.12), python3-pil (>= 10.1), python3-serial (>= 3.5),
 python3-usb (>= 1.2.1), python3-pycryptodome (>= 3.20), python3-gi,
 gir1.2-ayatanaappindicator3-0.1, python3-numpy, fonts-dejavu-core
Recommends: systemd, git, fonts-ubuntu
```

- **`fonts-dejavu-core` is a hard dependency, not a recommendation.** A minimal
  Ubuntu ships **no TrueType font at all**, and `render._font` would silently
  fall back to a bitmap face on a device whose whole purpose is legible text.
  The smoke test asserts a real TrueType path is resolved.
- **`python3-usb` and `python3-pycryptodome` drive the TURZX panels.** Their
  versions here are the ones Ubuntu ships, which sit *below* the floors in
  `pyproject.toml` (`pyusb>=1.3`, `pycryptodome>=3.23`). That divergence is
  deliberate: those floors arrived with a bulk dependency bump in `c9257d8`, not
  for any API, and everything `turing_usb.py` calls — `usb.util.find_descriptor`,
  endpoint `read`/`write`, `DES` in CBC mode — long predates both. Pinning the
  archive versions is what lets the package install on a stock Ubuntu at all.
- **`python3-gi` and `gir1.2-ayatanaappindicator3-0.1` are the tray icon**, which
  is how the settings editor is reached on a desktop. Hard dependencies so a
  default Linux install matches Windows; on a headless box they cost a few
  megabytes and the daemon logs that it found no tray and carries on.
- **`git` is only a recommendation** — without it the branch beside the project
  name is simply absent.
- **smartscreen-driver is vendored, not depended on**: it is not in the archive.
  Pure Python and GPL-3.0 like this project, so it ships inside the package
  rather than becoming a pip step needing network at install time. Built from
  the same pinned commit as the Windows payload.

## The system / per-user split

`postinst` reloads udev and **prints instructions**. It does not wire hooks.
Quoted from its header:

> Only the system-wide half belongs here. The hooks and the systemd user service
> are per-user state under `$HOME`, and this script runs as root — wiring them
> here would install them for root and for nobody else.

`postrm` is symmetric: it does not reach into home directories to edit
`~/.claude/settings.json`, because it cannot know which users have it. So
package removal leaves per-user hooks in place; they fail harmlessly, and the
message says so.

The user's half is `usb-lcd-dashboard install` — see
[../integration/install.md](../integration/install.md).

## The udev rule

One file, two panels, because the two transports need different grants.

```udev
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", GROUP="plugdev", MODE="0660", TAG+="uaccess", SYMLINK+="turing-lcd"
SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", GROUP="plugdev", MODE="0660", TAG+="uaccess"
```

The first line does two things for the 3.5" serial panel: creates the stable
`/dev/turing-lcd` symlink that the default Linux config points at, and grants
the logged-in user access via `uaccess` and `plugdev`.

Without it there is only an unpredictable `/dev/ttyUSB*`, root-owned, that the
config does not name — `doctor` reports `FAIL device`, or `FAIL read/write
access` if the rule landed after the session started (log out and back in).

The second line covers TURZX panels. They expose a single vendor-class (`ff`)
interface with **no kernel driver bound**, so there is no tty to grant and no
symlink to create: libusb opens `/dev/bus/usb/<bus>/<dev>` directly, and that
node is `crw-rw-r-- root root` by default — readable, so enumeration works and
the panel is *found*, but not writable, so every frame fails. `doctor` names the
exact node in that case.

It matches on the vendor alone, not on product ids. The supported set lives in
`turing_usb.py:PRODUCT_SIZES` and grows as panels are added; a stale list here
would fail as an unwritable device rather than a missing one, which is much
harder to read.

### `/etc` shadows the packaged rule

The package installs to `/lib/udev/rules.d/`. udev skips a `/usr/lib` rules file
entirely when `/etc/udev/rules.d/` holds one of the **same name** — not merged,
skipped — so a hand-installed copy there masks every later update to the
packaged rule, silently and forever.

`README.md`'s run-from-source instructions install to `/etc/udev/rules.d/`,
which makes this collision easy to reach: install from source first, then the
`.deb`, and the package's rule never applies. It has already happened once — a
copy predating TURZX support kept a 1920x462 panel's raw node root-only while
`doctor` cheerfully reported the panel as found, because the node is *readable*
by default and only writes fail.

Diagnosing it takes one command, which names the skipped file outright:

```bash
udevadm test /sys/bus/usb/devices/<port> 2>&1 | grep -i skipping
```

## Build notes worth knowing

- The package tree is built at `/tmp/build` **inside the container**, not on the
  bind mount: a Windows mount reports every directory as mode 777 and
  `dpkg-deb` refuses a control directory outside 0755–0775.
- `postinst`/`postrm` have CR stripped at build time even though
  `.gitattributes` pins LF, because a zip download or stray editor could
  reintroduce one and the failure would only surface on the user's machine.
- `fakeroot dpkg-deb --build --root-owner-group` so files are `root:root`
  without the build running as root.

## The smoke test

`packaging/linux/smoke-test.sh` drives the whole lifecycle in a throwaway
container. The unit tests cover the code; this covers the packaging.

1. `apt install` the `.deb` — proves the declared dependencies are enough.
2. CLI runs, both modules import, and a **real TrueType font** resolves.
3. As an unprivileged user: `install`, then assert the hook command points at
   something executable and the unit's `ExecStart` is right.
4. Run the real daemon in simulate mode, emit a `PermissionRequest`, and assert
   a frame was actually rendered.
5. `doctor` (exits 1 in a container — no panel).
6. `uninstall`, then assert the unit is gone, no hooks remain, and the status
   line was restored.
7. `apt remove`, then assert the binary and udev rule are gone.

## Versioning

`pyproject.toml` is the source; both build scripts and the smoke test read it.
On a release, also update `packaging/linux/changelog`, `LINUX.md`, `WINDOWS.md`
(including the installer's **sha256**), and `README.md` — the docs quote
version-stamped filenames.

## See also

- [windows.md](windows.md)
- [../integration/install.md](../integration/install.md)
- `LINUX.md` at the repo root — the user-facing document.
