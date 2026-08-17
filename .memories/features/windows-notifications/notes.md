# Notes

- Windows notification access requires package identity and `uap3:userNotificationListener`.
- The Windows installer build requires Windows SDK tools to embed and sign identity.
- Docker Desktop may be absent; start Podman and set `CONTAINER_RUNTIME=podman`.
- AppX rejected the self-signed MSIX with `0x800B0109` from both current-user
  `TrustedPeople` and `Root`, even when Authenticode reported a valid signature.
- The supported self-signed MSIX path is `LocalMachine\TrustedPeople`. The NSIS
  installer therefore requests elevation and uses noninteractive `certutil`;
  uninstall removes only the bundled certificate's exact thumbprint.
- PyWinRT projections do not declare every cross-namespace runtime dependency.
  Notification access also needs Foundation, Foundation.Collections,
  ApplicationModel, and Data.Xml.Dom wheels explicitly bundled.
- Because NSIS is elevated for certificate trust, it must launch the per-user
  startup shortcut through Explorer rather than starting `pythonw.exe` as an
  elevated child.
