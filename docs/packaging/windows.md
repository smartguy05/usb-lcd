# The Windows installer

> **Covers:** `packaging/windows/build-installer.sh`, `packaging/windows/installer.nsi`, `packaging/windows/config.example.toml`

A self-contained NSIS installer that bundles its own CPython, because Windows
has none. Built in a container, so it can be produced from Linux or from Windows
under Git Bash.

```bash
packaging/windows/build-installer.sh          # -> dist/USB-LCD-Dashboard-Setup-<version>.exe
CONTAINER_RUNTIME=podman packaging/windows/build-installer.sh
```

## The build

1. Read `APP_VERSION` from `pyproject.toml` — the single source.
2. Download **CPython 3.12.10 embeddable amd64**, verified against a pinned
   `PYTHON_SHA256` before it is trusted.
3. `pip download` pinned wheels for the target platform: Pillow 12.3.0, pyserial
   3.5, numpy 2.5.1 (`--platform win_amd64 --only-binary=:all:`).
4. `pip wheel` **smartscreen-driver** from a pinned git commit
   (`918342ec…`) — the same commit the Debian build vendors.
5. Unzip every wheel into `payload/Lib/site-packages`, copy `src/usb_lcd_dashboard`
   in beside them, strip `__pycache__`.
6. Patch `python312._pth` to add `Lib/site-packages` and uncomment `import site`
   — the embeddable distribution disables both by default.
7. Run `makensis -DAPP_VERSION=…` inside `ubuntu:24.04`.
8. Print `file` and `sha256sum` of the result.

**No console script is installed**, which is why `_command_prefix` has its
`python.exe -m usb_lcd_dashboard` fallback — see
[../integration/install.md](../integration/install.md#how-the-command-is-resolved).

## What the installer does

Per-user, no administrator rights:

```nsis
InstallDir "$LOCALAPPDATA\Programs\USB LCD Dashboard"
RequestExecutionLevel user
```

Ordered contract:

1. **Shut down any running instance** — `python.exe -m usb_lcd_dashboard shutdown`,
   then sleep 500 ms.
2. Copy the payload; write `Uninstall.exe`.
3. **Run the app's own setup**: `python.exe -m usb_lcd_dashboard install`. NSIS
   never touches hook files itself.
4. **Verify it worked** by checking for `install-state.json`, and abort loudly
   with a message box if it is missing. A half-installed state is not accepted.
5. Shortcuts: `$SMSTARTUP\USB LCD Dashboard.lnk` → `pythonw.exe -m usb_lcd_dashboard run`
   (this *is* the autostart mechanism — no service, no scheduled task), plus
   Start-menu **Diagnostics** (`doctor`) and **Uninstall**.
6. `HKCU` registry: `InstallDir`, plus the standard Uninstall key with
   `DisplayName`, `DisplayVersion`, `UninstallString` and `QuietUninstallString`
   — which is what puts it in **Settings → Apps**.
7. **Launch it immediately**: `Exec pythonw.exe -m usb_lcd_dashboard run`. The
   user does not have to log out.

Uninstall reverses it: shutdown, `uninstall` (hooks and status line), delete the
shortcuts, delete both registry keys, `RMDir /r "$INSTDIR"`. It leaves
`%LOCALAPPDATA%\usb-lcd-dashboard` — config, state and backups — alone.

Add `/S` for a silent install.

> **Never run the exe to inspect it.** `/S` performs a full install, not an
> extraction. Use `packaging/windows/payload/` if you want to see what is in it.

## The payload directory is generated

`packaging/windows/payload/` is gitignored build output. Do not edit anything in
it and do not read it as source; the real code is in `src/`.

## Windows-specific runtime notes

- `[ipc] mode = "tcp"` on port 45722, because the shipped default has no AF_UNIX.
- `[tray] enabled = true` — the tray is Windows-only, and is the only visible
  sign of life under console-less `pythonw.exe`. See
  [../admin/tray.md](../admin/tray.md).
- `run` logs to a file on Windows; on Linux it logs to the journal.

## See also

- [linux.md](linux.md) — the other package, deliberately a different shape.
- [../integration/install.md](../integration/install.md) — step 3.
- `WINDOWS.md` at the repo root — the user-facing document, which quotes the
  version-stamped filename and the installer's sha256.
