# Notes

- The renderer must receive an immutable snapshot; it must not access SQLite directly.
- Existing layouts, including the pixel-frozen legacy layout, stay unchanged.
- Current pytest runs are affected by Windows sandbox permissions on pytest temporary directories.
- Windows MCP must launch with `python.exe`, not the hook-friendly `pythonw.exe`; stdio clients need real pipes.
