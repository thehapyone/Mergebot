"""Symbol extraction and caching for the fact pack.

Python files get real AST
symbols; other languages fall back to conservative line-based heuristics. This is the
local-excerpt story only — cross-language graph facts come from code-review-graph.
"""

import ast
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE_VERSION = "1"
CACHE_PRUNE_INTERVAL_SECONDS = 24 * 60 * 60
CACHE_ENTRY_TTL_SECONDS = 30 * 24 * 60 * 60

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".swift",
    ".scala",
    ".sh",
    ".bash",
    ".zsh",
}


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str


class SymbolCache:
    """Content-hash-keyed symbol cache, persisted across reviews.

    `cache_key` must be a stable project identity (e.g. the project path), NOT the
    per-review checkout path — entries are keyed by file content hash, so a stable
    project key is what lets a later review of the same project hit the cache.
    Writes are atomic (temp file + rename) because concurrent reviews of the same
    project share the directory; unreadable entries are treated as misses.
    """

    def __init__(self, cache_dir: Path, cache_key: str) -> None:
        repo_key = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        self.cache_dir = cache_dir / repo_key
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._prune_expired()

    def get_or_parse(self, path: Path) -> tuple[list[Symbol], bool]:
        digest = _file_sha256(path)
        cache_path = self.cache_dir / f"{digest}.json"
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") == CACHE_VERSION:
                return [_symbol_from_dict(item) for item in payload["symbols"]], True
        except (OSError, ValueError, KeyError, TypeError):
            pass  # missing, corrupt, or stale entry → re-parse and overwrite

        symbols = extract_symbols(path)
        self._atomic_write(
            cache_path,
            json.dumps(
                {
                    "version": CACHE_VERSION,
                    "path": str(path),
                    "symbols": [symbol.__dict__ for symbol in symbols],
                },
                indent=2,
                sort_keys=True,
            ),
        )
        return symbols, False

    @staticmethod
    def _atomic_write(cache_path: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(tmp_name, cache_path)
        except OSError:
            Path(tmp_name).unlink(missing_ok=True)

    def _prune_expired(self) -> None:
        """Drop entries unused for CACHE_ENTRY_TTL_SECONDS, at most once a day."""
        marker = self.cache_dir / ".last-prune"
        now = time.time()
        try:
            if now - marker.stat().st_mtime < CACHE_PRUNE_INTERVAL_SECONDS:
                return
        except OSError:
            pass
        marker.touch()
        for entry in self.cache_dir.glob("*.json"):
            try:
                if now - entry.stat().st_mtime > CACHE_ENTRY_TTL_SECONDS:
                    entry.unlink()
            except OSError:
                continue


def extract_symbols(path: Path) -> list[Symbol]:
    text = read_text(path)
    if path.suffix == ".py":
        return _extract_python_symbols(text, path.name)
    return _extract_heuristic_symbols(text, path.name)


def symbol_with_path(symbol: Symbol, path: str) -> Symbol:
    return Symbol(
        name=symbol.name,
        kind=symbol.kind,
        path=path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        signature=symbol.signature,
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_within(root: Path, rel_path: str | Path) -> Path | None:
    """Resolve `root / rel_path` for reading, refusing paths that escape `root`.

    Symlink-aware: the resolved target must stay under `root`, so a symlinked
    path inside a checkout can never route a read outside it (PR content is
    attacker-controlled). Defense in depth behind the workspace clone's
    `core.symlinks=false`, which stops symlinks from materializing at all.
    """
    try:
        real = (root / rel_path).resolve()
        root_real = root.resolve()
    except OSError:
        return None
    if real != root_real and not real.is_relative_to(root_real):
        return None
    return real


def is_probably_binary(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\0" in sample


def is_source_path(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_SUFFIXES


def _extract_python_symbols(text: str, rel_path: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_heuristic_symbols(text, rel_path)

    symbols = []
    parents: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            name = ".".join([*parents, node.name])
            symbols.append(_python_symbol(node, rel_path, name, "class", text))
            parents.append(node.name)
            for child in node.body:
                visit(child)
            parents.pop()
            return
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = ".".join([*parents, node.name])
            symbols.append(_python_symbol(node, rel_path, name, "function", text))
            parents.append(node.name)
            for child in node.body:
                visit(child)
            parents.pop()
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return sorted(symbols, key=lambda item: (item.start_line, item.name))


def _python_symbol(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: str,
    name: str,
    kind: str,
    text: str,
) -> Symbol:
    end_line = getattr(node, "end_lineno", node.lineno)
    lines = text.splitlines()
    signature = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else name
    return Symbol(
        name=name,
        kind=kind,
        path=rel_path,
        start_line=node.lineno,
        end_line=end_line,
        signature=signature,
    )


def _extract_heuristic_symbols(text: str, rel_path: str) -> list[Symbol]:
    patterns = [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
        (re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
        (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="), "function"),
        (re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)"), "function"),
        (re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
        (re.compile(r"^\s*(?:public|private|protected)?\s*class\s+([A-Za-z_]\w*)"), "class"),
        (re.compile(r"^\s*def\s+([A-Za-z_]\w*)"), "function"),
    ]
    lines = text.splitlines()
    starts: list[tuple[int, str, str, str]] = []
    for index, line in enumerate(lines, start=1):
        for pattern, kind in patterns:
            match = pattern.match(line)
            if match:
                starts.append((index, match.group(1), kind, line.strip()))
                break

    symbols = []
    for offset, (start, name, kind, signature) in enumerate(starts):
        end = starts[offset + 1][0] - 1 if offset + 1 < len(starts) else len(lines)
        symbols.append(
            Symbol(
                name=name,
                kind=kind,
                path=rel_path,
                start_line=start,
                end_line=max(start, end),
                signature=signature,
            )
        )
    return symbols


def _symbol_from_dict(data: dict[str, Any]) -> Symbol:
    return Symbol(
        name=data["name"],
        kind=data["kind"],
        path=data["path"],
        start_line=int(data["start_line"]),
        end_line=int(data["end_line"]),
        signature=data["signature"],
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
