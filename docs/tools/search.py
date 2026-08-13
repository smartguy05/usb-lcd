#!/usr/bin/env python3
"""Query the docs/index/ indexes.

Built for agents rather than humans: every answer is a short, greppable line
containing a path and a line number, so the next step is a targeted read of a
few lines rather than a whole file.

    python docs/tools/search.py assign              # symbols and docs matching
    python docs/tools/search.py --symbol compose    # definitions only
    python docs/tools/search.py --doc arbitration   # documents only
    python docs/tools/search.py --file layout.py    # what is in a file, and
                                                    # which docs cover it
    python docs/tools/search.py --check             # verify docs' code citations

``--check`` is the one to run after editing code: documentation that cites
``file.py:LINE`` rots silently as lines move, and this reports every citation
that now points past the end of a file or at a file that no longer exists.

Exits 1 when ``--check`` finds problems or a query matches nothing, so it can be
used in a script.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs" / "index"

# [text](target) - markdown links, for the rot check.
LINK = re.compile(r"\]\(([^)\s]+)\)")


def load(name: str) -> dict:
    path = INDEX / name
    if not path.exists():
        sys.exit(
            f"{path.relative_to(ROOT).as_posix()} is missing. "
            "Build it with: python docs/tools/build_index.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def rank(needle: str, name: str) -> int:
    """Exact beats prefix beats substring, so the obvious hit sorts first."""
    lowered = name.lower()
    if lowered == needle:
        return 0
    if lowered.endswith("." + needle):  # Class.method searched by method name
        return 1
    if lowered.startswith(needle):
        return 2
    return 3


def find_symbols(needle: str, kinds: set[str] | None = None) -> list[dict]:
    symbols = load("symbols.json")["symbols"]
    hits = [
        s
        for s in symbols
        if needle in s["name"].lower() and (not kinds or s["kind"] in kinds)
    ]
    return sorted(hits, key=lambda s: (rank(needle, s["name"]), s["file"], s["line"]))


def find_docs(needle: str) -> list[dict]:
    documents = load("docs.json")["documents"]
    hits = []
    for doc in documents:
        haystack = " ".join(
            [doc["title"], doc["path"], " ".join(doc["headings"]), " ".join(doc["covers"])]
        ).lower()
        if needle in haystack:
            hits.append(doc)
    return sorted(hits, key=lambda d: (rank(needle, d["title"]), d["path"]))


def show_symbol(symbol: dict) -> str:
    tail = f"  # {symbol['summary']}" if symbol["summary"] else ""
    return f"{symbol['file']}:{symbol['line']}  [{symbol['kind']}] {symbol['signature']}{tail}"


def show_doc(doc: dict) -> str:
    covers = f"  covers: {', '.join(doc['covers'])}" if doc["covers"] else ""
    return f"{doc['path']}  \"{doc['title']}\"{covers}"


def command_file(pattern: str) -> int:
    symbols = load("symbols.json")["symbols"]
    coverage = load("coverage.json")["by_source"]

    files = sorted({s["file"] for s in symbols if pattern in s["file"]})
    if not files:
        print(f"No indexed file matches {pattern!r}")
        return 1

    for name in files:
        print(f"\n=== {name} ===")
        docs = coverage.get(name, [])
        print(f"documented by: {', '.join(docs) if docs else 'NOTHING YET'}")
        for symbol in [s for s in symbols if s["file"] == name]:
            if symbol["kind"] == "module":
                continue
            print(f"  {symbol['line']:5d}  [{symbol['kind']:8s}] {symbol['name']}")
    return 0


def source_files() -> list[Path]:
    """Every Python file that is ours, ignoring the venv and build output."""
    skip = {".venv", ".build", "payload", "__pycache__", "node_modules"}
    return [
        path
        for path in ROOT.rglob("*.py")
        if not skip.intersection(path.parts)
    ]


def resolve(cited: str, files: list[Path]) -> Path | None:
    """Find the file a citation names.

    Matched on a path *suffix*, not a bare basename: half the modules in this
    project are called __init__.py, and matching on the name alone would happily
    resolve "widgets/__init__.py" to the package root's.
    """
    wanted = cited.replace("\\", "/").lstrip("./")
    matches = [f for f in files if f.as_posix().endswith("/" + wanted)]
    if not matches:
        # A bare name with no directory part is still allowed, as long as it is
        # unambiguous.
        matches = [f for f in files if f.name == Path(wanted).name]
        if len(matches) != 1:
            return None
    # Prefer the shortest path when several match, which is the least nested and
    # therefore the most likely intent.
    return min(matches, key=lambda f: len(f.parts))


def command_check() -> int:
    """Verify every file.py:LINE a document cites still resolves."""
    documents = load("docs.json")["documents"]
    files = source_files()
    problems: list[str] = []
    checked = 0

    for doc in documents:
        for citation in doc["citations"]:
            name, _, line_text = citation.rpartition(":")
            line = int(line_text)
            checked += 1
            target = resolve(name, files)
            if target is None:
                problems.append(
                    f"{doc['path']}: cites {citation} but no such file exists"
                )
                continue
            total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            if line > total:
                problems.append(
                    f"{doc['path']}: cites {citation} but "
                    f"{target.relative_to(ROOT).as_posix()} has only {total} lines"
                )

    # Relative links rot the same way citations do, and a dead link in a
    # directory README is worse than a stale line number: it sends the reader
    # nowhere at all.
    links = 0
    for doc in documents:
        source = ROOT / doc["path"]
        text = source.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            links += 1
            path, _, anchor = target.partition("#")
            if not path:
                continue
            resolved = (source.parent / path).resolve()
            if not resolved.exists():
                problems.append(f"{doc['path']}: broken link -> {target}")

    coverage = load("coverage.json")
    for source_name in coverage["uncovered_sources"]:
        problems.append(f"no document covers {source_name}")

    print(
        f"checked {checked} code citations and {links} relative links "
        f"across {len(documents)} documents"
    )
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("all citations resolve, all source files are covered")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="search.py", description="Query the documentation indexes."
    )
    parser.add_argument("query", nargs="?", default="", help="text to look for")
    parser.add_argument("--symbol", metavar="NAME", help="search definitions only")
    parser.add_argument("--doc", metavar="TEXT", help="search documents only")
    parser.add_argument("--file", metavar="PATH", help="list a file's symbols and docs")
    parser.add_argument("--check", action="store_true", help="validate doc citations")
    parser.add_argument("--limit", type=int, default=25, help="max hits per section")
    args = parser.parse_args(argv)

    if args.check:
        return command_check()
    if args.file:
        return command_file(args.file)

    if args.symbol:
        hits = find_symbols(args.symbol.lower())
        for symbol in hits[: args.limit]:
            print(show_symbol(symbol))
        return 0 if hits else 1

    if args.doc:
        hits = find_docs(args.doc.lower())
        for doc in hits[: args.limit]:
            print(show_doc(doc))
        return 0 if hits else 1

    if not args.query:
        parser.print_help()
        return 1

    needle = args.query.lower()
    documents = find_docs(needle)
    symbols = find_symbols(needle)

    if documents:
        print("== documents ==")
        for doc in documents[: args.limit]:
            print(show_doc(doc))
    if symbols:
        if documents:
            print()
        print("== definitions ==")
        for symbol in symbols[: args.limit]:
            print(show_symbol(symbol))

    if not documents and not symbols:
        print(f"Nothing matches {args.query!r}.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
