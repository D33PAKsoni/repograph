"""
Member 1 (You): Graphify Bridge — bridge.py
============================================
Converts repograph impact analysis results into the REAL Graphify graph.json
schema (schema_version: 1, nodes + links) as used by Graphify-Labs/graphify.

The Graphify schema uses:
  • "nodes"  – list of {id, label, source_file, source_location, _origin, …}
  • "links"  – list of {source, target, relation, …}
  • "graph"  – metadata envelope {schema_version: 1, …}

Exposes:
  get_repo_context(repo_path, diff_files, diff_text, hops) → Graphify JSON dict
  render_subgraph_image(graphify_data)                      → base64 PNG string
"""

from __future__ import annotations

import base64
import io
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Real repograph API ──────────────────────────────────────────────────────
from repograph.indexer import index_repository
from repograph.store import Store
from repograph.config import load_settings
from repograph.impact import analyze_impact

# ── Our parser layer ────────────────────────────────────────────────────────
from parser import (
    build_repo_graph, CodeGraph, Node, Edge,
    parse_diff_files, parse_diff_line_ranges,
)

logger = logging.getLogger("bridge")

# ── Graphify schema constants ─────────────────────────────────────────────────
GRAPHIFY_SCHEMA_VERSION = 1


# ─────────────────────────────────────────────────────────────────────────────
# Graphify schema helpers
# ─────────────────────────────────────────────────────────────────────────────

def _graphify_node(
    node_id: str,
    label: str,
    source_file: str,
    source_location: Optional[str],
    node_type: str,
    impact_status: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Constructs a Graphify-compliant node dict."""
    return {
        "id": node_id,
        "label": label,
        "source_file": source_file,
        "source_location": source_location,   # "L<line>" or None
        "_origin": "ast",                      # repograph is deterministic AST
        "type": node_type,
        "impact_status": impact_status,        # extended field for our agent
        **(metadata or {}),
    }


def _graphify_link(
    source: str,
    target: str,
    relation: str,
    confidence: str = "confirmed",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Constructs a Graphify-compliant link dict."""
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": confidence,
        **(metadata or {}),
    }


def _graphify_envelope(
    nodes: List[Dict[str, Any]],
    links: List[Dict[str, Any]],
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Wraps nodes and links in the Graphify graph.json top-level schema."""
    graph_meta: Dict[str, Any] = {
        "schema_version": GRAPHIFY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "graphify-repograph-agent",
    }
    if extra_meta:
        graph_meta.update(extra_meta)

    return {
        "graph": graph_meta,
        "nodes": nodes,
        "links": links,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Blast radius computation using repograph's analyze_impact
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_diff_path(path: str) -> str:
    """Strips leading a/ b/ from git diff paths."""
    return re.sub(r"^[ab]/", "", path).strip()


def _compute_blast_radius(
    root: Path,
    diff_files: List[str],
    diff_text: Optional[str],
    hops: int = 2,
) -> Dict[str, Any]:
    """
    Uses repograph's real analyze_impact() to compute the blast radius.
    Returns the full repograph impact payload.
    """
    settings = load_settings(root)
    with Store(settings) as store:
        # Normalize paths relative to repo root
        normalized_paths = []
        for p in diff_files:
            norm = _normalize_diff_path(p)
            # Accept both absolute and relative — repograph uses relative posix
            normalized_paths.append(norm)

        result = analyze_impact(
            store,
            root,
            paths=normalized_paths if normalized_paths else None,
            depth=min(hops, 5),
            include_tests=True,
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main public API: get_repo_context
# ─────────────────────────────────────────────────────────────────────────────

def get_repo_context(
    repo_path: str | Path,
    diff_files: Optional[List[str]] = None,
    diff_text: Optional[str] = None,
    hops: int = 2,
) -> Dict[str, Any]:
    """
    Builds a Graphify-compliant graph.json subgraph for the blast radius
    of the incoming diff, powered by repograph's real SQLite index.

    Steps:
      1. Ensure the repository is indexed (repograph incremental indexer).
      2. Derive diff_files from diff_text if not explicitly provided.
      3. Call repograph's analyze_impact() for true caller/dependent resolution.
      4. Build our CodeGraph from the full index.
      5. Tag nodes with their impact_status.
      6. Emit Graphify schema: {graph: {…}, nodes: […], links: […]}.
    """
    root = Path(repo_path).resolve()

    # ── 1. Parse diff text for files + hunk ranges ───────────────────────────
    line_ranges: Dict[str, List[Tuple[int, int]]] = {}
    if diff_text:
        derived = parse_diff_files(diff_text)
        line_ranges = parse_diff_line_ranges(diff_text)
        if not diff_files:
            diff_files = derived
        else:
            diff_files = list(set(diff_files) | set(derived))

    diff_files = diff_files or []

    # ── 2. Index repository (incremental) ────────────────────────────────────
    try:
        index_repository(root)
    except Exception as idx_err:
        logger.warning("repograph indexing failed: %s — continuing with cached index.", idx_err)

    # ── 3. Build in-memory CodeGraph ─────────────────────────────────────────
    try:
        code_graph = build_repo_graph(root)
    except Exception as cg_err:
        logger.error("CodeGraph build failed: %s", cg_err)
        code_graph = CodeGraph()

    # ── 4. Compute blast radius via repograph's analyze_impact ───────────────
    impact_payload: Dict[str, Any] = {}
    direct_dependent_paths: set[str] = set()
    transitive_dependent_paths: set[str] = set()

    if diff_files:
        try:
            impact_payload = _compute_blast_radius(root, diff_files, diff_text, hops)
            direct_dependent_paths = {
                d["path"] for d in impact_payload.get("direct_dependents", [])
            }
            transitive_dependent_paths = {
                d["path"] for d in impact_payload.get("transitive_dependents", [])
            }
        except Exception as imp_err:
            logger.warning("analyze_impact failed: %s — proceeding without blast radius.", imp_err)

    # Normalize diff file paths for matching
    norm_diff_files = {_normalize_diff_path(f) for f in diff_files}

    # ── 5. Tag node impact_status ─────────────────────────────────────────────
    def _status(node: Node) -> str:
        nf = node.file.replace("\\", "/")
        if any(nf == df or nf.endswith("/" + df) or df.endswith("/" + nf) for df in norm_diff_files):
            # Check hunk line overlap if we have ranges
            hunks = line_ranges.get(nf) or next(
                (line_ranges[k] for k in line_ranges if nf.endswith(k) or k.endswith(nf)), []
            )
            if hunks:
                if any(node.line_start <= e and node.line_end >= s for s, e in hunks):
                    return "modified"
                return "unchanged"
            return "modified"
        if nf in direct_dependent_paths or any(nf.endswith("/" + d) or d.endswith("/" + nf) for d in direct_dependent_paths):
            return "direct_dependent"
        if nf in transitive_dependent_paths or any(nf.endswith("/" + d) or d.endswith("/" + nf) for d in transitive_dependent_paths):
            return "indirect_dependent"
        return "unchanged"

    # ── 6. Subgraph selection ─────────────────────────────────────────────────
    #    Include: modified, direct dependents, indirect dependents.
    #    If nothing flagged, include entire graph.
    tagged: Dict[str, str] = {nid: _status(n) for nid, n in code_graph.nodes.items()}
    relevant_ids = {nid for nid, s in tagged.items() if s != "unchanged"}

    if not relevant_ids:
        # Entire graph (small repo or no diff files matched the index)
        relevant_ids = set(code_graph.nodes.keys())

    # ── 7. Build Graphify nodes ───────────────────────────────────────────────
    graphify_nodes: List[Dict[str, Any]] = []
    for nid in relevant_ids:
        node = code_graph.nodes[nid]
        status = tagged.get(nid, "unchanged")
        source_location = f"L{node.line_start}" if node.line_start else None
        graphify_nodes.append(_graphify_node(
            node_id=nid,
            label=node.name,
            source_file=node.file,
            source_location=source_location,
            node_type=node.type,
            impact_status=status,
            metadata={
                "start_line": node.line_start,
                "end_line": node.line_end,
                "node_metadata": node.metadata,
            },
        ))

    # ── 8. Build Graphify links ───────────────────────────────────────────────
    graphify_links: List[Dict[str, Any]] = []
    for edge in code_graph.edges:
        if edge.source in relevant_ids and edge.target in relevant_ids:
            graphify_links.append(_graphify_link(
                source=edge.source,
                target=edge.target,
                relation=edge.type,
                confidence=edge.confidence,
                metadata=edge.metadata,
            ))

    # ── 9. Assemble envelope with repograph impact metadata ───────────────────
    modified_count = sum(1 for s in tagged.values() if s == "modified")
    direct_count = len(direct_dependent_paths)
    transitive_count = len(transitive_dependent_paths)
    blast_score = min(10, max(1, modified_count * 2 + direct_count + transitive_count // 2))

    extra_meta = {
        "diff_files": diff_files,
        "modified_node_count": modified_count,
        "direct_dependent_files": sorted(direct_dependent_paths)[:20],
        "transitive_dependent_files": sorted(transitive_dependent_paths)[:20],
        "blast_radius_score": blast_score,
        "repograph_impact_summary": impact_payload.get("summary", {}),
        "repograph_blind_spots": impact_payload.get("blind_spots", []),
        "node_count": len(graphify_nodes),
        "link_count": len(graphify_links),
    }

    result = _graphify_envelope(graphify_nodes, graphify_links, extra_meta)

    logger.info(
        "Graphify context: %d nodes, %d links, blast_score=%d",
        len(graphify_nodes), len(graphify_links), blast_score,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Visual topology renderer (for Gemma 4 multimodal input)
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "modified": "#ef4444",
    "direct_dependent": "#f59e0b",
    "indirect_dependent": "#3b82f6",
    "unchanged": "#6b7280",
}


def render_subgraph_image(graphify_data: Dict[str, Any]) -> str:
    """
    Renders the Graphify subgraph (nodes + links) into a base64 PNG for
    Gemma 4's multimodal visual reasoning pass.

    Nodes are color-coded by impact_status:
      red    → modified (touched by the PR diff)
      orange → direct_dependent (1-hop caller/importer)
      blue   → indirect_dependent (2-hop transitive)
      gray   → unchanged context
    """
    nodes = graphify_data.get("nodes", [])
    links = graphify_data.get("links", [])

    if not nodes:
        return ""

    G: nx.DiGraph = nx.DiGraph()
    node_colors: List[str] = []
    node_sizes: List[int] = []
    labels: Dict[str, str] = {}

    for n in nodes:
        nid = n["id"]
        status = n.get("impact_status", "unchanged")
        ntype = n.get("type", "function")
        G.add_node(nid, label=n.get("label", nid), status=status, type=ntype)
        node_colors.append(_STATUS_COLORS.get(status, "#9ca3af"))
        node_sizes.append(900 if ntype == "module" else 600)
        labels[nid] = (n.get("label") or nid).split("::")[-1][:18]

    for lnk in links:
        s, t = lnk.get("source"), lnk.get("target")
        if s and t and s in G and t in G:
            G.add_edge(s, t, relation=lnk.get("relation", ""))

    fig, ax = plt.subplots(figsize=(11, 7), dpi=130)
    fig.patch.set_facecolor("#0a0f1e")
    ax.set_facecolor("#0a0f1e")

    try:
        pos = nx.spring_layout(G, k=1.2, seed=42, iterations=60)
    except Exception:
        pos = nx.circular_layout(G)

    nx.draw_networkx_nodes(
        G, pos,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#ffffff",
        linewidths=1.8,
        ax=ax,
    )
    nx.draw_networkx_edges(
        G, pos,
        edge_color="#475569",
        arrows=True,
        arrowsize=16,
        arrowstyle="-|>",
        connectionstyle="arc3,rad=0.08",
        width=1.3,
        ax=ax,
    )
    nx.draw_networkx_labels(
        G, pos,
        labels=labels,
        font_size=8,
        font_color="#f8fafc",
        font_family="sans-serif",
        font_weight="bold",
        ax=ax,
    )

    legend_handles = [
        mpatches.Patch(color=c, label=lbl)
        for lbl, c in [
            ("Modified (PR diff)", "#ef4444"),
            ("Direct dependent (1-hop)", "#f59e0b"),
            ("Indirect dependent (2-hop)", "#3b82f6"),
            ("Unchanged context", "#6b7280"),
        ]
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper right",
        facecolor="#1e293b",
        edgecolor="#334155",
        labelcolor="#e2e8f0",
        fontsize=8,
        framealpha=0.9,
    )

    meta = graphify_data.get("graph", {})
    blast = meta.get("blast_radius_score", "?")
    mod = meta.get("modified_node_count", "?")
    ax.set_title(
        f"Graphify AST Blast Radius  |  Modified: {mod}  |  Blast Score: {blast}/10",
        color="#f8fafc",
        fontsize=11,
        pad=14,
        fontweight="bold",
    )
    ax.axis("off")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
