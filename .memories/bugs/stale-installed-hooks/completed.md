# Completed

- Upgraded the installed dashboard from 0.8.0 to 0.9.0.
- Re-merged live Claude and Codex configuration: 17 managed hooks now use five-second timeouts.
- Exercised nine Claude and nine Codex event payloads; all returned zero in 284-328 ms.
- Changed the Windows installer to reject a failed setup helper even when an old install-state file exists.
- Rebuilt the signed Windows installer and Debian package; the Ubuntu 24.04 install/render/doctor/uninstall smoke test passed.
