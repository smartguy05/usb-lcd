# Notes

- The failed 0.9.0 upgrade left `Lib` and several runtime DLLs but removed `pythonw.exe`, the application package, identity scripts, `_pth` file, and uninstaller.
- Direct `File /r` extraction into `$INSTDIR` is not transactional; an extraction error can mix old/new files and make rollback impossible.
- The sandboxed Windows pytest runner can lose access to directories it creates; focused non-temp tests passed, while the Debian container smoke test covered install/uninstall behavior end to end.
- NSIS `SetOutPath` changes the setup process CWD. Leaving it inside `$INSTDIR.__new` makes Windows reject the activation rename; switch to `$TEMP` before directory operations.
- The directory rename still failed interactively after changing CWD. Activate by recursively copying the validated stage into a fresh final directory, then validate the final copy before deleting the stage.
- Interactive retry showed the old directory itself remained locked. The dashboard shutdown covers the daemon but persistent MCP/helper Python processes can still run from the embedded installation; stop only processes whose executable path is beneath the exact install directory.
- NSIS `CopyFiles` also produced the activation failure. Use built-in `robocopy` for the recursive staged copy and treat its documented 0-7 result range as success.
- The reported exit code 1 was from `usb_lcd_dashboard install`, not robocopy (where 1 is success). Reproduction against isolated copies of the live configs found `UnicodeDecodeError` reading UTF-8 `.claude.json` through Windows CP-1252 defaults.
