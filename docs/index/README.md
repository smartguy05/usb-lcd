# The indexes

Generated lookup tables that let an agent answer "where is this?" and "what
explains this?" without grepping the tree or reading whole files. They are
committed so they can be read directly, and rebuilt in about a second when the
code moves.

```bash
python docs/tools/build_index.py     # rebuild all three
python docs/tools/search.py --check  # verify the docs still match the code
```

See [../tools/README.md](../tools/README.md) for how to query them.

## The files

| File | What it holds |
| --- | --- |
| `symbols.json` | Every class, function, method, dataclass field and module-level constant in `src/`, plus every test name in `tests/`. Each entry has `name`, `kind`, `file`, `line`, `signature` and the first line of its docstring. |
| `docs.json` | Every document under `docs/`: title, headings, the source files it declares it covers, and every `file.py:LINE` it cites. |
| `coverage.json` | `by_source` maps each source file to the documents covering it. `uncovered_sources` lists the source files no document covers — the list that keeps this documentation honest as the code grows. |

## How coverage is declared

A document claims a source file by carrying a line like this near the top:

```markdown
> **Covers:** `src/usb_lcd_dashboard/layout.py`, `src/usb_lcd_dashboard/background.py`
```

`build_index.py` parses those lines to build `coverage.json`. If you add a source
file and no document claims it, `search.py --check` fails and names it. If you
add a document, give it a `Covers:` line or it will contribute nothing to the
reverse map.

## Staleness

`symbols.json` is regenerated from the code, so it is only as fresh as the last
build. Line numbers cited in prose are the part that rots: `search.py --check`
re-resolves every citation and reports any that now point past the end of a file
or at a file that no longer exists.

Rebuild the indexes whenever you add, move or rename a symbol, and run `--check`
before committing documentation changes.
