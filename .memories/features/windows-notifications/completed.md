# Completed

- Implemented notification collection, filtering, rotation, settings, tests, and Windows identity packaging.
- Added installer-maintenance requirements to `AGENTS.md` and `CLAUDE.md`.
- Rebuilt the 0.7.1 Windows and Debian installers from the current tree.
- Smoke-tested the Debian package and recorded both SHA-256 hashes in release docs.
- Diagnosed AppX error `0x800B0109`: current-user certificate trust is not
  accepted by the deployment service. Changed NSIS to elevate and place the
  public signing certificate in `LocalMachine\TrustedPeople`, with exact
  thumbprint cleanup, then rebuilt the Windows installer.
- Diagnosed the blank LCD after reinstall: the installed embedded runtime was
  incomplete and Pillow could not import, while notification startup also lacked
  cross-namespace PyWinRT wheels. Added the wheels, a longer daemon shutdown
  window, copy-error detection, and an Explorer-mediated non-elevated launch.
