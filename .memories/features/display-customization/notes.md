# Notes

- The legacy full-screen fast path must remain byte-identical when no wallpaper is configured.
- The settings editor communicates with the daemon through the config file; uploads must not activate a wallpaper before Save.
- A real daemon may own the default IPC/admin ports and physical panel.
- Pytest temporary directories require running outside the managed filesystem sandbox on this Windows host.
- Git's `usr/bin` must be on PATH for the Windows status-line proxy test that invokes `cat`.
