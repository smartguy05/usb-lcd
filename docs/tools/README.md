# The documentation tools

Two stdlib-only scripts. Nothing to install, and they run on Windows and Linux.

## search.py — find things cheaply

```bash
python docs/tools/search.py assign             # documents and definitions
python docs/tools/search.py --symbol compose   # definitions only
python docs/tools/search.py --doc arbitration  # documents only
python docs/tools/search.py --file crab.py     # a file's symbols, and its docs
python docs/tools/search.py --check            # validate the docs against the code
```

Every result is one greppable line carrying a path and a line number, so the
next step is a targeted read rather than opening a whole file:

```text
src/usb_lcd_dashboard/model.py:117  [method] def assign(self, slots: int, ...)  # Place live sessions into `slots` tiles.
```

`--file` also reports which documents cover that file, or `NOTHING YET`.

Exits 1 when a query matches nothing or when `--check` finds problems, so it
composes in a script.

## build_index.py — rebuild them

```bash
python docs/tools/build_index.py
```

Walks `src/`, `tests/` and `docs/` and writes three JSON files to
[../index/](../index/README.md). Takes about a second. Run it after adding,
moving or renaming a symbol.

It prints any source file that no document covers, which is the signal that the
documentation is falling behind the code.

## Keeping documentation honest

Prose that cites `file.py:LINE` rots silently as lines move. `--check`
re-resolves every citation, reports any that now point past the end of a file or
at a file that no longer exists, and fails if a source file has no document
covering it.

Run it before committing a documentation change.

## See also

- [../index/README.md](../index/README.md) — what the three index files contain.
- [../README.md](../README.md) — the documentation map.
