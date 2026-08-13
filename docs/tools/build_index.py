#!/usr/bin/env python3
"""Build the machine-readable indexes under docs/index/.

The point of these indexes is cost. An agent that needs to know where
``StateStore.assign`` lives, or which document explains tile arbitration, should
spend one cheap lookup rather than grepping a tree and reading whole files into
its context. Everything here is stdlib-only and runs on Windows and Linux, so
there is nothing to install before using it.

Three indexes are produced:

``symbols.json``
    Every class, function, method and module-level constant in ``src/``, with
    its file, line, signature and first docstring line.

``docs.json``
    Every document under ``docs/``, with its title, headings, the source files
    it declares that it covers, and the ``file.py:LINE`` references it cites.

``coverage.json``
    The reverse map: source file -> documents that cover it, plus the source
    files that no document covers yet. That last list is the one worth watching;
    it is how this documentation avoids quietly rotting as the code grows.

Run it from anywhere:

    python docs/tools/build_index.py
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
DOCS = ROOT / "docs"
INDEX = DOCS / "index"

# A document declares what it documents with a line like:
#     > **Covers:** `src/usb_lcd_dashboard/layout.py`, `src/.../widgets/base.py`
COVERS = re.compile(r"^>\s*\*\*Covers:\*\*\s*(.+)$", re.MULTILINE)
BACKTICKED = re.compile(r"`([^`]+)`")
# A citation of real code, e.g. layout.py:127 or src/usb_lcd_dashboard/cli.py:53
CITATION = re.compile(r"([\w./\\-]+\.py):(\d+)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.MULTILINE)


def relative(path: Path) -> str:
    """Repo-relative POSIX path, so an index built on Windows reads the same on
    Linux and vice versa."""
    return path.relative_to(ROOT).as_posix()


def signature(node: ast.AST) -> str:
    """Render a def/class header without its body."""
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(base) for base in node.bases]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


def summary(node: ast.AST) -> str:
    """The first line of the docstring, which is the useful part in a listing."""
    text = ast.get_docstring(node) or ""
    return text.strip().splitlines()[0] if text.strip() else ""


def index_python(path: Path) -> list[dict]:
    """Every top-level symbol, every method, and every module-level constant."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    found: list[dict] = []
    module_doc = summary(tree)
    found.append(
        {
            "name": path.stem,
            "kind": "module",
            "file": relative(path),
            "line": 1,
            "signature": f"module {path.stem}",
            "summary": module_doc,
            "parent": "",
        }
    )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            found.append(
                {
                    "name": node.name,
                    "kind": kind,
                    "file": relative(path),
                    "line": node.lineno,
                    "signature": signature(node),
                    "summary": summary(node),
                    "parent": "",
                }
            )
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        found.append(
                            {
                                "name": f"{node.name}.{child.name}",
                                "kind": "method",
                                "file": relative(path),
                                "line": child.lineno,
                                "signature": signature(child),
                                "summary": summary(child),
                                "parent": node.name,
                            }
                        )
                    # Dataclass fields are the shape of the data, so they are
                    # worth finding by name too.
                    elif isinstance(child, ast.AnnAssign) and isinstance(
                        child.target, ast.Name
                    ):
                        found.append(
                            {
                                "name": f"{node.name}.{child.target.id}",
                                "kind": "field",
                                "file": relative(path),
                                "line": child.lineno,
                                "signature": ast.unparse(child).split("\n")[0],
                                "summary": "",
                                "parent": node.name,
                            }
                        )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                # Module-level SHOUTY names are the tunables and tables people
                # look for: PHASES, WIDGETS, CLAUDE, DEFAULT_IPC_PORT.
                if isinstance(target, ast.Name) and target.id.isupper():
                    found.append(
                        {
                            "name": target.id,
                            "kind": "constant",
                            "file": relative(path),
                            "line": node.lineno,
                            "signature": f"{target.id} = ...",
                            "summary": "",
                            "parent": "",
                        }
                    )
    return found


def index_tests(path: Path) -> list[dict]:
    """Test names, so "what pins this behaviour?" is a lookup, not a search."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    return [
        {
            "name": node.name,
            "kind": "test",
            "file": relative(path),
            "line": node.lineno,
            "signature": f"def {node.name}(...)",
            "summary": summary(node),
            "parent": "",
        }
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def index_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    headings = [
        {"level": len(hashes), "text": title}
        for hashes, title in HEADING.findall(text)
    ]
    covers: list[str] = []
    match = COVERS.search(text)
    if match:
        covers = [item.strip() for item in BACKTICKED.findall(match.group(1))]
    citations = sorted({f"{file}:{line}" for file, line in CITATION.findall(text)})
    return {
        "path": relative(path),
        "title": headings[0]["text"] if headings else path.stem,
        "headings": [h["text"] for h in headings[1:]],
        "covers": covers,
        "citations": citations,
        "words": len(text.split()),
    }


def main() -> int:
    INDEX.mkdir(parents=True, exist_ok=True)

    symbols: list[dict] = []
    for path in sorted(SRC.rglob("*.py")):
        symbols.extend(index_python(path))
    for path in sorted(TESTS.rglob("*.py")):
        symbols.extend(index_tests(path))

    documents = [
        index_doc(path)
        for path in sorted(DOCS.rglob("*.md"))
        # The index's own README describes the index; it documents no source.
        if INDEX not in path.parents
    ]

    # source file -> the documents claiming to cover it
    coverage: dict[str, list[str]] = {}
    for doc in documents:
        for source in doc["covers"]:
            coverage.setdefault(source, []).append(doc["path"])

    source_files = [relative(p) for p in sorted(SRC.rglob("*.py"))]
    uncovered = [f for f in source_files if f not in coverage]

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write(INDEX / "symbols.json", {"generated": generated, "symbols": symbols})
    write(INDEX / "docs.json", {"generated": generated, "documents": documents})
    write(
        INDEX / "coverage.json",
        {
            "generated": generated,
            "by_source": coverage,
            "uncovered_sources": uncovered,
        },
    )

    covered = sum(1 for name in source_files if name in coverage)
    print(f"symbols   {len(symbols):5d}  -> {relative(INDEX / 'symbols.json')}")
    print(f"documents {len(documents):5d}  -> {relative(INDEX / 'docs.json')}")
    print(f"covered   {covered:5d} of {len(source_files)} source files")
    if uncovered:
        print(f"UNCOVERED {len(uncovered):5d}:")
        for name in uncovered:
            print(f"    {name}")
    return 0


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
