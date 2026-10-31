# Graphify-Repograph Agent 🧠🕸️

> **Hacktoberfest Hack Day Flagship Project**  
> A self-hosted, multimodal code review agent that converts real repositories into graph-aware contexts using the **real** [repograph](https://github.com/D33PAKsoni/repograph) + [Graphify](https://github.com/Graphify-Labs/graphify) stacks, evaluates incoming PRs with **Gemma 4** via the Gemini API, and deploys live to **Cloudways by DigitalOcean**.

---

## 🏆 Challenge Tracks

| Track | Approach |
|---|---|
| **Best Open-Source AI Project** | Deterministic tree-sitter AST extraction via the **real repograph** library. No embeddings, no hallucinations — every call/import edge comes from repograph's SQLite index. |
| **Best Use of Gemma 4** | Multimodal: unified git diff + Graphify JSON context + base64 topology diagram → Gemma 4 → typed JSON review schema. |
| **Best Use of Graphify** | Bridges repograph's `analyze_impact()` into the real **Graphify `graph.json` schema** (`schema_version: 1`, `nodes` + `links`, `_origin: "ast"`). |
| **Best Use of Cloudways** | Automated `deploy.sh` using Cloudways REST API v1 (OAuth token → git pull → operation polling → healthcheck). |

---

## 👥 3-Member Team Allocation

```
┌───────────────────────────────────────────────────────────────┐
│              GRAPHIFY-REPOGRAPH AGENT                         │
└───────────────────────────────────────────────────────────────┘

[ MEMBER 1 — YOU ] Core Graph Engine
  parser.py  — CodeGraph adapter over repograph's SQLite indexer
               Uses: repograph.indexer, repograph.store, repograph.impact
  bridge.py  — Graphify schema_version:1 bridge
               Uses: repograph.impact.analyze_impact()
               Emits: {graph:{schema_version:1}, nodes:[…], links:[…]}

[ MEMBER 2 ] AI Reasoning Pipeline
  ai_agent.py — Gemma 4 via google-genai SDK
                Input:  diff_str + graph_context (Graphify JSON) + image
                Output: {impact_rating, breaking_changes,
                         architectural_summary, patch_recommendation}

[ MEMBER 3 ] Dashboard & Deployment
  server.py  — FastAPI: POST /analyze · GET /health · GET / (D3.js)
  Dockerfile — Multi-stage, non-root, health-probed container
  deploy.sh  — Cloudways REST API v1 automated deployment
```

---

## 🔗 Real Upstream Repositories

| Role | Repo | What we use |
|---|---|---|
| **Indexer & Impact Engine** | [D33PAKsoni/repograph](https://github.com/D33PAKsoni/repograph) | `index_repository()`, `Store`, `analyze_impact()` |
| **Graph Schema** | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | `graph.json` schema v1 (`nodes` + `links` + `graph.schema_version`) |

---

## 📂 File Reference

| File | Owner | Purpose |
|---|---|---|
| [`parser.py`](file:///home/darion-dev/Dev/Incubator/repograph/parser.py) | Member 1 | Thin adapter over **real** repograph indexer. Reads symbols, imports, refs from SQLite store → `CodeGraph` |
| [`bridge.py`](file:///home/darion-dev/Dev/Incubator/repograph/bridge.py) | Member 1 | Runs `analyze_impact()` for blast radius. Emits real **Graphify** `graph.json` schema v1 with `nodes`/`links` |
| [`ai_agent.py`](file:///home/darion-dev/Dev/Incubator/repograph/ai_agent.py) | Member 2 | Gemma 4 multimodal review pipeline via `google-genai` SDK |
| [`server.py`](file:///home/darion-dev/Dev/Incubator/repograph/server.py) | Member 3 | FastAPI server + D3.js live dashboard |
| [`Dockerfile`](file:///home/darion-dev/Dev/Incubator/repograph/Dockerfile) | Member 3 | Production multi-stage container |
| [`deploy.sh`](file:///home/darion-dev/Dev/Incubator/repograph/deploy.sh) | Member 3 | Cloudways REST API v1 deployment automation |

---

## 🚀 Quickstart

### 1. Clone upstream forks
```bash
# Clone this repo
git clone https://github.com/D33PAKsoni/repograph.git
cd repograph

# Install real repograph (editable, so you can contribute back)
pip install -e /path/to/repograph-upstream

# Install graphify (if contributing to schema bridge)
pip install -e /path/to/graphify-upstream

# Install remaining project deps
pip install -r requirements.txt
```

### 2. Set Gemma 4 API key (optional — runs offline without it)
```bash
export GEMINI_API_KEY="your-google-gemini-api-key"
export GEMMA_MODEL="gemma-4"
```

### 3. Run integration test
```bash
python3 test_pipeline.py
```

Expected output (abridged):
```
[Member 1] Step 1 — Running repograph incremental indexer …
  → CodeGraph: 41 nodes, 94 edges
  → Node kinds: {'module': 5, 'class': 6, 'function': 22, 'method': 8}
[Member 1] Step 2 — Graphify Bridge + real analyze_impact() …
  → graph.schema_version : 1
  → Nodes in subgraph    : 9
  → Links in subgraph    : 10
  → Blast radius score   : 2
  → Direct dependents    : ['server.py', 'test_pipeline.py']
[Member 2] Step 4 — Gemma 4 multimodal review pipeline …
  → Impact rating       : 9/10
ALL 5 DELIVERABLES VERIFIED WITH REAL REPOGRAPH + GRAPHIFY APIs! 🚀
```

### 4. Start local server + dashboard
```bash
python3 server.py
# → http://localhost:8000
```
Click **⚡ Load Demo PR** → **▶ Run Gemma 4 Review** to see the live D3.js blast radius graph and review drawer.

---

## ☁️ Cloudways by DigitalOcean Deployment

```bash
export CLOUDWAYS_EMAIL="developer@example.com"
export CLOUDWAYS_API_KEY="<your-cloudways-api-key>"
export CLOUDWAYS_SERVER_ID="123456"
export CLOUDWAYS_APP_ID="654321"
export APP_LIVE_URL="https://phpstack-xxxx.cloudwaysapps.com"

./deploy.sh --live-url "$APP_LIVE_URL"
```

The script:
1. `POST /oauth/access_token` → bearer token
2. `POST /git/pull` → triggers Git deployment on the Cloudways server
3. Polls `GET /operation/{id}` until `status == completed`
4. Hits `${APP_LIVE_URL}/health` to confirm the app is live

---

## 📡 API Reference

### `POST /analyze`
```json
{
  "repo_path": ".",
  "git_diff": "--- a/app.py\n+++ b/app.py\n@@ -10,3 +10,4 ...",
  "diff_files": ["app.py"],
  "generate_image": true
}
```

**Response (Graphify schema_version:1):**
```json
{
  "review": {
    "impact_rating": 8,
    "breaking_changes": ["…"],
    "architectural_summary": "…",
    "patch_recommendation": "--- a/app.py\n+++ b/app.py\n…"
  },
  "graph": {
    "graph": {
      "schema_version": 1,
      "blast_radius_score": 8,
      "repograph_impact_summary": { "direct_dependents": 5, "…": "…" }
    },
    "nodes": [
      { "id": "app.py::process", "label": "process",
        "source_file": "app.py", "source_location": "L42",
        "_origin": "ast", "impact_status": "modified" }
    ],
    "links": [
      { "source": "app.py::process", "target": "utils.py::__module__",
        "relation": "calls", "confidence": "confirmed" }
    ]
  },
  "graph_image_b64": "iVBORw0KGgo…",
  "stats": { "schema_version": 1, "blast_radius_score": 8 }
}
```

### `GET /health`
```json
{ "status": "healthy", "service": "graphify-repograph-agent", "model": "gemma-4" }
```

---

## 🧩 How the Real Graphify Schema Is Produced

`bridge.py` emits valid Graphify `graph.json` schema v1 compatible with [`graphify.export.to_json()`](https://github.com/Graphify-Labs/graphify):

| Graphify field | Source |
|---|---|
| `graph.schema_version` | Hard-coded `1` |
| `nodes[*].id` | `<file_path>::<qualified_name>` |
| `nodes[*].label` | Symbol name (e.g. `process_transaction`) |
| `nodes[*].source_file` | Relative file path |
| `nodes[*].source_location` | `"L<start_line>"` |
| `nodes[*]._origin` | `"ast"` (repograph is deterministic AST) |
| `nodes[*].impact_status` | `modified` / `direct_dependent` / `indirect_dependent` / `unchanged` |
| `links[*].relation` | `calls` / `imports` / `inherits` / `defines` |
| `links[*].confidence` | `confirmed` / `inferred` (from repograph's resolver) |
