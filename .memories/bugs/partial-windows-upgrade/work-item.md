# Work Item

Fix the 0.9.0 Windows setup program leaving a partial, unusable installation during upgrade.

## Acceptance criteria

- The complete payload is staged before the existing installation is changed.
- A failed upgrade preserves or restores the previous installation.
- Setup rejects incomplete staged payloads.
- Both 0.9.1 release installers are rebuilt and verified.
