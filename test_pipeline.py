"""
Integration test for Graphify-Repograph Agent.
Validates the real repograph + Graphify pipeline end-to-end.
"""

import json
from pathlib import Path

REPO_PATH = Path(__file__).parent  # run tests against this very project

def run_pipeline_test():
    print("=" * 65)
    print("Graphify-Repograph Agent — Integration Test (Real APIs)")
    print("=" * 65)

    # ── Member 1: repograph indexer ──────────────────────────────────────────
    print("\n[Member 1] Step 1 — Running repograph incremental indexer …")
    from parser import build_repo_graph, parse_diff_files, parse_diff_line_ranges

    graph = build_repo_graph(REPO_PATH)
    print(f"  → CodeGraph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    assert len(graph.nodes) > 0, "repograph should find at least some symbols"

    node_types = {}
    for n in graph.nodes.values():
        node_types[n.type] = node_types.get(n.type, 0) + 1
    print(f"  → Node kinds: {node_types}")

    # ── Member 1: Graphify bridge & blast radius ─────────────────────────────
    print("\n[Member 1] Step 2 — Graphify Bridge + real analyze_impact() …")
    from bridge import get_repo_context, render_subgraph_image

    SAMPLE_DIFF = """\
--- a/bridge.py
+++ b/bridge.py
@@ -30,4 +30,5 @@
 def get_repo_context(
     repo_path: str | Path,
+    strict_mode: bool = False,
     diff_files: Optional[List[str]] = None,
"""

    ctx = get_repo_context(
        repo_path=REPO_PATH,
        diff_files=["bridge.py"],
        diff_text=SAMPLE_DIFF,
        hops=2,
    )

    graph_meta = ctx.get("graph", {})
    nodes = ctx.get("nodes", [])
    links = ctx.get("links", [])

    print(f"  → graph.schema_version : {graph_meta.get('schema_version')}")
    print(f"  → Nodes in subgraph    : {len(nodes)}")
    print(f"  → Links in subgraph    : {len(links)}")
    print(f"  → Blast radius score   : {graph_meta.get('blast_radius_score')}")
    print(f"  → Direct dependents    : {graph_meta.get('direct_dependent_files', [])[:3]}")
    print(f"  → repograph summary    : {json.dumps(graph_meta.get('repograph_impact_summary', {}), indent=4)}")

    # Validate Graphify schema shape
    assert ctx["graph"]["schema_version"] == 1, "schema_version must be 1"
    assert "nodes" in ctx and "links" in ctx, "must have 'nodes' and 'links' keys"
    for node in nodes[:3]:
        assert "id" in node
        assert "label" in node
        assert "source_file" in node
        assert "_origin" in node
        assert node["_origin"] == "ast"
        print(f"     node sample: {node['id'][:60]}  [{node['impact_status']}]")

    # ── Member 1: Visual topology render ─────────────────────────────────────
    print("\n[Member 1] Step 3 — Rendering visual graph topology PNG …")
    b64 = render_subgraph_image(ctx)
    print(f"  → Base64 PNG length: {len(b64)} chars")
    assert len(b64) > 200, "should produce a non-trivial image"

    # ── Member 2: Gemma 4 review ─────────────────────────────────────────────
    print("\n[Member 2] Step 4 — Gemma 4 multimodal review pipeline …")
    from ai_agent import analyze_pull_request, GemmaReviewOutput

    review = analyze_pull_request(
        diff_str=SAMPLE_DIFF,
        graph_context=ctx,
        graph_image_b64=b64,
    )
    print(f"  → Impact rating       : {review.impact_rating}/10")
    print(f"  → Breaking changes    : {len(review.breaking_changes)}")
    for bc in review.breaking_changes:
        print(f"     • {bc}")
    print(f"  → Architectural summary (excerpt):")
    print(f"     {review.architectural_summary[:160]}…")
    assert isinstance(review, GemmaReviewOutput)

    # ── Member 3: FastAPI server ─────────────────────────────────────────────
    print("\n[Member 3] Step 5 — FastAPI server sanity-check …")
    from server import app
    route_paths = [r.path for r in app.routes]
    print(f"  → Routes registered: {route_paths}")
    assert "/analyze" in route_paths
    assert "/health" in route_paths

    print("\n" + "=" * 65)
    print("ALL 5 DELIVERABLES VERIFIED WITH REAL REPOGRAPH + GRAPHIFY APIs! 🚀")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline_test()
