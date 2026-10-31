"""
Member 1 (You): Core Graph Engine — parser.py
==============================================
Thin adapter layer over the REAL repograph (D33PAKsoni/repograph) indexer.

repograph already handles:
  • tree-sitter AST extraction for Python, JS, TS (+ Go, Rust, Ruby, etc.)
  • Incremental SQLite-backed indexing (.repograph/index.db)
  • Symbol / import / ref / route extraction
  • Confirmed + inferred cross-file call edges

This module exposes a clean, higher-level CodeGraph abstraction (nodes, edges)
that bridge.py can consume directly AND that the rest of the project can use
without touching repograph internals.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ── Real repograph API ──────────────────────────────────────────────────────
from repograph.indexer import index_repository, IndexStats
from repograph.store import Store
from repograph.config import load_settings, Settings

logger = logging.getLogger("parser")


# ── Domain types ────────────────────────────────────────────────────────────

@dataclass
class Node:
    """Code entity (function, class, method, module, import …)."""
    id: str
    name: str
    type: str          # function | class | method | module | import | interface | type | enum
    file: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Edge:
    """Directed dependency between two nodes."""
    source: str        # node id
    target: str        # node id
    type: str          # calls | imports | inherits | defines | ref
    weight: float = 1.0
    confidence: str = "confirmed"   # confirmed | inferred | heuristic
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CodeGraph:
    """In-memory directed dependency graph built from repograph's SQLite index."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._adj_out: Dict[str, Set[str]] = {}
        self._adj_in: Dict[str, Set[str]] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self._adj_out.setdefault(node.id, set())
        self._adj_in.setdefault(node.id, set())

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)
        self._adj_out.setdefault(edge.source, set()).add(edge.target)
        self._adj_in.setdefault(edge.target, set()).add(edge.source)

    def get_neighbors_out(self, node_id: str) -> Set[str]:
        return self._adj_out.get(node_id, set())

    def get_neighbors_in(self, node_id: str) -> Set[str]:
        return self._adj_in.get(node_id, set())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "stats": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
            },
        }


# ── Indexing helpers ─────────────────────────────────────────────────────────

def ensure_indexed(repo_path: Path, *, force: bool = False) -> IndexStats:
    """
    Run repograph's incremental indexer on *repo_path*.
    Idempotent: only reindexes files that changed since the last run.
    Returns IndexStats for diagnostics.
    """
    logger.info("Running repograph indexer on %s …", repo_path)
    stats = index_repository(repo_path, force=force)
    logger.info(
        "Index complete — %d files, %d added, %d updated, %d unchanged, "
        "%d parse errors (%.2fs)",
        stats.files_scanned, stats.added, stats.updated,
        stats.unchanged, stats.parse_errors, stats.duration_s,
    )
    return stats


# ── CodeGraph builder ────────────────────────────────────────────────────────

def _node_id(file_path: str, symbol_name: str) -> str:
    """Canonical node ID: <rel_path>::<qualified_name>."""
    return f"{file_path}::{symbol_name}"


def build_repo_graph(
    repo_path: str | Path,
    *,
    force_reindex: bool = False,
) -> CodeGraph:
    """
    Builds a CodeGraph by:
      1. Running repograph's incremental indexer (tree-sitter AST + resolve pass).
      2. Reading symbols, imports, and refs from the SQLite store.
      3. Converting them into Node / Edge objects.

    All the heavy lifting (multi-language parsing, call-resolution,
    import tracing) is done by repograph itself.
    """
    root = Path(repo_path).resolve()
    ensure_indexed(root, force=force_reindex)

    settings = load_settings(root)
    graph = CodeGraph()

    with Store(settings) as store:
        # ── 1. File-level module nodes ───────────────────────────────────────
        for f in store.all_files():
            fpath = f["path"]
            mod_id = _node_id(fpath, "__module__")
            graph.add_node(Node(
                id=mod_id,
                name=Path(fpath).stem,
                type="module",
                file=fpath,
                line_start=1,
                line_end=1,
                metadata={
                    "lang": f["lang"],
                    "is_test": bool(f["is_test"]),
                    "indexed_at": f["indexed_at"],
                    "size": f["size"],
                    "parse_ok": bool(f["parsed"]),
                },
            ))

        # ── 2. Symbol nodes (functions, classes, methods …) ──────────────────
        sym_rows = store.conn.execute(
            """SELECT s.id, s.name, s.qualified_name, s.kind,
                      s.start_line, s.end_line, s.tags,
                      f.path
               FROM symbols s
               JOIN files f ON f.id = s.file_id
               ORDER BY f.path, s.start_line"""
        ).fetchall()

        sym_id_to_node_id: Dict[int, str] = {}

        for row in sym_rows:
            sym_db_id = row["id"]
            fpath = row["path"]
            qname = row["qualified_name"] or row["name"]
            node_id = _node_id(fpath, qname)
            tags = (row["tags"] or "").split(",") if row["tags"] else []

            node = Node(
                id=node_id,
                name=row["name"],
                type=row["kind"],
                file=fpath,
                line_start=row["start_line"],
                line_end=row["end_line"],
                metadata={"qualified_name": qname, "tags": tags},
            )
            graph.add_node(node)
            sym_id_to_node_id[sym_db_id] = node_id

            # Parent is the module node
            mod_id = _node_id(fpath, "__module__")
            graph.add_edge(Edge(
                source=mod_id,
                target=node_id,
                type="defines",
            ))

        # ── 3. Import edges (file → file) ────────────────────────────────────
        for imp in store.file_edges():
            src_mod = _node_id(imp["src"], "__module__")
            dst_mod = _node_id(imp["dst"], "__module__")
            if src_mod in graph.nodes and dst_mod in graph.nodes:
                graph.add_edge(Edge(
                    source=src_mod,
                    target=dst_mod,
                    type="imports",
                    confidence=imp["confidence"],
                    metadata={
                        "method": imp["method"],
                        "module": imp["module"],
                        "line": imp["line"],
                    },
                ))

        # ── 4. Cross-file ref edges (calls / inherits) ───────────────────────
        ref_rows = store.conn.execute(
            """SELECT r.name, r.line, r.kind, r.confidence, r.method,
                      r.target_name,
                      sf.path AS src_file,
                      tf.path AS target_file
               FROM refs r
               JOIN files sf ON sf.id = r.file_id
               LEFT JOIN files tf ON tf.id = r.target_file_id
               WHERE r.target_file_id IS NOT NULL
               ORDER BY sf.path, r.line
               LIMIT 200000"""
        ).fetchall()

        for ref in ref_rows:
            src_mod = _node_id(ref["src_file"], "__module__")
            target_name = ref["target_name"] or ref["name"]
            dst_id = _node_id(ref["target_file"], target_name)

            # Fallback to module node if exact symbol not found
            if dst_id not in graph.nodes:
                dst_id = _node_id(ref["target_file"], "__module__")

            if src_mod in graph.nodes and dst_id in graph.nodes:
                edge_type = "inherits" if ref["kind"] == "inherits" else "calls"
                graph.add_edge(Edge(
                    source=src_mod,
                    target=dst_id,
                    type=edge_type,
                    confidence=ref["confidence"],
                    metadata={
                        "ref_kind": ref["kind"],
                        "method": ref["method"],
                        "line": ref["line"],
                    },
                ))

    logger.info(
        "CodeGraph built: %d nodes, %d edges", len(graph.nodes), len(graph.edges)
    )
    return graph


# ── Diff file parser ─────────────────────────────────────────────────────────

def parse_diff_files(diff_text: str) -> List[str]:
    """Extracts file paths modified in a unified git diff."""
    files: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            p = line[6:].strip()
            if p and p != "/dev/null":
                files.add(p)
        elif line.startswith("diff --git a/"):
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                p = parts[3][2:].strip()
                if p and p != "/dev/null":
                    files.add(p)
    return sorted(files)


def parse_diff_line_ranges(diff_text: str) -> Dict[str, List[tuple[int, int]]]:
    """Extracts hunk line ranges per file from a unified git diff."""
    HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    hunks: Dict[str, List[tuple[int, int]]] = {}
    cur_file: Optional[str] = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:].strip()
            hunks.setdefault(cur_file, [])
        elif cur_file and line.startswith("@@ "):
            m = HUNK_RE.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                hunks[cur_file].append((start, start + count - 1))

    return hunks
