# Graphify-Repograph Agent 🧠🕸️

> **Hacktoberfest Hack Day Flagship Project**  
> A self-hosted, multimodal code review agent and real-time visualization tool that converts code repositories into graph-aware contexts, evaluates incoming pull requests using **Gemma 4** (via the Gemini API), and deploys live to **Cloudways by DigitalOcean**.

---

## 🏆 Challenge & Track Alignment

1. **Best Open-Source AI Project**:
   - Self-hosted, deterministic open harness using AST trees instead of naive vector embeddings.
   - Zero hallucination in symbol navigation: maps exact call graphs, class inheritance, and file dependencies.
2. **Best Use of Gemma 4**:
   - Evaluates incoming PRs multimodally: takes raw unified Git diffs + Graphify structural JSON + base64 rendered graph topology diagrams.
   - Outputs strict, validated JSON with blast radius severity ratings, breaking change detection, and unified Git patch recommendations.
3. **Best Use of Graphify**:
   - Bridges AST extractions from `repograph` into official `graph.json` Graphify-compliant schemas.
   - Calculates 1-hop and 2-hop upstream caller propagation to isolate the blast radius before sending to the model.
4. **Best Use of Cloudways**:
   - Fully automated production deployment pipeline script (`deploy.sh`) targeting Cloudways by DigitalOcean via the Cloudways REST API v1.
   - Containerized with multi-stage production Docker packaging, non-root security profiles, and automated health checks.

---

## 👥 3-Person Team Division of Labor

```
┌────────────────────────────────────────────────────────────────────────┐
│                      GRAPHIFY-REPOGRAPH AGENT                          │
└────────────────────────────────────────────────────────────────────────┘
          │                                           │
  [ MEMBER 1: CORE ENGINE ]                   [ MEMBER 2: AI AGENT ]
  parser.py & bridge.py                       ai_agent.py
  - AST Parser (Python & JS/TS)               - Google Gemini API (Gemma 4)
  - Graphify JSON Bridge                      - Multimodal Diff + Image Input
  - Blast Radius (1-hop / 2-hop)              - Structured Review Schema
          │                                           │
          └─────────────────────┬─────────────────────┘
                                │
                    [ MEMBER 3: FULL-STACK & DEPLOY ]
                    server.py, Dockerfile, deploy.sh
                    - FastAPI Endpoints (POST /analyze, GET /health)
                    - D3.js Force-Directed Interactive Canvas
                    - Real-time Gemma 4 Slide-out Review Drawer
                    - Cloudways by DigitalOcean Deploy Scripts
```

---

## 📂 Deliverables Overview

| Member | File | Purpose |
|---|---|---|
| **Member 1** | [`parser.py`](file:///home/darion-dev/Dev/Incubator/repograph/parser.py) | Parses Python & JS/TS AST trees into deterministic `Node` and `Edge` objects. Resolves call targets, inheritance hierarchies, and imports. |
| **Member 1** | [`bridge.py`](file:///home/darion-dev/Dev/Incubator/repograph/bridge.py) | Converts AST graphs into Graphify `graph.json` format. Computes 1-hop and 2-hop blast radii from diff hunks and renders visual topology PNGs. |
| **Member 2** | [`ai_agent.py`](file:///home/darion-dev/Dev/Incubator/repograph/ai_agent.py) | Connects to Gemma 4 via Google Gemini API. Analyzes diffs + Graphify context + visual topology. Outputs validated JSON schema. |
| **Member 3** | [`server.py`](file:///home/darion-dev/Dev/Incubator/repograph/server.py) | FastAPI server serving `POST /analyze` and an interactive D3.js dark-mode visualizer with animated gauge and patch viewer. |
| **Member 3** | [`deploy.sh`](file:///home/darion-dev/Dev/Incubator/repograph/deploy.sh) | Production deployment shell script for Cloudways REST API v1 OAuth token retrieval, Git deployment, and healthchecks. |
| **Member 3** | [`Dockerfile`](file:///home/darion-dev/Dev/Incubator/repograph/Dockerfile) | Multi-stage, non-root production container packaging the complete application. |

---

## 🚀 Quickstart & Local Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
```bash
# For live Gemma 4 inference via Google Gemini API
export GEMINI_API_KEY="your-google-gemini-api-key"
export GEMMA_MODEL="gemma-4"
```
*(Note: If no API key is set, the agent seamlessly operates in deterministic offline AST mock mode for testing and local evaluation!)*

### 3. Run Integration Verification
```bash
python3 test_pipeline.py
```

### 4. Start Dashboard Locally
```bash
python3 server.py
# or
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser. Click **⚡ Load Demo PR** and **▶ Run Gemma 4 Review** to explore the real-time visual graph and AI drawer.

---

## ☁️ Deploying to Cloudways by DigitalOcean

### Option A: Automated Cloudways REST API Deployment
```bash
export CLOUDWAYS_EMAIL="developer@example.com"
export CLOUDWAYS_API_KEY="your-api-key"
export CLOUDWAYS_SERVER_ID="123456"
export CLOUDWAYS_APP_ID="654321"
export APP_LIVE_URL="https://phpstack-xxxx-xxxx.cloudwaysapps.com"

./deploy.sh --email "$CLOUDWAYS_EMAIL" \
            --api-key "$CLOUDWAYS_API_KEY" \
            --server-id "$CLOUDWAYS_SERVER_ID" \
            --app-id "$CLOUDWAYS_APP_ID" \
            --live-url "$APP_LIVE_URL"
```

### Option B: Container Deployment via Docker / SSH
```bash
./deploy.sh --mode docker-ssh
```

---

## 📡 API Reference

### `POST /analyze`
Receives code diff and repository path, runs the AST parser, computes the Graphify blast radius, and returns Gemma 4's evaluation.

**Request Payload:**
```json
{
  "repo_path": ".",
  "git_diff": "--- a/app.py\n+++ b/app.py\n...",
  "diff_files": ["app.py"],
  "generate_image": true
}
```

**Response Payload:**
```json
{
  "review": {
    "impact_rating": 8,
    "breaking_changes": [
      "Altered signature in calculate_tax may break 5 direct callers: checkout_flow, invoice_job"
    ],
    "architectural_summary": "Gemma 4 evaluated 2 modified AST nodes with a downstream blast radius of 5 dependents...",
    "patch_recommendation": "--- a/app.py\n+++ b/app.py\n@@ -10,3 +10,4 @@..."
  },
  "graph": {
    "graph_version": "1.0",
    "nodes": [...],
    "edges": [...],
    "stats": { ... }
  },
  "graph_image_b64": "iVBORw0KGgo...",
  "stats": {
    "blast_radius_score": 8,
    "modified_count": 2,
    "direct_dependent_count": 5
  }
}
```

### `GET /health`
Returns health check status for load balancers and uptime probes.
