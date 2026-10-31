"""
Member 3: Dashboard & API Server
Module: server.py
FastAPI server exposing POST /analyze, GET /health, and an interactive D3.js
web interface for real-time AST dependency graph exploration and Gemma 4 review.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from parser import build_repo_graph
from bridge import get_repo_context, render_subgraph_image
from ai_agent import analyze_pull_request, GemmaReviewOutput

app = FastAPI(
    title="Graphify-Repograph Agent",
    description="Multimodal AST-aware code review agent powered by Gemma 4 and Graphify",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    repo_path: Optional[str] = Field(None, description="Local path or cloned repository directory")
    git_diff: str = Field(..., description="Unified Git diff string representing incoming changes")
    diff_files: Optional[List[str]] = Field(None, description="Optional explicit list of modified files")
    generate_image: bool = Field(True, description="Whether to render base64 graph topology for Gemma 4")
    model_name: Optional[str] = Field(None, description="Model identifier override (defaults to gemma-4)")


class AnalyzeResponse(BaseModel):
    review: GemmaReviewOutput
    graph: Dict[str, Any]
    graph_image_b64: Optional[str] = None
    stats: Dict[str, Any]


@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Health check endpoint for Cloudways / DigitalOcean monitoring."""
    return {
        "status": "healthy",
        "service": "graphify-repograph-agent",
        "version": "1.0.0",
        "model": os.getenv("GEMMA_MODEL", "gemma-4")
    }


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Review"])
async def analyze_code(request: AnalyzeRequest):
    """
    Core Pipeline Endpoint:
    1. Member 1: Builds AST graph of repo_path and computes Graphify blast radius.
    2. Member 1: Renders multimodal base64 graph topology PNG.
    3. Member 2: Sends diff + graph context + image to Gemma 4 via Gemini API.
    4. Returns combined review and graph JSON.
    """
    repo_path = request.repo_path

    # If no repo_path provided, create a temporary directory or use current workspace
    if not repo_path or not Path(repo_path).exists():
        repo_path = os.getcwd()

    try:
        # Step 1: Member 1 - Graphify Bridge Context & Subgraph
        graph_context = get_repo_context(
            repo_path=repo_path,
            diff_files=request.diff_files,
            diff_text=request.git_diff,
            hops=2
        )

        # Step 2: Member 1 - Visual Graph Topology Render
        graph_image_b64 = None
        if request.generate_image:
            try:
                graph_image_b64 = render_subgraph_image(graph_context)
            except Exception as img_err:
                # Non-fatal image fallback
                pass

        # Step 3: Member 2 - Gemma 4 Multimodal Reasoning
        review_result = analyze_pull_request(
            diff_str=request.git_diff,
            graph_context=graph_context,
            graph_image_b64=graph_image_b64,
            model_name=request.model_name
        )

        # Graphify schema uses "graph" for metadata (schema_version:1)
        graph_meta = graph_context.get("graph", graph_context.get("stats", {}))

        return AnalyzeResponse(
            review=review_result,
            graph=graph_context,
            graph_image_b64=graph_image_b64,
            stats=graph_meta
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/api/demo-payload", tags=["Demo"])
async def get_demo_payload():
    """Supplies a sample repository snippet and breaking diff for 1-click live judging."""
    sample_diff = """--- a/services/payment.py
+++ b/services/payment.py
@@ -10,3 +10,4 @@
-def process_transaction(user_id: str, amount: float) -> bool:
+def process_transaction(user_id: str, amount: float, currency_code: str, idempotency_key: str) -> bool:
+    # Breaking change: added required arguments without defaults
     pass
"""
    return {
        "repo_path": ".",
        "git_diff": sample_diff,
        "diff_files": ["services/payment.py"]
    }


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_dashboard():
    """Serves the interactive D3.js and Gemma 4 live visual dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Graphify-Repograph Agent | Gemma 4 AST Review</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    :root {
      --bg-dark: #090d16;
      --bg-card: rgba(17, 24, 39, 0.75);
      --bg-card-border: rgba(255, 255, 255, 0.08);
      --accent-cyan: #06b6d4;
      --accent-indigo: #6366f1;
      --accent-pink: #ec4899;
      --color-modified: #ef4444;
      --color-direct: #f59e0b;
      --color-indirect: #3b82f6;
      --color-unchanged: #6b7280;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg-dark);
      color: var(--text-main);
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    /* Header Bar */
    header {
      height: 64px;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--bg-card-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      z-index: 50;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-logo {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, var(--accent-indigo), var(--accent-cyan));
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      color: #fff;
      box-shadow: 0 0 16px rgba(99, 102, 241, 0.5);
    }

    .brand-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
      background: linear-gradient(90deg, #fff, #cbd5e1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .brand-badge {
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.4);
      color: #a5b4fc;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 999px;
      font-weight: 600;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .btn {
      font-family: inherit;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.06);
      color: #cbd5e1;
      border: 1px solid var(--bg-card-border);
    }
    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }

    .btn-primary {
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      color: #fff;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
    }
    .btn-primary:hover {
      box-shadow: 0 6px 18px rgba(99, 102, 241, 0.5);
      transform: translateY(-1px);
    }

    /* Main Grid Layout */
    .app-container {
      flex: 1;
      display: grid;
      grid-template-columns: 360px 1fr 420px;
      height: calc(100vh - 64px);
      position: relative;
    }

    /* Left Sidebar: Diff Input */
    .sidebar {
      background: rgba(15, 23, 42, 0.6);
      border-right: 1px solid var(--bg-card-border);
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      overflow-y: auto;
    }

    .panel-title {
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #94a3b8;
    }

    .form-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .form-label {
      font-size: 12px;
      font-weight: 600;
      color: #cbd5e1;
    }

    .input-field {
      width: 100%;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      padding: 10px 12px;
      color: #f1f5f9;
      font-family: inherit;
      font-size: 13px;
    }
    .input-field:focus {
      outline: none;
      border-color: var(--accent-indigo);
    }

    textarea.input-field {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      resize: vertical;
      min-height: 220px;
      line-height: 1.5;
    }

    /* Center Canvas: D3 Graph */
    .graph-viewport {
      position: relative;
      background: radial-gradient(circle at 50% 50%, #172033 0%, #090d16 100%);
      overflow: hidden;
    }

    #graph-svg {
      width: 100%;
      height: 100%;
    }

    .graph-overlay-stats {
      position: absolute;
      top: 16px;
      left: 16px;
      display: flex;
      gap: 10px;
      z-index: 10;
    }

    .stat-pill {
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(8px);
      border: 1px solid var(--bg-card-border);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .stat-val { font-weight: 700; color: #fff; }

    .graph-legend {
      position: absolute;
      bottom: 20px;
      left: 20px;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--bg-card-border);
      border-radius: 8px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 11px;
      z-index: 10;
    }
    .legend-item { display: flex; align-items: center; gap: 8px; }
    .legend-dot { width: 10px; height: 10px; border-radius: 50%; }

    /* Right Drawer: Gemma 4 Review */
    .review-drawer {
      background: rgba(15, 23, 42, 0.95);
      border-left: 1px solid var(--bg-card-border);
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .impact-meter-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--bg-card-border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .gauge-circle {
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: conic-gradient(var(--color-modified) 0deg 280deg, rgba(255,255,255,0.1) 280deg 360deg);
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .gauge-circle::before {
      content: '';
      position: absolute;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #0f172a;
    }
    .gauge-value {
      position: relative;
      font-size: 20px;
      font-weight: 800;
      color: #fff;
    }

    .breaking-card {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      border-radius: 10px;
      padding: 14px;
    }
    .breaking-title {
      color: #f87171;
      font-size: 13px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
    }
    .breaking-list {
      padding-left: 18px;
      font-size: 12px;
      color: #fca5a5;
      line-height: 1.6;
    }

    .summary-card {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--bg-card-border);
      border-radius: 10px;
      padding: 16px;
    }
    .summary-text {
      font-size: 13px;
      line-height: 1.6;
      color: #cbd5e1;
    }

    .patch-box {
      background: #050811;
      border: 1px solid var(--bg-card-border);
      border-radius: 8px;
      padding: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #a5f3fc;
      max-height: 200px;
      overflow-x: auto;
      overflow-y: auto;
      white-space: pre;
    }

    /* Node tooltip */
    .tooltip {
      position: absolute;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 12px;
      pointer-events: none;
      z-index: 100;
      display: none;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">G</div>
      <div>
        <div class="brand-title">Graphify-Repograph Agent</div>
        <div style="font-size: 11px; color: var(--text-muted);">Multimodal AST Code Review with Gemma 4</div>
      </div>
      <div class="brand-badge">Hacktoberfest Hack Day</div>
    </div>
    <div class="header-actions">
      <button class="btn btn-secondary" onclick="loadDemoPayload()">⚡ Load Demo PR</button>
      <button class="btn btn-primary" id="run-btn" onclick="executeReview()">▶ Run Gemma 4 Review</button>
    </div>
  </header>

  <div class="app-container">
    <!-- Left Sidebar: PR Diff Input -->
    <div class="sidebar">
      <div class="panel-title">PR Context &amp; Diff</div>
      <div class="form-group">
        <label class="form-label">Repository Root</label>
        <input type="text" id="repo-path" class="input-field" value="." placeholder="/path/to/repo">
      </div>
      <div class="form-group" style="flex: 1; display: flex; flex-direction: column;">
        <label class="form-label">Git Unified Diff</label>
        <textarea id="diff-input" class="input-field" style="flex: 1;" placeholder="Paste unified diff here..."></textarea>
      </div>
    </div>

    <!-- Center Viewport: D3 AST Dependency Graph -->
    <div class="graph-viewport">
      <div class="graph-overlay-stats">
        <div class="stat-pill">Nodes: <span class="stat-val" id="stat-nodes">0</span></div>
        <div class="stat-pill">Edges: <span class="stat-val" id="stat-edges">0</span></div>
        <div class="stat-pill">Blast Radius: <span class="stat-val" id="stat-blast">0</span></div>
      </div>

      <svg id="graph-svg"></svg>

      <div class="graph-legend">
        <div class="legend-item"><div class="legend-dot" style="background: var(--color-modified);"></div> Modified (Diff)</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--color-direct);"></div> 1-Hop Caller / Dependent</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--color-indirect);"></div> 2-Hop Caller</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--color-unchanged);"></div> Unchanged Context</div>
      </div>

      <div id="tooltip" class="tooltip"></div>
    </div>

    <!-- Right Drawer: Gemma 4 Review Results -->
    <div class="review-drawer">
      <div class="panel-title">Gemma 4 Multi-Modal Assessment</div>

      <!-- Impact Score -->
      <div class="impact-meter-card">
        <div>
          <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700;">Blast Severity</div>
          <div style="font-size: 18px; font-weight: 800; color: #fff;" id="impact-label">Pending Run</div>
        </div>
        <div class="gauge-circle" id="gauge-circle">
          <div class="gauge-value" id="impact-number">-</div>
        </div>
      </div>

      <!-- Breaking Changes -->
      <div class="breaking-card">
        <div class="breaking-title">⚠ Detected Breaking Changes</div>
        <ul class="breaking-list" id="breaking-list">
          <li>Submit a pull request diff to trigger AST evaluation.</li>
        </ul>
      </div>

      <!-- Architectural Summary -->
      <div class="summary-card">
        <div style="font-size: 12px; font-weight: 700; color: #cbd5e1; margin-bottom: 8px;">Architectural Topology Impact</div>
        <div class="summary-text" id="summary-text">Gemma 4 will analyze caller/callee AST edges and call graph propagation.</div>
      </div>

      <!-- Patch Recommendation -->
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <div style="font-size: 12px; font-weight: 700; color: #cbd5e1;">Patch Recommendation</div>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="copyPatch()">Copy Diff</button>
        </div>
        <div class="patch-box" id="patch-box"># Recommended unified patch will appear here</div>
      </div>
    </div>
  </div>

  <script>
    let currentSimulation = null;

    async function loadDemoPayload() {
      try {
        const res = await fetch('/api/demo-payload');
        const data = await res.json();
        document.getElementById('repo-path').value = data.repo_path;
        document.getElementById('diff-input').value = data.git_diff;
      } catch (e) {
        console.error("Demo load error:", e);
      }
    }

    async function executeReview() {
      const runBtn = document.getElementById('run-btn');
      runBtn.innerText = 'Analyzing...';
      runBtn.disabled = true;

      const payload = {
        repo_path: document.getElementById('repo-path').value,
        git_diff: document.getElementById('diff-input').value,
        generate_image: true
      };

      try {
        const response = await fetch('/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          throw new Error('Analysis failed: ' + response.statusText);
        }

        const data = await response.json();
        updateDashboard(data);
      } catch (err) {
        alert('Analysis error: ' + err.message);
      } finally {
        runBtn.innerText = '▶ Run Gemma 4 Review';
        runBtn.disabled = false;
      }
    }

    function updateDashboard(data) {
      const review = data.review;
      const graph = data.graph;
      const stats = data.stats || {};

      // Update counters — Graphify schema uses 'links' not 'edges'
      document.getElementById('stat-nodes').innerText = graph.nodes ? graph.nodes.length : 0;
      const links = graph.links || graph.edges || [];
      document.getElementById('stat-edges').innerText = links.length;
      document.getElementById('stat-blast').innerText =
        stats.blast_radius_score || (graph.graph && graph.graph.blast_radius_score) || review.impact_rating;

      // Update Impact Rating Gauge
      const rating = review.impact_rating || 1;
      document.getElementById('impact-number').innerText = rating + '/10';
      const deg = Math.round((rating / 10) * 360);
      const color = rating >= 7 ? '#ef4444' : (rating >= 4 ? '#f59e0b' : '#10b981');
      document.getElementById('gauge-circle').style.background = `conic-gradient(${color} 0deg ${deg}deg, rgba(255,255,255,0.1) ${deg}deg 360deg)`;
      document.getElementById('impact-label').innerText = rating >= 7 ? 'Critical Impact' : (rating >= 4 ? 'Moderate Blast' : 'Contained Change');
      document.getElementById('impact-label').style.color = color;

      // Breaking changes
      const bList = document.getElementById('breaking-list');
      bList.innerHTML = '';
      (review.breaking_changes || []).forEach(item => {
        const li = document.createElement('li');
        li.innerText = item;
        bList.appendChild(li);
      });
      if ((review.breaking_changes || []).length === 0) {
        bList.innerHTML = '<li>Zero breaking changes detected in AST graph.</li>';
      }

      // Summary
      document.getElementById('summary-text').innerText = review.architectural_summary || 'Evaluation completed.';

      // Patch recommendation
      document.getElementById('patch-box').innerText = review.patch_recommendation || '# No diff adjustments required.';

      // Render D3 Graph
      renderGraph(graph);
    }

    function renderGraph(graphData) {
      const svg = d3.select("#graph-svg");
      svg.selectAll("*").remove();

      const width = document.querySelector(".graph-viewport").clientWidth;
      const height = document.querySelector(".graph-viewport").clientHeight;
      const tooltip = d3.select("#tooltip");

      const nodes = (graphData.nodes || []).map(d => ({ ...d }));
      // Graphify real schema uses 'links'; fall back to 'edges' for compat
      const edges = (graphData.links || graphData.edges || []).map(d => ({ ...d }));

      const g = svg.append("g");

      // Zoom & Pan
      const zoom = d3.zoom()
        .scaleExtent([0.2, 4])
        .on("zoom", (event) => g.attr("transform", event.transform));
      svg.call(zoom);

      // Define Arrow Markers
      svg.append("defs").selectAll("marker")
        .data(["calls", "defines", "imports", "inherits"])
        .enter().append("marker")
        .attr("id", d => "arrow-" + d)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 22)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#64748b");

      const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(edges).id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(35));

      currentSimulation = simulation;

      // Draw Edges
      const link = g.append("g")
        .attr("stroke", "#475569")
        .attr("stroke-opacity", 0.6)
        .selectAll("line")
        .data(edges)
        .enter().append("line")
        .attr("stroke-width", 1.5)
        .attr("marker-end", d => "url(#arrow-" + (d.relation || d.type || "calls") + ")");

      // Draw Nodes
      const node = g.append("g")
        .selectAll("g")
        .data(nodes)
        .enter().append("g")
        .call(d3.drag()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x; d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          }));

      // Node Circles with impact-based coloring
      node.append("circle")
        .attr("r", d => d.type === 'module' ? 14 : 10)
        .attr("fill", d => {
          if (d.impact_status === 'modified') return '#ef4444';
          if (d.impact_status === 'direct_dependent') return '#f59e0b';
          if (d.impact_status === 'indirect_dependent') return '#3b82f6';
          return '#6b7280';
        })
        .attr("stroke", "#fff")
        .attr("stroke-width", 2)
        .style("filter", d => d.impact_status === 'modified' ? 'drop-shadow(0px 0px 6px #ef4444)' : 'none');

      // Node Labels
      node.append("text")
        .text(d => (d.label || d.id).split("::").pop())
        .attr("x", 14)
        .attr("y", 4)
        .attr("fill", "#f8fafc")
        .attr("font-size", "11px")
        .attr("font-weight", "600")
        .attr("font-family", "Plus Jakarta Sans, sans-serif");

      // Hover Tooltip
      node.on("mouseover", (event, d) => {
        tooltip.style("display", "block")
          .html(`
            <div style="font-weight:700; color:#fff;">${d.label || d.id}</div>
            <div style="color:#94a3b8; font-size:11px;">Type: ${d.type} | File: ${d.file}</div>
            <div style="color:#38bdf8; font-size:11px;">Lines: ${d.start_line}-${d.end_line}</div>
            <div style="color:#f59e0b; font-size:11px;">Impact: ${d.impact_status}</div>
          `);
      })
      .on("mousemove", (event) => {
        tooltip.style("left", (event.pageX + 15) + "px")
               .style("top", (event.pageY - 25) + "px");
      })
      .on("mouseout", () => tooltip.style("display", "none"));

      simulation.on("tick", () => {
        link
          .attr("x1", d => d.source.x)
          .attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x)
          .attr("y2", d => d.target.y);

        node
          .attr("transform", d => `translate(${d.x},${d.y})`);
      });
    }

    function copyPatch() {
      const text = document.getElementById('patch-box').innerText;
      navigator.clipboard.writeText(text);
      alert('Patch copied to clipboard!');
    }

    // Auto-load demo on startup
    window.addEventListener('DOMContentLoaded', loadDemoPayload);
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
