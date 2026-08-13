# Packaging

Two installers, deliberately different shapes, both built in containers so
either can be produced from either host.

| Document | Covers |
| --- | --- |
| [windows.md](windows.md) | The NSIS installer and its bundled CPython. |
| [linux.md](linux.md) | The `.deb`, the udev rule, and the smoke test. |

## Why they differ

Windows bundles a Python runtime because Windows has none. Ubuntu already ships
python3, Pillow, pySerial and numpy, so the `.deb` depends on them — 67 KB
against 20 MB, and it gets security updates from the archive.

Both split the same way: the package puts the program on the machine, and
`usb-lcd-dashboard install` wires it into *your* sessions. On Windows the
installer runs that step for you. On Linux it cannot, because `postinst` runs as
root and would wire the dashboard into root's sessions and nobody else's.

## Build

```bash
packaging/windows/build-installer.sh    # needs Docker or Podman
packaging/linux/build-deb.sh
packaging/linux/smoke-test.sh           # after build-deb.sh
```

The version comes from `pyproject.toml`. On a release the docs that quote
version-stamped filenames also need updating, including the installer sha256 in
`WINDOWS.md`.

## Two traps

- **Never run `dist/*.exe` to inspect it.** NSIS `/S` performs a full install,
  not an extraction.
- **`packaging/windows/payload/` is generated build output**, gitignored. Never
  edit it, and never read it as source — the real code is in `src/`.

## See also

- [../integration/install.md](../integration/install.md) — the per-user half.
- `WINDOWS.md` and `LINUX.md` at the repo root — the user-facing versions.
