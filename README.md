# Vyuha — The Autonomous Orbital Overseer

**Vyuha** is an agentic AI that autonomously navigates the **lethal kinetic reality** of Low Earth Orbit, securing the **$2 trillion space economy**. It is a production-grade Space Domain Awareness agent: real-time open telemetry, autonomous collision prediction and avoidance, and White Circle–validated commands to prevent the "autonomous insider threat" (indirect prompt injection). All capabilities are visible and usable in the API and Mission Control dashboard, including **real-time orbits**, **simulation modes**, and a **cyberattack resilience demo**.

---

## The Problem

Low Earth Orbit is degrading into a congested **junkyard**. With satellite counts projected to jump from **15,000 to 100,000 by 2030**, and over **one million** pieces of lethal debris in orbit, the volume of tracking data has vastly exceeded human analytical capacity. Traditional manual oversight is **too slow** to prevent catastrophic collisions in this high-velocity environment.

---

## The Solution

**Vyuha** decouples satellite operations from terrestrial control. By ingesting real-time open telemetry (CelesTrak Open Data), it:

- **Predicts** — autonomously identifies collision risks (conjunctions) in real time.
- **Acts** — calculates and executes avoidance maneuvers without human-in-the-loop latency.
- **Protects** — uses a **White Circle** security gateway to validate every orbital command, preventing **indirect prompt injection** from hijacking satellite thrusters or causing intentional de-orbit.

It addresses a **critical United States strategic priority**, uses **Blaxel** for serverless agent deployment, and implements **White Circle** to solve the "autonomous insider threat," delivering a production-grade solution to a multibillion-dollar friction point.

---

## Capabilities

| Area | Capability | API / UI |
|------|------------|----------|
| **Orbital ingestion** | Live ISS TLE from CelesTrak; hybrid demo (real telemetry + forced critical scenario) | `POST /scan` · **Scan SECTOR (LIVE)** · **Simulate Debris (DEMO)** |
| **Autonomous loop** | Commander decides; Shield validates; self-correction on block | `POST /act` · Automatic on CRITICAL scan |
| **Cyberattack & resilience** | Simulate indirect prompt injection → White Circle blocks → Commander issues safe command | `POST /act` with `simulate_cyberattack: true` · **Simulate Cyberattack** button |
| **Security** | White Circle validation + local deny-list fallback | Applied in `/act`; visible in chain-of-thought and Cyberattack panel |
| **State & memory** | Persistent position, original trajectory, maneuver history | `GET /state`, `POST /restore`, `GET /history` · Dashboard: State & Memory panel |
| **Learning** | Event store + success rate, latency, violation tags, recommendations | `GET /insights` · Autonomous Learning panel |
| **Observability** | Health, OpenAPI docs, trace IDs, structured logs | `GET /health`, `GET /docs` |

All capabilities are **visible and usable** in the software: real-time orbits and telemetry, simulation (debris and cyberattack), state/memory, and learning panel.

---

## Run Locally

Follow these steps to run the backend API and the Mission Control dashboard on your machine.

### 1. Clone and enter the repo

```bash
git clone https://github.com/roshaninfordham/vyuhaai.git
cd vyuhaai
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- **Blaxel** (Commander model): `BLAXEL_API_KEY`, `BLAXEL_WORKSPACE`
- **White Circle** (guardrails): `WHITE_CIRCLE_API_KEY`, `WHITE_CIRCLE_DEPLOYMENT_ID`
- **Dashboard** (optional): `VYUHA_API_URL=http://localhost:8000` (default)

See `.env.example` for all options. Do not commit `.env`; it is git-ignored.

### 5. Start the backend API

```bash
python -m agent.src.main
```

Or with uvicorn directly:

```bash
uvicorn agent.src.main:app --host 0.0.0.0 --port 8000
```

- API root: **http://localhost:8000**
- OpenAPI docs: **http://localhost:8000/docs**
- Health: **http://localhost:8000/health**

### 6. Start the Mission Control dashboard (second terminal)

```bash
source .venv/bin/activate
streamlit run dashboard/app.py --server.port 8501
```

- Dashboard: **http://localhost:8501**

Use **Scan SECTOR (LIVE)** for real telemetry, **Simulate Debris (DEMO)** to force a critical scenario and trigger the autonomous act loop, or **Simulate Cyberattack** to see how an attacker's injected command is blocked by White Circle and how the system remains resilient. The sidebar shows The Problem, The Solution, and Run Locally; the right column shows State & Memory and Maneuver History.

---

## Deploy with Blaxel and White Circle AI

The backend is deployed as a Blaxel agent. White Circle AI is used at runtime to validate every Commander command (Shield). Both must be configured for production.

### 1. Prerequisites

- **Blaxel CLI** installed and logged in: `bl login <workspace>`
- **White Circle AI** account: API key and Deployment ID (from [White Circle](https://us.whitecircle.ai) or your admin)
- `blaxel.toml` and entrypoint are in the repo

### 2. Set environment variables in Blaxel

Before or after first deploy, set these in your **Blaxel project** (dashboard or CLI):

| Variable | Required | Description |
|----------|----------|-------------|
| `WHITE_CIRCLE_API_KEY` | **Yes** | White Circle API key (secret) |
| `WHITE_CIRCLE_DEPLOYMENT_ID` | **Yes** | White Circle deployment/policy ID for session check |
| `WHITE_CIRCLE_BASE_URL` | No | Default `https://us.whitecircle.ai` (in `blaxel.toml` [env]) |
| `WHITE_CIRCLE_VERSION` | No | Default `2025-12-01` (in `blaxel.toml` [env]) |
| `BLAXEL_API_KEY` / workspace | Usually | Often auto-injected by Blaxel for model gateway |

Without `WHITE_CIRCLE_API_KEY` and `WHITE_CIRCLE_DEPLOYMENT_ID`, the Shield falls back to local deny-list only; `/health` will report `white_circle_configured: false`.

### 3. Deploy

```bash
bl login rs
bl deploy
```

Note the deployed base URL (e.g. `https://agt-vyuha-ai-xxxx.bl.run`).

### 4. Point the dashboard at the deployed API

```bash
export VYUHA_API_URL=https://agt-vyuha-ai-xxxx.bl.run
streamlit run dashboard/app.py --server.port 8501
```

For **authenticated** requests from the dashboard to the Blaxel agent, set in `.env` (or the environment where Streamlit runs):

- `BLAXEL_API_KEY`
- `BLAXEL_WORKSPACE=rs`

### 5. Verify deployment

1. **Health (Blaxel + White Circle)**  
   ```bash
   curl https://agt-vyuha-ai-xxxx.bl.run/health
   ```  
   Expect `"status": "ok"`, `"white_circle_configured": true` if White Circle env vars are set in Blaxel.

2. **White Circle in action**  
   Open the dashboard, click **Simulate Cyberattack**. You should see Attempt 1 (malicious command) **blocked** and Attempt 2 (safe command) **approved**. That confirms White Circle is validating and the system is resilient.

3. **Endpoints**  
   All triggers in `blaxel.toml` (scan, act, state, restore, history, health, insights) should be reachable at the deployed base URL.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service status and endpoint index |
| `GET` | `/health` | Liveness and telemetry readiness |
| `POST` | `/scan` | Conjunction scan (live or simulated); query `?simulate_danger=true` for demo |
| `POST` | `/act` | Autonomous Commander → Shield loop; body: `{"risk_data": {...}, "simulate_cyberattack": false}` (set `simulate_cyberattack: true` for cyberattack resilience demo) |
| `GET` | `/state` | Current spacecraft state (position, last maneuver, original trajectory) |
| `POST` | `/restore` | Restore spacecraft to original trajectory (clear deviation) |
| `GET` | `/history` | Maneuver history and original trajectory |
| `GET` | `/insights` | Runtime analytics and recommendations |
| `GET` | `/docs` | OpenAPI interactive documentation |

---

## Production, Security & Scalability

- **Secrets**: All secrets are in environment variables. `.env` is git-ignored; use `.env.example` as a template. Never commit API keys or deployment IDs.
- **Data**: Runtime files (`agent/data/*.jsonl`, `agent/data/spacecraft_state.json`) are git-ignored. Use volumes or persistent storage in production so state and events survive restarts.
- **Security**: Every proposed command is validated by White Circle and a local deny-list before execution, addressing **indirect prompt injection** (autonomous insider threat). Blocked commands trigger a self-correction loop with bounded retries; after exhaustion the API returns MANUAL_OVERRIDE_REQUIRED. The **Simulate Cyberattack** flow demonstrates attack → block → resilience.
- **Observability**: Structured logging, optional Blaxel telemetry, and `/insights` support post-incident analysis and tuning. Use `X-Request-ID` and response headers for tracing.
- **Scalability**: The FastAPI app is stateless except for in-memory state (loaded from disk on startup). For horizontal scaling, ensure state persistence is on shared or replicated storage if multiple instances are used. Blaxel deployment handles scaling of the agent.
- **Bounded retries**: `MAX_RETRIES` (default 3) limits Commander retries per `/act` request to avoid unbounded loops.

---

## Tech Stack

- **Backend**: FastAPI, Pydantic, Uvicorn
- **Orbital mechanics**: Skyfield, NumPy, CelesTrak TLE feed
- **AI**: Blaxel model gateway (OpenAI-compatible path for Commander)
- **Security**: White Circle AI + local deny-list fallback
- **Frontend**: Streamlit, Plotly
- **State & learning**: File-based state (`agent/data/spacecraft_state.json`), JSONL event store, `/insights` analytics
- **Deployment**: Blaxel (`blaxel.toml`)

---

## Documentation Index

- **README.md** (this file) — Problem, capabilities, run locally, deploy, API, production notes
- **agent/README.md** — Backend subsystem overview
- **agent/src/README.md** — Module-level design
- **agent/data/README.md** — Runtime data and learning store
- **dashboard/README.md** — Mission Control UI and demo usage

---

## Quick Verification

- **Local backend**: `curl http://localhost:8000/health` — check `white_circle_configured`
- **Deployed (Blaxel)**: `curl https://<your-blaxel-url>/health` — same; ensures White Circle env is set in Blaxel
- **White Circle API**: `python scripts/verify_whitecircle.py` — requires `.env` with `WHITE_CIRCLE_API_KEY` and `WHITE_CIRCLE_DEPLOYMENT_ID`
- **State demo**: `python scripts/demo_state_management.py` (backend running; set `BASE_URL` if not localhost)
