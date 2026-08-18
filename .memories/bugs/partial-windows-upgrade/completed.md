# Completed

- Confirmed the 0.9.0 setup left a partial live installation missing its executable entry point and application code.
- Changed Windows upgrades to validate a side-by-side staged payload, atomically swap directories, and restore the old tree and identity on failure.
- Added source-level regression tests for staging order, payload validation, and rollback paths.
- Released 0.9.1, rebuilt both artifacts, verified Windows version/payload metadata and SHA-256 hashes, and passed the Ubuntu 24.04 install/render/doctor/uninstall smoke test.
- Corrected the staged activation failure reported during interactive setup by moving setup's working directory outside the staged tree before renaming it.
- Rebuilt the corrected 0.9.1 Windows setup executable and recorded its final SHA-256 digest.
- Replaced staged-directory activation by rename with a validated recursive copy after the rename continued to fail on the target machine.
- Rebuilt and verified the copy-activation 0.9.1 Windows installer; final SHA-256 is `49f152426c2c6cc2418b852ea19c98fa5f6246813aeccd865012777cf40acf62`.
- Added exact-install-path process cleanup for persistent MCP and hook interpreters that keep the old embedded runtime locked during upgrade.
- Rebuilt and verified the locked-process-safe 0.9.1 installer; final SHA-256 is `a1ca3a514d068d0b1fd580dcfe8cc9ad4134f0b38fa30b4b45bdd3839babc5d8`.
- Replaced unreliable recursive NSIS shell copying with `robocopy` activation and explicit exit-code handling.
- Rebuilt and verified the robocopy-based 0.9.1 installer; final SHA-256 is `f2d6d7bdc9c063a1f2ce68033d719f22ebb421d05dae664d052c48e5c47a62b4`.
- Made installer-managed JSON, TOML, config, and systemd text explicitly UTF-8 and added Unicode configuration regression coverage.
- Reproduced setup against isolated copies of the user's live configs: the original payload exited 1 with `UnicodeDecodeError`; the fixed source completed with exit 0.
- Rebuilt both 0.9.1 artifacts, verified the UTF-8 fix is embedded, and passed the Ubuntu install/render/doctor/uninstall smoke test.
- User confirmed the final Windows installer completes successfully.
- Documented the cross-work-item installer and UTF-8 invariants in `CLAUDE.md` and the detailed upgrade lessons in `docs/packaging/windows.md`.
- Regenerated the documentation index; all 103 code citations and 222 relative links validate.
