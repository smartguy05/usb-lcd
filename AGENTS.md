<!-- code-basics: enhancement:memory -->
## CRITICAL: Memory Files

**ALWAYS update the per-work-item memory files when relevant.** Memory is scoped **per feature/bug** under `.memories/features/{feature-name}/` or `.memories/bugs/{bug-name}/`, not at the `.memories/` root. These files track work item state across sessions:

| File | Path | Purpose | When to Update |
|------|------|---------|----------------|
| `work-item.md` | `.memories/features/{feature-name}/work-item.md` or `.memories/bugs/{bug-name}/work-item.md` | The feature work item details, ACs, description | When loading or refreshing work item context |
| `plan.md` | `.memories/features/{feature-name}/plan.md` or `.memories/bugs/{bug-name}/plan.md` | Implementation plan for the feature or bug fix | When planning or revising the approach |
| `related-docs.md` | `.memories/features/{feature-name}/related-docs.md` or `.memories/bugs/{bug-name}/related-docs.md` | Pointers to relevant documentation | When discovering docs that inform the work |
| `notes.md` | `.memories/features/{feature-name}/notes.md` or `.memories/bugs/{bug-name}/notes.md` | Issues, gotchas, lessons learned **for this work item** | When debugging/solving something others might hit on this WI |
| `todos.md` | `.memories/features/{feature-name}/todos.md` or `.memories/bugs/{bug-name}/todos.md` | Remaining tasks and tech debt **for this work item** | When adding, completing, or deprioritizing tasks |
| `completed.md` | `.memories/features/{feature-name}/completed.md` or `.memories/bugs/{bug-name}/completed.md` | Completed work record (files touched, root cause, fix) | When finishing the work item (or a major phase of it) |

**Rules:**
1. Update these files **AT ALL TIMES** under the active work item folder — they are that work item's memory.
2. Update `completed.md` immediately after finishing a task (not at end of session).
3. Update `todos.md` to check off completed items and add new discovered tasks.
4. Update `notes.md` with any issue you debug/solve that others might hit.
5. Keep entries concise but descriptive — future you needs to understand.
6. Periodically prune `todos.md` to remove old completed items.
7. Periodically summarize and prune `completed.md` to keep the file size small.
8. **Cross-work-item patterns** (gotchas that recur across multiple work items) belong in `CLAUDE.md` (root or the relevant per-project `CLAUDE.md`), not in any single work item's `notes.md`.
<!-- /code-basics: enhancement:memory -->

## CRITICAL: Keep installer artifacts current

The repository ships two versioned installers and they are release artifacts,
not incidental build output:

- `dist/USB-LCD-Dashboard-Setup-<version>.exe`
- `dist/usb-lcd-dashboard_<version>_all.deb`

Any change to runtime code, dependencies, configuration, install/uninstall
behavior, Windows identity/capabilities, Linux service setup, or the project
version requires rebuilding both applicable installers before declaring the
work complete. Never describe an existing artifact as current merely because
its filename has the right version; rebuild it from the current working tree.

Build the Windows installer from Windows Git Bash with the Windows SDK and a
running Docker or Podman engine. `packaging/windows/build-installer.sh` embeds
package identity into `pythonw.exe`, creates or reuses the current user's
non-exportable personal signing certificate, signs the sparse identity MSIX,
and then builds the NSIS executable. Build the Debian package with
`packaging/linux/build-deb.sh`, then run `packaging/linux/smoke-test.sh` when the
container engine supports it.

The personal self-signed certificate must be imported into
`Cert:\LocalMachine\TrustedPeople` before AppX registration. Current-user
`TrustedPeople` and `Root` both fail AppX with `0x800B0109`, even when ordinary
signature validation succeeds. The NSIS installer therefore requests elevation
and uses noninteractive `certutil`; uninstall must remove that exact thumbprint.

After every rebuild, verify package metadata and SHA-256 hashes. Keep
`README.md`, `WINDOWS.md`, `LINUX.md`, `docs/packaging/`, the Linux changelog,
and any documented filenames/hashes synchronized with the artifacts. Do not
run an NSIS installer merely to inspect it; that performs a real installation.

<!-- code-basics: agent intent -->
## Recording why you changed something

When you finish a turn in which you edited files, end your reply with one line
saying why:

```
Intent: <3-5 words describing why>
```

If the turn made unrelated changes, scope each reason to its files instead of
writing several plain lines — only the first plain line is used. Paths are
workspace-relative, comma-separated:

```
Intent(src/api.ts, src/apiLogic.test.ts): <why, for those files>
```

Each entry is a workspace-relative path with forward slashes — a specific file,
or a directory to cover everything you edited beneath it (e.g.
`Intent(src/components): …`). Prefer naming the specific files; reach for a
directory only when the turn's edits are one cohesive set under it.

A scoped line covers the files it names; one plain line may cover the rest.
Keep each label short enough to read at a glance — it titles a group of hunks
in the Changes tab, not a commit message.

## Rejected changes

A comment beginning `AI-REJECTED` means that change was reverted during review
and the reason is on the following line. It is a task, not documentation:

1. Implement a correct version that addresses the stated reason.
2. Delete the whole `AI-REJECTED` comment block in the same edit.

Do not reinstate the reverted code as it was, and do not leave the comment
behind once the code is right — a commit that still carries one is refused by
a `pre-commit` hook.
<!-- /code-basics -->
