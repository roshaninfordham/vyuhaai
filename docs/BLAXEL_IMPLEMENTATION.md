# How Blaxel Is Implemented in Vyuha — Demo-Ready Guide

This document explains **where and how Blaxel is used** across the entire Vyuha software so you can answer expert questions during a demo.

---

## 1. What Blaxel Does in This Project (Two Roles)

Blaxel is used in **two distinct ways**:

| Role | What it does | Where in the codebase |
|------|----------------|------------------------|
| **1. Model gateway (LLM)** | Hosts the AI model that powers the **Commander** (decides FIRE_THRUSTERS vs HOLD_POSITION). All Commander LLM calls go through Blaxel’s API, not directly to OpenAI. | `agent/src/commander.py` |
| **2. Agent deployment (hosting)** | Runs the FastAPI backend as a **serverless agent**. You deploy with `bl deploy`; Blaxel builds, runs, and scales the service. | `blaxel.toml`, `agent/src/main.py` (entrypoint) |

So: **Blaxel both serves the LLM and hosts the app** that uses it.

---

## 2. Deployment: `blaxel.toml` (The Manifest)

**File:** `blaxel.toml` at the project root.

- **What it is:** Blaxel’s deployment manifest. It defines *what* gets deployed and *how* it is exposed.

**Key fields experts may ask about:**

| Field | Value | Meaning |
|-------|--------|---------|
| `name` | `vyuha-ai` | Agent name in Blaxel (used in URLs and CLI). |
| `workspace` | `rs` | Blaxel workspace (tenant). |
| `type` | `agent` | This is an agent (HTTP-serving app), not a bare function. |
| `public` | `true` | Deployed app is reachable at a public URL. |
| `models` | `["sandbox-openai"]` | Which Blaxel model this agent is allowed to use (the Commander uses this). |
| `functions` | `["vyuha-orbital-tools"]` | MCP / tool-servers the agent can call (optional; we use CelesTrak in-app). |
| `[env]` | `SPACECRAFT_MODE`, `COLLISION_THRESHOLD`, `STATE_PERSISTENCE`, `WHITE_CIRCLE_*`, etc. | Environment variables **baked into** the deployed container. Secrets (e.g. `WHITE_CIRCLE_API_KEY`) are set in the Blaxel **dashboard**, not in the file. |
| `[runtime]` | `timeout = 900`, `memory = 4096`, `generation = "mk3"` | Max request time (15 min), memory (4 GB), Blaxel runtime generation. |
| `[entrypoint]` | `prod = "python -m agent.src.main"` | Command that starts the app (our FastAPI server). |
| `[[triggers]]` | Multiple HTTP triggers | Each trigger exposes one **path** on the deployed base URL (e.g. `agents/vyuha-ai/scan`, `agents/vyuha-ai/act`, `agents/vyuha-ai/health`). |

**Triggers we expose:**  
`scan`, `act`, `state`, `restore`, `history`, `health` (public), `insights`, plus async `maneuver`.  
Each maps to the same FastAPI app; the path determines which endpoint is hit.

**Deploy command:** `bl login rs` then `bl deploy`. Blaxel builds from the repo, runs `python -m agent.src.main`, and routes HTTP traffic to it.

---

## 3. Backend Startup: Blaxel SDK and Telemetry (`main.py`)

**File:** `agent/src/main.py` (top of file).

**What happens at startup:**

1. **`blaxel.autoload()`**
   - We try: `from blaxel import autoload` then `autoload()`.
   - **Purpose:** Configures auth, telemetry, and tracing for the **deployed** environment when running on Blaxel. Safe to call when running **locally** (no Blaxel infra); it no-ops or adapts.
   - We set `_BLAXEL_READY = True/False` depending on success.

2. **`blaxel.telemetry`**
   - We try: `import blaxel.telemetry`.
   - **Purpose:** Optional OpenTelemetry instrumentation (traces/metrics) when running on Blaxel.
   - We set `_BLAXEL_TELEMETRY = True/False`.

3. **`/health` response**
   - Returns `blaxel_sdk: _BLAXEL_READY` and `blaxel_telemetry: _BLAXEL_TELEMETRY`.
   - **Why it matters:** Experts can call `GET /health` and see whether the Blaxel SDK and telemetry are active (e.g. in production vs local).

**Summary:** Blaxel is used in the backend for **lifecycle/observability** (autoload, telemetry) and to **expose readiness** via `/health`. The actual **LLM calls** are in the Commander.

---

## 4. Commander: How the LLM Is Called (`commander.py`)

**File:** `agent/src/commander.py`.

The Commander is the “brain” that turns telemetry (and optional rejection feedback) into a structured decision. **Every LLM call goes through Blaxel’s model gateway**, not directly to OpenAI.

### 4.1 Configuration (env)

- `BLAXEL_API_KEY` — API key for Blaxel (model gateway + optional deployment auth).
- `BLAXEL_WORKSPACE` — Workspace (e.g. `rs`). Used in the model URL.
- `BLAXEL_MODEL_NAME` — Model id in Blaxel (we use `sandbox-openai`).
- **Model base URL:**  
  `https://run.blaxel.ai/{BLAXEL_WORKSPACE}/models/{BLAXEL_MODEL_NAME}/v1`  
  So all chat completions hit Blaxel’s endpoint, not `api.openai.com`.

### 4.2 Two Code Paths (SDK vs Direct Client)

We support **two ways** to call the same Blaxel-hosted model:

**Path 1 — Blaxel SDK (preferred)**  
- We try: `from blaxel.core.models import BLModel` and create `BLModel(BLAXEL_MODEL_NAME)`.
- **Use:** When making the actual request, we call `_bl_model.get_parameters()` to get the resolved URL and model name, then we use the **OpenAI-compatible** chat completions API with:
  - **Headers:** `X-Blaxel-Authorization: Bearer <BLAXEL_API_KEY>`, `X-Blaxel-Workspace: <BLAXEL_WORKSPACE>`.
  - **Base URL:** The one returned by Blaxel (so we stay compatible with Blaxel’s routing and any future changes).
- **Why:** Automatic telemetry, token refresh, and best compatibility when running **on** Blaxel.

**Path 2 — Direct OpenAI client (fallback)**  
- If the SDK is not available (e.g. import fails or no BLModel), we use the standard `openai` Python client with:
  - `base_url` = `https://run.blaxel.ai/{workspace}/models/{model_name}/v1`
  - `api_key` = `BLAXEL_API_KEY`
  - A custom `httpx` client that adds **the same two headers**: `X-Blaxel-Authorization` and `X-Blaxel-Workspace`.
- **Why:** The Blaxel model API is **OpenAI-compatible**; we can call it with the OpenAI client as long as we send Blaxel’s auth headers.

**Which path runs:** The code tries the SDK path first (async); on any failure it falls back to the sync direct client. So **Blaxel is always the model gateway**; only the client (SDK vs direct) changes.

### 4.3 Request Flow (High Level)

1. `analyze_situation(risk_data, previous_rejection_reason)` is called from `main.py` when handling `POST /act`.
2. We build a **system prompt** (JSON rules: FIRE_THRUSTERS vs HOLD_POSITION, schema) and a **user prompt** (telemetry + optional rejection feedback).
3. We call the LLM via Blaxel (SDK or direct client) with `temperature=0.2`, `max_tokens=256`.
4. We parse the response as JSON, validate required keys, and return the decision (or a safe fallback on error).
5. That decision is then validated by the **Shield** (White Circle + local deny-list); if blocked, we pass the rejection reason back into `analyze_situation` for the next attempt.

**Important for demo:**  
- “The Commander does not call OpenAI directly. It calls **Blaxel’s model gateway** at `run.blaxel.ai` with our workspace and model name, using Blaxel auth headers.”  
- “We use the Blaxel SDK when available for telemetry and compatibility; otherwise we use the OpenAI client pointed at Blaxel’s URL with the same auth.”

---

## 5. Dashboard: Calling the Deployed Agent

**File:** `dashboard/app.py`.

When the dashboard talks to the **deployed** backend (Blaxel-hosted), it must authenticate.

- **Env:** `BLAXEL_API_KEY`, `BLAXEL_WORKSPACE` (or `BL_API_KEY`).
- **Behavior:** For every request to `API_URL` (e.g. `https://agt-vyuha-ai-xxxx.bl.run`), if `BLAXEL_API_KEY` is set, we add:
  - `X-Blaxel-Authorization: Bearer <BLAXEL_API_KEY>`
  - `X-Blaxel-Workspace: <BLAXEL_WORKSPACE>`
- **Where:** `_request_headers()` builds these; they are used for `/scan`, `/act`, `/state`, `/restore`, `/history`, `/insights`.

So: **Blaxel is used in the dashboard only for authenticating HTTP requests to the Blaxel-deployed agent.** The dashboard does not call the Blaxel model API directly; the **backend** does that in the Commander.

---

## 6. Environment Variables (Summary)

| Variable | Where used | Purpose |
|----------|------------|---------|
| `BLAXEL_API_KEY` | Commander, Dashboard | Auth for Blaxel model API and for calling the deployed agent. |
| `BLAXEL_WORKSPACE` | Commander, Dashboard, base URL | Workspace in URLs and auth. |
| `BLAXEL_MODEL_NAME` | Commander, blaxel.toml | Model id (e.g. `sandbox-openai`). |
| `BL_API_KEY` | Dashboard | Alias for `BLAXEL_API_KEY`. |

For **deployed** runs, these can be set in the Blaxel project (dashboard); for **local** runs, they go in `.env`.

---

## 7. End-to-End Flow (For “Walk Me Through It” Questions)

1. **User** clicks “Simulate Debris” or “Simulate Cyberattack” in the dashboard.
2. **Dashboard** sends `POST /act` (and optionally `POST /scan` first) to the backend URL (local or Blaxel). If the URL is Blaxel, it sends `X-Blaxel-Authorization` and `X-Blaxel-Workspace`.
3. **Backend** (FastAPI, running locally or **on Blaxel** via `python -m agent.src.main`):
   - Receives the request.
   - Calls `commander.analyze_situation(risk_data, rejection_reason)`.
4. **Commander**:
   - Builds prompts.
   - Calls the **Blaxel model gateway** (SDK or direct client with Blaxel base URL + auth headers).
   - Parses JSON and returns a decision.
5. **Backend** runs the **Shield** (White Circle + local deny-list) on that decision. If blocked, it retries the Commander with the rejection reason (up to `MAX_RETRIES`).
6. **Backend** returns the final status (EXECUTED or MANUAL_OVERRIDE), and optionally persists state.
7. **Dashboard** displays the result and, for cyberattack demo, the Attack → Defense → Resilience view.

So: **Blaxel appears in (a) hosting the FastAPI app, (b) providing the LLM for the Commander, and (c) authenticating dashboard → agent requests.**

---

## 8. Quick Answers for Common Expert Questions

- **“Where does the LLM run?”**  
  On **Blaxel’s model gateway** (`run.blaxel.ai`). We use the model named in `blaxel.toml` and `BLAXEL_MODEL_NAME` (e.g. `sandbox-openai`).

- **“Do you call OpenAI directly?”**  
  No. All Commander LLM calls go through Blaxel (same OpenAI-compatible API, but Blaxel’s URL and auth).

- **“How do you authenticate to Blaxel?”**  
  With `BLAXEL_API_KEY` and `BLAXEL_WORKSPACE`. In code we send `X-Blaxel-Authorization: Bearer <key>` and `X-Blaxel-Workspace: <workspace>` on every model request and, from the dashboard, on every request to the deployed agent.

- **“What is `blaxel.toml`?”**  
  The **deployment manifest**: agent name, workspace, type, models, env, runtime, entrypoint (`python -m agent.src.main`), and HTTP triggers (paths) for the deployed app.

- **“What’s the entrypoint?”**  
  `python -m agent.src.main` — that starts our FastAPI app. Blaxel runs this in the container.

- **“How do you know Blaxel is working when running locally?”**  
  We call `GET /health` and check `blaxel_sdk` and `blaxel_telemetry`. When deployed, the same endpoint confirms the app is up; White Circle config is separate (`white_circle_configured`).

- **“Why two paths in the Commander (SDK vs direct client)?”**  
  Resilience: if the Blaxel SDK isn’t available (e.g. different environment), we still call the same Blaxel model API using the OpenAI client and Blaxel’s auth headers.

---

## 9. File Reference

| File | Blaxel usage |
|------|------------------|
| `blaxel.toml` | Deployment: name, workspace, type, models, functions, env, runtime, entrypoint, HTTP triggers. |
| `agent/src/main.py` | `blaxel.autoload()`, `blaxel.telemetry`, `/health` (`blaxel_sdk`, `blaxel_telemetry`). |
| `agent/src/commander.py` | Model gateway: BLModel (SDK), OpenAI client + Blaxel base URL and `X-Blaxel-*` headers; `analyze_situation()` calls Blaxel. |
| `dashboard/app.py` | `_request_headers()` adds `X-Blaxel-Authorization` and `X-Blaxel-Workspace` when calling the deployed agent. |
| `.env.example` | Documents `BLAXEL_API_KEY`, `BLAXEL_WORKSPACE`, `BLAXEL_MODEL_NAME`, and deployment note. |

This should be enough to explain **in detail** how Blaxel is implemented across the entire software during a demo.
